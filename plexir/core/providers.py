"""
LLM provider implementations for Plexir.
Handles communication with Gemini and OpenAI-compatible APIs (Groq, Ollama, etc.).
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Union, Optional

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable
from groq import AsyncGroq
from openai import AsyncOpenAI

from plexir.tools.base import ToolRegistry
from plexir.core.config_manager import ProviderConfig

logger = logging.getLogger(__name__)

class LLMProvider(ABC):
    """Abstract base class for all LLM service providers."""
    
    def __init__(self, config: ProviderConfig, tools: ToolRegistry):
        self.config = config
        self.tools = tools
        self.name = config.name

    @abstractmethod
    async def generate(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """Generates a response from the LLM."""
        pass

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Executes a tool by name with the given arguments."""
        tool = self.tools.get(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found."
        try:
            return await tool.run(**args)
        except Exception as e:
            logger.error(f"Tool error ({tool_name}): {e}")
            return f"Tool execution failed: {e}"

class GeminiProvider(LLMProvider):
    """Provider for Google's Gemini API."""
    
    def __init__(self, config: ProviderConfig, tools: ToolRegistry):
        super().__init__(config, tools)
        self.model_name = config.model_name
        if config.api_key:
            genai.configure(api_key=config.api_key)

    async def generate(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        if not self.config.api_key:
            raise ValueError(f"API Key for {self.name} is missing.")

        gemini_history = []
        for msg in history:
            raw_role = msg.get("role", "user")
            
            # Map roles to Gemini's expected 'user' or 'model'
            if raw_role in ("assistant", "model"):
                role = "model"
            else:
                role = "user" # Map 'system', 'user', etc. to 'user'
            
            parts = []
            
            # Handle summary or system messages by prefixing content
            content_prefix = ""
            if raw_role == "system":
                content_prefix = "[SYSTEM CONTEXT]: "
            
            content = msg.get("content", "").strip()
            if content:
                parts.append({"text": content_prefix + content})
            
            if "parts" in msg:
                for p in msg["parts"]:
                    if "text" in p:
                        parts.append({"text": p["text"]})
                    elif "function_call" in p:
                        fc = p["function_call"]
                        parts.append({"function_call": {"name": fc["name"], "args": fc["args"]}})
                    elif "function_response" in p:
                        fr = p["function_response"]
                        # Gemini tool response MUST be a dict
                        res = fr["response"]
                        if not isinstance(res, dict):
                            res = {"result": res}
                        parts.append({"function_response": {"name": fr["name"], "response": res}})

            if not parts:
                continue

            # Ensure alternating roles or at least valid role transitions
            # Gemini is picky about 'function_response' being in a 'user' role message
            is_func_response = any("function_response" in p for p in parts)
            current_role = "user" if is_func_response else role
            
            gemini_history.append({
                "role": current_role,
                "parts": parts
            })
            
        if not gemini_history:
            gemini_history = [{"role": "user", "parts": [{"text": "Hello"}]}]

        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_instruction,
            tools=self.tools.to_gemini_toolbox()
        )

        try:
            response = await model.generate_content_async(
                contents=gemini_history, 
                stream=True
            )
            
            async for chunk in response:
                # Handle usage metadata
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    m = chunk.usage_metadata
                    yield {
                        "type": "usage",
                        "prompt_tokens": m.prompt_token_count,
                        "completion_tokens": m.candidates_token_count,
                        "total_tokens": m.total_token_count
                    }

                if not hasattr(chunk, 'candidates') or not chunk.candidates:
                    continue
                
                candidate = chunk.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            yield {
                                "type": "tool_call",
                                "name": fc.name,
                                "args": {k: v for k, v in fc.args.items()}
                            }
                            return
                        if hasattr(part, 'text') and part.text:
                            yield part.text
                
        except Exception as e:
            logger.error(f"Gemini error ({self.model_name}): {e}")
            raise e

class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI, Groq, Ollama, and other compatible APIs."""
    
    def __init__(self, config: ProviderConfig, tools: ToolRegistry):
        super().__init__(config, tools)
        self.model_name = config.model_name
        api_key = config.api_key or "MISSING_KEY"
        
        if config.type == "groq" and not config.base_url:
            self.client = AsyncGroq(api_key=api_key)
        else:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=config.base_url or "https://api.openai.com/v1"
            )

    async def generate(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        if not self.config.api_key and self.config.type != "ollama":
            raise ValueError(f"API Key for {self.name} is missing.")

        openai_history = []
        for msg in history:
            raw_role = msg.get("role", "user")
            role = "assistant" if raw_role == "model" else raw_role
            
            # OpenAI history shouldn't have 'system' role in the middle usually, 
            # but if it does, map to 'user' for safety with picky providers.
            if role == "system" and openai_history:
                role = "user"
                content = "[SYSTEM CONTEXT]: " + msg.get("content", "")
            else:
                content = msg.get("content", "")

            new_msg = {"role": role}
            if content.strip():
                new_msg["content"] = content.strip()
                
            if "parts" in msg:
                tool_calls = []
                for p in msg["parts"]:
                    if "function_call" in p:
                        fc = p["function_call"]
                        tool_calls.append({
                            "id": fc.get("id") or f"call_{len(openai_history)}_{int(time.time())}",
                            "type": "function",
                            "function": {"name": fc["name"], "arguments": json.dumps(fc["args"])}
                        })
                    elif "function_response" in p:
                        fr = p["function_response"]
                        # Extract the result more cleanly
                        res_obj = fr.get("response", {})
                        res_content = res_obj.get("result") if isinstance(res_obj, dict) else res_obj
                        if res_content is None: res_content = str(res_obj)

                        openai_history.append({
                            "role": "tool",
                            "tool_call_id": fr.get("id") or "call_default",
                            "name": fr["name"],
                            "content": json.dumps(res_content) if isinstance(res_content, (dict, list)) else str(res_content)
                        })
                
                if tool_calls:
                    new_msg["tool_calls"] = tool_calls
            
            if new_msg.get("content") or new_msg.get("tool_calls"):
                # Merge consecutive assistant messages
                if openai_history and openai_history[-1]["role"] == "assistant" and role == "assistant":
                    if new_msg.get("content"):
                        old_content = openai_history[-1].get("content", "")
                        openai_history[-1]["content"] = (old_content + "\n" + new_msg["content"]).strip()
                    if new_msg.get("tool_calls"):
                        old_tcs = openai_history[-1].get("tool_calls", [])
                        openai_history[-1]["tool_calls"] = old_tcs + new_msg["tool_calls"]
                else:
                    openai_history.append(new_msg)

        messages = [{"role": "system", "content": system_instruction}] + openai_history
        openai_tools = self.tools.to_openai_toolbox()

        try:
            stream = await self.client.chat.completions.create(
                messages=messages,
                model=self.model_name,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None,
                stream=True,
                stream_options={"include_usage": True}
            )
            
            tool_call_accumulator = {} 

            async for chunk in stream:
                # Handle usage metadata
                if hasattr(chunk, 'usage') and chunk.usage:
                    u = chunk.usage
                    yield {
                        "type": "usage",
                        "prompt_tokens": u.prompt_tokens,
                        "completion_tokens": u.completion_tokens,
                        "total_tokens": u.total_tokens
                    }

                if not hasattr(chunk, 'choices') or not chunk.choices:
                    continue
                
                choice = chunk.choices[0]
                delta = getattr(choice, 'delta', None)
                if not delta: continue
                
                if getattr(delta, 'content', None):
                    yield delta.content
                
                if getattr(delta, 'tool_calls', None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, 'index', 0)
                        if idx not in tool_call_accumulator:
                            tool_call_accumulator[idx] = {"name": "", "args": "", "id": ""}
                        
                        if tc.id:
                            tool_call_accumulator[idx]["id"] += tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_call_accumulator[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_accumulator[idx]["args"] += tc.function.arguments

                if getattr(choice, 'finish_reason', None) == "tool_calls":
                     for idx, data in tool_call_accumulator.items():
                        try:
                            yield {
                                "type": "tool_call",
                                "name": data["name"],
                                "args": json.loads(data["args"]) if data["args"] else {},
                                "id": data["id"] or f"call_{int(time.time())}_{idx}"
                            }
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse tool args: {data['args']}")
                     return
        except Exception as e:
            logger.error(f"OpenAI error ({self.model_name}): {e}")
            raise e