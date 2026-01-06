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
    EditFileTool, GitDiffTool, GitAddTool, GitCommitTool, GitCheckoutTool, GitBranchTool,
    GitPushTool, GitPullTool,
    GitHubCreateIssueTool, GitHubCreatePRTool,
    WebSearchTool, BrowseURLTool, CodebaseSearchTool, GetDefinitionsTool, ScratchpadTool
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
    USAGE = "usage"

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
    MAX_HISTORY_MESSAGES = 40

    def __init__(self, sandbox_enabled: bool = False):
        self.registry = ToolRegistry()
        self.mcp_clients: List[MCPClient] = []
        self.sandbox_enabled = sandbox_enabled
        self.sandbox = PersistentSandbox() if sandbox_enabled else None
        self.container_started = False
        self.load_base_tools()
        self.providers = []
        self.active_provider_index = 0
        self.session_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost": 0.0}

        # Naive pricing map (per 1M tokens)
        self.PRICING_MAP = {
            "gemini-2.0-flash": (0.10, 0.40),
            "gemini-1.5-flash": (0.075, 0.30),
            "gemini-1.5-pro": (1.25, 5.00),
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "claude-3-5-sonnet": (3.00, 15.00),
            "llama-3.3-70b-versatile": (0.59, 0.79), # Groq
        }

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimates cost based on model and token counts."""
        rates = self.PRICING_MAP.get(model.lower(), (0.50, 1.50)) # Default fallback
        cost = (prompt_tokens / 1_000_000 * rates[0]) + (completion_tokens / 1_000_000 * rates[1])
        return cost

    def load_base_tools(self):
        """Loads all built-in tools into the registry."""
        tools = [
            ReadFileTool(), WriteFileTool(), ListDirTool(), RunShellTool(),
            PythonSandboxTool(), GrepTool(), GitStatusTool(), EditFileTool(),
            GitDiffTool(), GitAddTool(), GitCommitTool(), GitCheckoutTool(), GitBranchTool(),
            GitPushTool(), GitPullTool(),
            GitHubCreateIssueTool(), GitHubCreatePRTool(),
            WebSearchTool(), BrowseURLTool(), CodebaseSearchTool(), GetDefinitionsTool(), ScratchpadTool()
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
                    # Hybrid Support: Convert legacy ProviderConfig to MCPServerConfig
                    if p_config.base_url and p_config.base_url.startswith("stdio://"):
                        cmd_str = p_config.base_url[len("stdio://"):]
                        parts = cmd_str.split()
                        if parts:
                            from plexir.core.config_manager import MCPServerConfig
                            # Naive split: command is parts[0], args are parts[1:]
                            legacy_mcp_config = MCPServerConfig(
                                command=parts[0],
                                args=parts[1:],
                                env={}
                            )
                            mcp_client = MCPClient(p_config.name, legacy_mcp_config, self.registry)
                            await mcp_client.connect()
                            self.mcp_clients.append(mcp_client)
                    else:
                        logger.warning(f"Legacy MCP provider '{p_config.name}' ignored: Invalid base_url (must start with stdio://).")
            except Exception as e:
                logger.error(f"Failed to load provider {name}: {e}")

        # Load MCP Servers
        for name, mcp_config in config_manager.config.mcp_servers.items():
            if mcp_config.disabled:
                continue
            try:
                mcp_client = MCPClient(name, mcp_config, self.registry)
                # We start connection in background or await it? 
                # Ideally await to ensure tools are ready before first turn.
                await mcp_client.connect()
                self.mcp_clients.append(mcp_client)
            except Exception as e:
                logger.error(f"Failed to load MCP server '{name}': {e}")

    async def route(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any], RouterEvent], None]:
        """
        Orchestrates LLM generation with smart retries and wrap-around failover.
        """
        # 0. Check budget
        budget = config_manager.config.session_budget
        if budget > 0 and self.session_usage["total_cost"] >= budget:
            yield f"\n[ERROR] Session budget exceeded (${self.session_usage['total_cost']:.2f} >= ${budget:.2f})."
            return

        # 1. Check for summarization
        if len(history) > self.MAX_HISTORY_MESSAGES:
            yield RouterEvent("system", data="Summarizing old conversation history to save context...")
            await self.summarize_session(history)

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

# Core Instructions
1. **Plan First**: For complex tasks, use the `scratchpad` to outline your plan before executing code.
2. **Context is King**: If you are unsure where code is located, use `codebase_search` to find it. Do not guess file paths.
3. **Verify**: After editing files, use `grep_search` or `read_file` to verify the changes were applied correctly.
4. **Safety**: When using `edit_file` or `write_file`, you will be asked for confirmation. Ensure your edits are precise.

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
            max_retries = 10
            for attempt in range(max_retries + 1):
                try:
                    first_chunk = True
                    async for chunk in provider.generate(history, turn_prompt):
                        if first_chunk:
                            self.active_provider_index = actual_index
                            first_chunk = False
                        
                        if isinstance(chunk, dict) and chunk.get("type") == "usage":
                            p_tokens = chunk.get("prompt_tokens", 0)
                            c_tokens = chunk.get("completion_tokens", 0)
                            t_tokens = chunk.get("total_tokens", 0)
                            
                            self.session_usage["prompt_tokens"] += p_tokens
                            self.session_usage["completion_tokens"] += c_tokens
                            self.session_usage["total_tokens"] += t_tokens
                            
                            cost = self._calculate_cost(provider.model_name, p_tokens, c_tokens)
                            self.session_usage["total_cost"] += cost
                            
                            chunk["total_cost_accumulated"] = self.session_usage["total_cost"]
                            yield RouterEvent(RouterEvent.USAGE, data=chunk)
                            continue
                            
                        yield chunk
                    return # Success! 

                except Exception as e:
                    if is_retryable_error(e) and attempt < max_retries:
                        # Exponential backoff: 1s, 2s, 4s, 8s, 16s... capped at 30s
                        wait_time = min(2 ** attempt, 30)
                        yield RouterEvent(RouterEvent.RETRY, data={
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "max": max_retries,
                            "error": str(e),
                            "wait": wait_time
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

    async def summarize_session(self, history: List[Dict[str, Any]]):
        """
        Summarizes older parts of the conversation to save context.
        """
        to_summarize, to_keep = context.get_messages_to_summarize(history, 20)
        if not to_summarize:
            return

        summary_prompt = "Summarize the following conversation history concisely, focusing on key decisions, findings, and completed tasks. Maintain essential technical details."
        distilled_to_summarize = context.distill(to_summarize)
        
        provider = self.providers[self.active_provider_index]
        summary_text = ""
        
        try:
            async for chunk in provider.generate([], f"{summary_prompt}\n\n{distilled_to_summarize}"):
                if isinstance(chunk, str):
                    summary_text += chunk
            
            if summary_text:
                # Replace history with summary + pinned + recent
                new_history = [
                    {"role": "system", "content": f"BACKGROUND SUMMARY of previous conversation:\n{summary_text.strip()}", "pinned": True}
                ] + to_keep
                # In-place update of history list
                history.clear()
                history.extend(new_history)
                logger.info("Session history summarized.")
        except Exception as e:
            logger.error(f"Failed to summarize session: {e}")
