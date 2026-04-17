"""
Core routing logic for Plexir.
Manages provider selection, failover, and tool orchestration with smart retries.
"""

import asyncio
import logging
import random
import re
import os
import time
from typing import List, Dict, Any, AsyncGenerator, Union, Optional

from plexir.tools.base import ToolRegistry
from plexir.tools.definitions import (
    ReadFileTool, WriteFileTool, ListDirTool, RunShellTool, GrepTool, GitStatusTool,
    EditFileTool, GitDiffTool, GitAddTool, GitCommitTool, GitCheckoutTool, GitBranchTool,
    GitPushTool, GitPullTool,
    GitHubCreateIssueTool, GitHubCreatePRTool,
    WebSearchTool, BrowseURLTool, CodebaseSearchTool, GetDefinitionsTool, GetRepoMapTool, ScratchpadTool,
    ExportSandboxTool, DelegateToAgentTool, SaveMemoryTool, SearchMemoryTool
)
from plexir.tools.sandbox import PythonSandboxTool, PersistentSandbox
from plexir.core import context
from plexir.core.config_manager import config_manager
from plexir.core.providers import GeminiProvider, OpenAICompatibleProvider
from plexir.mcp.client import MCPClient
from plexir.core.skills import SkillManager
from plexir.core.agents import get_agent_role

logger = logging.getLogger(__name__)

class RouterEvent:
    """Represents events emitted by the Router during the generation process.

    RouterEvent acts as a structured communication bridge between the Router's 
    internal orchestration logic and external consumers (such as the TUI or 
    API layers). Instead of returning raw strings, the Router yields these events 
    to signal non-textual updates like tool executions, token usage, or provider 
    failovers, allowing the UI to render specialized widgets or status indicators.

    Attributes:
        FAILOVER (str): Event type indicating a switch to a different LLM provider 
            after a fatal error or quota exhaustion.
        RETRY (str): Event type indicating a retry attempt due to a transient 
            error (e.g., 429 Rate Limit).
        TOOL_CALL (str): Event type indicating a tool is being invoked by the LLM.
        TOOL_RESULT (str): Event type indicating a tool has completed and its 
            result is being returned to the model.
        USAGE (str): Event type indicating token usage and cost updates for 
            the current request.
        THOUGHT (str): Event type indicating the model's internal reasoning 
            (e.g., <think> blocks in DeepSeek or internal chain-of-thought).
        PROGRESS (str): Event type indicating general progress updates.
        SYSTEM (str): Event type indicating system-level notifications or 
            internal state changes (e.g., summarization).
        ERROR (str): Event type indicating a non-fatal error occurred.
        SUBAGENT_START (str): Event type signaling the start of a specialized 
            sub-agent's execution.
        SUBAGENT_END (str): Event type signaling the completion of a 
            specialized sub-agent's task.
    """
    FAILOVER = "failover"
    RETRY = "retry"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    THOUGHT = "thought"
    PROGRESS = "progress"
    SYSTEM = "system"
    ERROR = "error"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    SUMMARIZATION = "summarization"

    def __init__(self, event_type: str, data: Any = None, metadata: Optional[Dict[str, Any]] = None):
        """Initializes a RouterEvent.

        Args:
            event_type (str): The type of the event (e.g., RouterEvent.FAILOVER).
            data (Any, optional): The primary data associated with the event. 
                Defaults to None.
            metadata (Optional[Dict[str, Any]], optional): Additional metadata 
                for the event. Defaults to None.
        """
        self.type = event_type
        self.data = data
        self.metadata = metadata or {}

def is_retryable_error(error: Exception) -> bool:
    """
    Determines if an error is a transient rate limit or a fatal resource exhaustion.

    Args:
        error (Exception): The exception to evaluate.

    Returns:
        bool: True if the error is considered transient and should be retried, 
            False if it is fatal (e.g., daily quota exceeded).
    """
    err_str = str(error).lower()
    
    # 1. Hard Limits (Fatal) -> Trigger Failover
    # Check for keywords indicating non-recoverable quota issues
    if "daily" in err_str or "bill" in err_str:
        return False
    
    # 2. Rate Limits (Retryable) -> Trigger Backoff
    # Google often says "Resource exhausted" for both RPM and Daily.
    # If it says "per minute" or "request limit", it's likely RPM.
    if "per minute" in err_str or "per_minute" in err_str or "rpm" in err_str:
        return True
        
    # If generic "quota" or "resource exhausted", and NOT daily/bill:
    # We treat it as retryable for a few attempts, but router handles max_retries.
    # The user complaint was premature failover. So let's err on side of Retry.
    if "resource exhausted" in err_str or "quota" in err_str:
        return True

    # Check for transient rate limits (RPM/TPM)
    if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
        return True
        
    # Check for transient server errors
    if any(code in err_str for code in ["500", "502", "503", "504", "overloaded", "server error"]):
        return True
        
    return False

class Router:
    """The central orchestration engine of Plexir that manages LLM providers, tool registries, 
    and failover logic with smart retries.

    The Router serves as the primary interface between the user's request and the 
    underlying Large Language Models (LLMs). Its core responsibility is to ensure 
    high availability and optimal performance by dynamically routing requests 
    across multiple providers, managing the context window via summarization 
    and pruning, and coordinating the execution of system tools.

    In the Plexir architecture, the Router acts as the 'brain' that handles:
    1. **Provider Management**: Selecting the best model for the task (e.g., 
       prioritizing "Pro" models for complex refactors).
    2. **Resilience**: Implementing exponential backoff for transient errors 
       (rate limits) and automatic failover to secondary providers for fatal errors.
    3. **Context Optimization**: Monitoring token usage and summarizing 
       conversation history to prevent context overflow.
    4. **Tool Orchestration**: Integrating a wide array of system tools (shell, 
       git, filesystem) and MCP (Model Context Protocol) servers.
    5. **Agentic Delegation**: Spawning specialized sub-agents for complex 
       multi-step objectives.

    Attributes:
        MAX_HISTORY_MESSAGES (int): The maximum number of messages to maintain 
            in the conversation history before triggering automatic summarization.
        registry (ToolRegistry): The central registry containing all available 
            tools accessible to the LLM.
        mcp_clients (List[MCPClient]): A list of active Model Context Protocol 
            (MCP) clients providing external tool capabilities.
        sandbox_enabled (bool): Indicates if the persistent Docker sandbox 
            is active for secure code and shell execution.
        mount_cwd (bool): Whether the current working directory is mounted 
            into the sandbox container.
        session_id (Optional[str]): A unique identifier for the current 
            session, used for session-persistent tools like the scratchpad.
        sandbox (Optional[PersistentSandbox]): The active sandbox instance 
            responsible for executing isolated commands.
        container_started (bool): A flag indicating whether the sandbox 
            container has been successfully initialized.
        providers (List[Provider]): A prioritized list of configured LLM 
            providers available for routing.
        active_provider_index (int): The index of the provider currently 
            being used for generation.
        session_usage (Dict[str, Any]): A dictionary tracking cumulative 
            token usage (prompt, completion, total) and total estimated cost.
        skill_manager (SkillManager): Manages project-specific knowledge, 
            skills, and the injection of custom system prompts.
    """
    MAX_HISTORY_MESSAGES = 100

    def __init__(self, sandbox_enabled: bool = False, mount_cwd: bool = False, session_id: Optional[str] = None):
        """
        Initializes the Router with tool registry, provider management, and sandbox settings.

        Args:
            sandbox_enabled (bool): Whether to enable the persistent Docker sandbox for executing 
                code and shell commands. Defaults to False.
            mount_cwd (bool): Whether to mount the current working directory into the sandbox 
                container. Defaults to False.
            session_id (Optional[str]): A unique identifier for the current session, used for 
                session-specific tools like the scratchpad. Defaults to None.
        """
        self.registry = ToolRegistry()
        self.mcp_clients: List[MCPClient] = []
        self.sandbox_enabled = sandbox_enabled
        self.mount_cwd = mount_cwd
        self.session_id = session_id
        self.sandbox = PersistentSandbox(mount_cwd=mount_cwd) if sandbox_enabled else None
        self.container_started = False
        self.load_base_tools()
        self.providers = []
        self.active_provider_index = 0
        self.session_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "last_context_tokens": 0
        }
        self.skill_manager = SkillManager(workspace_root=os.getcwd())


    def _calculate_cost(self, model: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> float:
        """
        Estimates the cost of an LLM request based on the model and token counts.

        Uses tiered pricing defined in the configuration manager to calculate the total
        cost for prompt and completion tokens.

        Args:
            model (str): The name of the model used for the request.
            prompt_tokens (Optional[int]): The number of prompt tokens. Defaults to 0 if None.
            completion_tokens (Optional[int]): The number of completion tokens. Defaults to 0 if None.

        Returns:
            float: The estimated total cost of the request in USD.
        """
        if prompt_tokens is None: prompt_tokens = 0
        if completion_tokens is None: completion_tokens = 0
        
        pricing_map = config_manager.config.pricing
        # pricing_map stores: model_name -> (prompt_rate_per_1M, completion_rate_per_1M)
        rates = pricing_map.get(model.lower(), (0.15, 0.60)) # Optimized default (e.g. Gemini 1.5 Flash)
        
        prompt_cost = (prompt_tokens / 1_000_000) * rates[0]
        completion_cost = (completion_tokens / 1_000_000) * rates[1]
        
        return prompt_cost + completion_cost

    def load_base_tools(self, whitelist: Optional[List[str]] = None, on_event: Optional[callable] = None):
        """
        Loads the standard suite of built-in tools into the tool registry.

        Args:
            whitelist (Optional[List[str]]): An optional list of tool names to include.
                If provided, only tools in this list will be registered. Defaults to None.
            on_event (Optional[callable]): Callback for real-time progress updates.
        """
        tools = [
            ReadFileTool(), WriteFileTool(), ListDirTool(), RunShellTool(),
            PythonSandboxTool(), GrepTool(), GitStatusTool(), EditFileTool(),
            GitDiffTool(), GitAddTool(), GitCommitTool(), GitCheckoutTool(), GitBranchTool(),
            GitPushTool(), GitPullTool(),
            GitHubCreateIssueTool(), GitHubCreatePRTool(),
            WebSearchTool(), BrowseURLTool(), CodebaseSearchTool(), GetDefinitionsTool(), GetRepoMapTool(),
            ScratchpadTool(session_id=self.session_id),
            ExportSandboxTool(), DelegateToAgentTool(router=self, on_event=on_event), SaveMemoryTool(), SearchMemoryTool()
        ]

        for tool in tools:
            if whitelist and tool.name not in whitelist:
                continue
            if self.sandbox:
                tool.sandbox = self.sandbox
            self.registry.register(tool)

    async def run_subagent(self, agent_name: str, objective: str, on_event: Optional[callable] = None) -> str:
        """
        Spawns a specialized sub-agent to perform a complex sub-task.

        The sub-agent is initialized with its own tool whitelist and system prompt based on 
        its role. It operates in its own execution loop until the objective is completed 
        or a maximum number of turns is reached.

        Args:
            agent_name (str): The name of the agent role to spawn (e.g., 'coder', 'researcher').
            objective (str): The detailed goal for the sub-agent to achieve.
            on_event (Optional[callable], optional): A callback function to handle events 
                (text chunks or RouterEvents) emitted by the sub-agent. Defaults to None.

        Returns:
            str: A formatted report containing the sub-agent's findings and final output.
        """
        role = get_agent_role(agent_name)
        if not role:
            return f"Error: Unknown agent role '{agent_name}'."

        if on_event:
            await on_event(RouterEvent(RouterEvent.SUBAGENT_START, data=agent_name))

        logger.info(f"Orchestrator: Spawning sub-agent '{agent_name}' for objective: {objective[:50]}...")

        # 1. Create a specialized sub-router
        sub_router = Router(
            sandbox_enabled=self.sandbox_enabled,
            mount_cwd=self.mount_cwd,
            session_id=f"{self.session_id}_{agent_name}"
        )
        sub_router.sandbox = self.sandbox
        sub_router.providers = self.providers
        sub_router.active_provider_index = self.active_provider_index

        # 2. Filter tools based on whitelist
        sub_router.registry = ToolRegistry()
        sub_router.load_base_tools(whitelist=role.tool_whitelist)

        # 3. Execution Loop
        sub_history = [{"role": "user", "content": f"OBJECTIVE: {objective}"}]
        max_turns = 15
        all_text_outputs = []

        for turn in range(max_turns):
            logger.debug(f"Sub-agent '{agent_name}' Turn {turn+1}")
            turn_content = ""
            current_tool_called = False

            async for chunk in sub_router.route(sub_history, system_instruction=role.system_prompt):
                if isinstance(chunk, str):
                    turn_content += chunk
                    if on_event:
                        await on_event(chunk)

                elif isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    current_tool_called = True
                    tool_name = chunk["name"]
                    args = chunk["args"]
                    tool_id = chunk.get("id", f"call_{int(time.time())}_{turn}")

                    if on_event:
                        # Signal the TUI that a tool is being called by the sub-agent
                        await on_event(chunk)

                    logger.info(f"Sub-agent '{agent_name}' executing tool: {tool_name}")
                    result = await sub_router.providers[sub_router.active_provider_index].execute_tool(tool_name, args)

                    if on_event:
                        # Signal the tool result
                        await on_event({"type": "tool_result", "name": tool_name, "result": result})

                    sub_history.append({
                        "role": "model", 
                        "parts": [{"function_call": {"name": tool_name, "args": args, "id": tool_id}}]
                    })
                    sub_history.append({
                        "role": "user", 
                        "parts": [{"function_response": {"name": tool_name, "response": {"result": result}, "id": tool_id}}]
                    })

                elif isinstance(chunk, RouterEvent):
                    if on_event:
                        await on_event(chunk)

            if turn_content:
                sub_history.append({"role": "model", "content": turn_content})
                all_text_outputs.append(turn_content)
                # If the sub-agent thinks it's done
                if any(word in turn_content.lower() for word in ["final report", "objective complete", "conclusion", "done"]):
                    break

            if not turn_content and not current_tool_called:
                break

        # Construct a meaningful report by combining all text outputs
        final_report = "\n\n".join(all_text_outputs)
        report_text = f"--- REPORT FROM {agent_name.upper()} ---\n{final_report or 'Objective attempted, but no text output was generated.'}\n-----------------------------"
        
        if on_event:
            await on_event(RouterEvent(RouterEvent.SUBAGENT_END, data=agent_name))
            
        return report_text
    async def reload_providers(self, on_event: Optional[callable] = None):
        """
        Re-initializes LLM providers and MCP clients based on the current configuration.

        This method ensures that the sandbox is started, disconnects existing MCP clients, 
        re-registers base tools, and loads providers in the order specified in the config.

        Args:
            on_event (Optional[callable], optional): A callback function for real-time 
                progress updates during the reload process. Defaults to None.
        """
        if self.sandbox and not self.container_started:
             await self.sandbox.start()
             self.container_started = True

        for client in self.mcp_clients:
            await client.disconnect() 
        self.mcp_clients.clear()

        self.registry = ToolRegistry() 
        self.load_base_tools(on_event=on_event)

        self.providers = []
        order = config_manager.config.active_provider_order
        
        for name in order:
            p_config = config_manager.get_provider_config(name)
            if not p_config: continue
            
            try:
                if p_config.type == "gemini":
                    self.providers.append(GeminiProvider(p_config, self.registry))
                elif p_config.type in ["openai", "groq", "ollama", "cerebras"]:
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

        The routing process includes:
        1. Budget checking.
        2. Automatic conversation summarization if history is too long.
        3. Complexity classification to prioritize "Pro" models for difficult tasks.
        4. Context window enforcement and pruning.
        5. Execution with exponential backoff for retryable errors.
        6. Failover to subsequent providers if the active one fails fatally.

        Args:
            history (List[Dict[str, Any]]): The conversation history as a list of messages.
            system_instruction (str, optional): Additional system instructions to prepend 
                to the default prompt. Defaults to "".

        Yields:
            Union[str, Dict[str, Any], RouterEvent]: Chunks of text, tool calls, or 
                RouterEvents (usage, thought, failover, etc.).

        Raises:
            RuntimeError: If all configured providers fail to generate a response.
        """
        # 0. Check budget
        budget = config_manager.config.session_budget
        if budget > 0 and self.session_usage["total_cost"] >= budget:
            yield f"\n[ERROR] Session budget exceeded (${self.session_usage['total_cost']:.2f} >= ${budget:.2f})."
            return

        # 1. Check for summarization (Token-aware)
        provider = self.providers[self.active_provider_index]
        limit = provider.config.context_limit or config_manager.config.model_context_windows.get(provider.model_name, 32000)
        
        # Trigger summarization at 80% of the limit or if message count is very high
        try:
            current_tokens = await provider.count_tokens(history, system_instruction)
        except Exception:
            from plexir.core.context import estimate_token_count
            current_tokens = estimate_token_count(history) + estimate_token_count(system_instruction)

        if current_tokens > (limit * 0.8) or len(history) > self.MAX_HISTORY_MESSAGES:
            yield RouterEvent(RouterEvent.SUMMARIZATION, data={
                "current_tokens": current_tokens,
                "limit": limit,
                "message_count": len(history)
            })
            await self.summarize_session(history, target_tokens=int(limit * 0.3))

        # 2. Complexity Classification (Smart Routing)
        is_complex = False
        if history:
            last_msg = history[-1].get("content", "").lower()
            # Simple heuristic for complexity; in production, this could be a small local model
            complex_keywords = ["refactor", "implement", "debug", "create", "architecture", "solve", "why", "how to"]
            if any(k in last_msg for k in complex_keywords) or len(last_msg) > 200:
                is_complex = True
            
            # If the last turn was a tool call, it's inherently part of a complex chain
            if "parts" in history[-1] and any("function_call" in p for p in history[-1]["parts"]):
                is_complex = True

        num_providers = len(self.providers)
        if num_providers == 0:
            yield "\n[System Error]: No LLM providers available."
            return

        # 3. Dynamic Re-ordering based on complexity
        if is_complex:
            # Move "Pro" models to the front if they aren't already
            # (Assuming model names with 'pro', 'sonnet', 'gpt-4' are Pro)
            pro_indices = [idx for idx, p in enumerate(self.providers) 
                           if any(k in p.model_name.lower() for k in ["pro", "sonnet", "gpt-4", "o1", "opus"])]
            if pro_indices and self.active_provider_index not in pro_indices:
                 yield RouterEvent(RouterEvent.SYSTEM, data=f"Complex task detected. Prioritizing Pro model: {self.providers[pro_indices[0]].name}")
                 self.active_provider_index = pro_indices[0]

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

        # 4. Inject Project Memory & Git Context
        current_system_prompt_base += self.skill_manager.get_system_injection()

        # 5. Extract episodic summary from history for system instruction
        episodic_summary = ""
        actual_history = []
        for msg in history:
            if msg.get("role") == "system" and "BACKGROUND SUMMARY" in msg.get("content", ""):
                episodic_summary = msg.get("content", "")
            else:
                actual_history.append(msg)
        
        if episodic_summary:
            current_system_prompt_base = f"# Episodic Summary\n{episodic_summary}\n\n{current_system_prompt_base}"

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

            # 2. Precise context enforcement using provider's token counter
            try:
                tokens = await provider.count_tokens(actual_history, turn_prompt)
                limit = provider.config.context_limit
                if limit is None:
                    limit = config_manager.config.model_context_windows.get(provider.model_name)
                
                if limit and tokens > (limit * 0.9):
                    yield RouterEvent("system", data=f"Context window for {provider.name} almost full ({tokens}/{limit}). Pruning...")
                    actual_history = context.enforce_context_limit(actual_history, limit, turn_prompt, current_tokens=tokens)
            except Exception as e:
                logger.warning(f"Token counting failed for {provider.name}: {e}")

            if i > 0:
                yield RouterEvent(RouterEvent.FAILOVER, data=provider.name)
                distilled = context.distill(actual_history)
                turn_prompt = f"{turn_prompt}\n\n[CONTEXT RESTORED]:\n{distilled}"

            # Inner loop: Retry transient errors
            max_retries = 10
            for attempt in range(max_retries + 1):
                try:
                    first_chunk = True
                    turn_usage_captured = False
                    
                    async for chunk in provider.generate(actual_history, turn_prompt):
                        if first_chunk:
                            self.active_provider_index = actual_index
                            first_chunk = False
                        
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get("type")
                            if chunk_type == "usage":
                                p_tokens = chunk.get("prompt_tokens") or 0
                                c_tokens = chunk.get("completion_tokens") or 0
                                t_tokens = chunk.get("total_tokens") or 0
                                
                                self.session_usage["last_context_tokens"] = p_tokens + c_tokens
                                
                                if not turn_usage_captured:
                                    self.session_usage["prompt_tokens"] += p_tokens
                                    self.session_usage["completion_tokens"] += c_tokens
                                    self.session_usage["total_tokens"] += t_tokens
                                    
                                    cost = self._calculate_cost(provider.model_name, p_tokens, c_tokens)
                                    self.session_usage["total_cost"] += cost
                                    turn_usage_captured = True
                                
                                chunk["total_cost_accumulated"] = self.session_usage["total_cost"]
                                chunk["last_context_tokens"] = self.session_usage["last_context_tokens"]
                                yield RouterEvent(RouterEvent.USAGE, data=chunk)
                            
                            elif chunk_type == "thought":
                                yield RouterEvent(RouterEvent.THOUGHT, data=chunk.get("content", ""))
                            
                            elif chunk_type == "tool_call":
                                yield chunk
                            
                            continue
                        
                        # Heuristic thought extraction for <think> blocks (DeepSeek, etc.)
                        if "<think>" in chunk:
                            # If it's a full block or a start tag
                            yield RouterEvent(RouterEvent.THOUGHT, data=chunk.replace("<think>", "").replace("</think>", ""))
                            continue

                        yield chunk
                    return # Success! 

                except Exception as e:
                    # Check if error has explicit retry delay
                    explicit_wait = 0.0
                    match = re.search(r"retry in (\d+(\.\d+)?)s", str(e).lower())
                    if match:
                        explicit_wait = float(match.group(1))

                    if is_retryable_error(e) and attempt < max_retries:
                        # Jittered Exponential backoff
                        base_wait = 2 ** attempt
                        calc_wait = min(60, base_wait + random.uniform(0, 3))
                        
                        # Use the larger of explicit wait or calculated wait
                        wait_time = max(explicit_wait, calc_wait)
                        
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
        """
        Resets the active provider index to the first configured provider.
        """
        self.active_provider_index = 0

    def get_tool(self, name: str):
        """
        Retrieves a tool instance from the registry by its name.

        Args:
            name (str): The name of the tool to retrieve.

        Returns:
            Optional[BaseTool]: The tool instance if found, otherwise None.
        """
        return self.registry.get(name)

    async def summarize_session(self, history: List[Dict[str, Any]], target_tokens: int = 4000):
        """
        Agentic Summarization: Uses the LLM to condense history while preserving state.
        """
        to_summarize, to_keep = context.get_messages_to_summarize(history)
        
        if not to_summarize:
            return

        # Structured Prompt for technical accuracy
        summary_prompt = f"""You are the Plexir Context Manager. 
Your goal is to distill the provided conversation history into a structured episodic memory block.

CRITICAL: 
1. DO NOT lose the original user instructions or current objective.
2. List all major technical findings and decisions made.
3. List the current status of all sub-tasks.
4. Keep the summary under {target_tokens} tokens.

STRUCTURE:
# CONTEXT SUMMARY
## MAIN OBJECTIVE: [Current user goal]
## FINDINGS: [List architectural or technical discoveries]
## COMPLETED ACTIONS: [List of tools/tasks finished]
## PENDING TASKS: [What needs to be done next]
"""
        # If the history to summarize is relatively small, pass raw text. 
        # Otherwise, use a light distillation to fit the summarizer's window.
        raw_to_summarize = str(to_summarize)
        if len(raw_to_summarize) > 50000: # 50k chars is a safe starting point
            raw_to_summarize = context.distill(to_summarize, max_chars=40000)

        provider = self.providers[self.active_provider_index]
        summary_text = ""
        
        try:
            # We use an empty history for the summarizer itself to keep its window clean
            async for chunk in provider.generate([], f"{summary_prompt}\n\n# HISTORY TO SUMMARIZE:\n{raw_to_summarize}"):
                if isinstance(chunk, str):
                    summary_text += chunk
            
            if summary_text:
                # Update history with the professional summary
                new_history = [
                    {
                        "role": "system", 
                        "content": f"BACKGROUND SUMMARY (Technical) of previous session:\n{summary_text.strip()}", 
                        "pinned": True
                    }
                ] + to_keep
                
                history.clear()
                history.extend(new_history)
                logger.info(f"LLM-based summarization complete. New history: {len(history)} messages.")

        except Exception as e:
            logger.error(f"LLM Summarization failed: {e}. Falling back to heuristic.")
            # Fallback to heuristic distillation if LLM fails
            fallback_summary = context.distill(to_summarize, max_chars=target_tokens * 4)
            history.clear()
            history.extend([
                {"role": "system", "content": f"BACKGROUND SUMMARY (Technical):\n{fallback_summary}", "pinned": True}
            ] + to_keep)
