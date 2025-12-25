"""
Core routing logic for Plexir.
Manages provider selection, failover, and tool orchestration with smart retries.
"""

import asyncio
import logging
from typing import List, Dict, Any, AsyncGenerator, Union, Optional

from plexir.tools.base import ToolRegistry
from plexir.tools.definitions import (
    ReadFileTool, WriteFileTool, ListDirTool, RunShellTool, GrepTool, GitStatusTool,
    EditFileTool, GitDiffTool, GitAddTool, GitCommitTool, WebSearchTool, BrowseURLTool
)
from plexir.tools.sandbox import PythonSandboxTool, PersistentSandbox
from plexir.core import context
from plexir.core.config_manager import config_manager
from plexir.core.providers import GeminiProvider, OpenAICompatibleProvider
from plexir.mcp.client import MCPClient

logger = logging.getLogger(__name__)

class RouterEvent:
    """Events emitted by the router during generation."""
    FAILOVER = "failover"
    RETRY = "retry"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    def __init__(self, event_type: str, data: Any = None):
        self.type = event_type
        self.data = data

def is_retryable_error(error: Exception) -> bool:
    """
    Determines if an error is a transient rate limit or a fatal resource exhaustion.
    """
    err_str = str(error).lower()
    
    # Check for hard exhaustion (Resource Exhaustion / Fatal)
    # If it says 'quota' or 'daily', it's usually a hard limit that won't resolve by retrying.
    if "quota" in err_str or "daily" in err_str or "exceeded your current" in err_str:
        return False
        
    # Check for transient rate limits (RPM/TPM)
    if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
        return True
        
    # Check for transient server errors
    if any(code in err_str for code in ["500", "502", "503", "504"]):
        return True
        
    return False

class Router:
    """
    Manages LLM providers, tool registries, and failover logic with smart retries.
    """
    
    def __init__(self, sandbox_enabled: bool = False):
        self.registry = ToolRegistry()
        self.mcp_clients: List[MCPClient] = []
        self.sandbox_enabled = sandbox_enabled
        self.sandbox = PersistentSandbox() if sandbox_enabled else None
        self.container_started = False
        self.load_base_tools()
        self.providers = []
        self.active_provider_index = 0

    def load_base_tools(self):
        """Loads all built-in tools into the registry."""
        tools = [
            ReadFileTool(), WriteFileTool(), ListDirTool(), RunShellTool(),
            PythonSandboxTool(), GrepTool(), GitStatusTool(), EditFileTool(),
            GitDiffTool(), GitAddTool(), GitCommitTool(), WebSearchTool(), BrowseURLTool()
        ]
        for tool in tools:
            if self.sandbox:
                tool.sandbox = self.sandbox
            self.registry.register(tool)

    async def reload_providers(self):
        """Re-initializes providers based on current configuration."""
        if self.sandbox and not self.container_started:
             await self.sandbox.start()
             self.container_started = True

        for client in self.mcp_clients:
            await client.disconnect() 
        self.mcp_clients.clear()

        self.registry = ToolRegistry() 
        self.load_base_tools()

        self.providers = []
        order = config_manager.config.active_provider_order
        
        for name in order:
            p_config = config_manager.get_provider_config(name)
            if not p_config: continue
            
            try:
                if p_config.type == "gemini":
                    self.providers.append(GeminiProvider(p_config, self.registry))
                elif p_config.type in ["openai", "groq", "ollama"]:
                    self.providers.append(OpenAICompatibleProvider(p_config, self.registry))
                elif p_config.type == "mcp":
                    mcp_client = MCPClient(p_config, self.registry)
                    await mcp_client.connect()
                    self.mcp_clients.append(mcp_client)
            except Exception as e:
                logger.error(f"Failed to load provider {name}: {e}")

    async def route(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any], RouterEvent], None]:
        """
        Orchestrates LLM generation with smart retries and wrap-around failover.
        """
        num_providers = len(self.providers)
        if num_providers == 0:
            yield "\n[System Error]: No LLM providers available."
            return

        tool_names_desc = "\n".join([f"- {t.name}: {t.description}" for t in self.registry.list_tools()])
        
        sandbox_notice = ""
        if self.sandbox_enabled:
            sandbox_notice = "\n\nENVIRONMENT: Persistent Docker Sandbox active."

        default_prompt_template = """You are Plexir, an advanced AI Assistant.
CRITICAL: You have ACCESS to system tools. Use them proactively{sandbox_notice}

Available Tools:
{tool_descriptions}
"""
        current_system_prompt_base = system_instruction or default_prompt_template.format(
            tool_descriptions=tool_names_desc,
            sandbox_notice=sandbox_notice
        )

        if self.active_provider_index >= num_providers:
            self.active_provider_index = 0
            
        start_index = self.active_provider_index
        all_provider_errors = []

        # Outer loop: Try each provider
        for i in range(num_providers):
            actual_index = (start_index + i) % num_providers
            provider = self.providers[actual_index]
            
            # Reset prompt for this provider attempt
            turn_prompt = current_system_prompt_base
            if i > 0:
                yield RouterEvent(RouterEvent.FAILOVER, data=provider.name)
                distilled = context.distill(history)
                turn_prompt = f"{turn_prompt}\n\n[CONTEXT RESTORED]:\n{distilled}"

            # Inner loop: Retry transient errors
            max_retries = 20
            for attempt in range(max_retries + 1):
                try:
                    first_chunk = True
                    async for chunk in provider.generate(history, turn_prompt):
                        if first_chunk:
                            self.active_provider_index = actual_index
                            first_chunk = False
                        yield chunk
                    return # Success! 

                except Exception as e:
                    if is_retryable_error(e) and attempt < max_retries:
                        wait_time = 2
                        yield RouterEvent(RouterEvent.RETRY, data={
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "max": max_retries,
                            "error": str(e)
                        })
                        await asyncio.sleep(wait_time)
                        continue # Retry same provider
                    
                    # Not retryable or max retries hit
                    logger.error(f"Provider {provider.name} failed (fatal/max retries): {e}")
                    all_provider_errors.append(f"• {provider.name}: {e}")
                    break # Move to next provider in outer loop

        # All options exhausted
        self.active_provider_index = 0
        final_msg = "\n[System Error]: All providers failed:\n" + "\n".join(all_provider_errors)
        yield final_msg
        raise RuntimeError("Failover exhausted.")

    def reset_provider(self):
        """Resets the active provider to index 0."""
        self.active_provider_index = 0

    def get_tool(self, name: str):
        """Retrieves a tool by name."""
        return self.registry.get(name)
