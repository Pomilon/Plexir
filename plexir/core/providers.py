"""
LLM provider implementations for Plexir.
Handles communication with Gemini and OpenAI-compatible APIs (Groq, Ollama, etc.).
"""

import json
import logging
import time
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Union, Optional

from google import genai
from google.genai import types
import google.auth
from google.oauth2.credentials import Credentials
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable
from groq import AsyncGroq
from openai import AsyncOpenAI

from plexir.tools.base import ToolRegistry
from plexir.core.config_manager import ProviderConfig
from plexir.core.gemini_rest_client import GeminiOAuthClient

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
    """Provider for Google's Gemini API (using google-genai SDK or Custom OAuth Client)."""
    
    def __init__(self, config: ProviderConfig, tools: ToolRegistry):
        super().__init__(config, tools)
        self.model_name = config.model_name
        self.client = None
        self._configured = False
        
        mode = config.auth_mode
        
        # 1. API Key Mode (Standard SDK)
        if mode in ("api_key", "auto"):
            api_key = config.get_api_key()
            if api_key:
                try:
                    self.client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
                    self._configured = True
                    logger.info(f"GeminiProvider {self.name} initialized with API Key (SDK).")
                    return
                except Exception as e:
                    logger.warning(f"Gemini API Key init failed: {e}")

        # 2. Standalone OAuth (Custom REST Client)
        if mode in ("oauth", "auto"):
            standalone_creds = self._load_standalone_creds()
            if standalone_creds:
                try:
                    # Use custom REST client to bypass SDK restrictions on OAuth+AI Studio
                    self.client = GeminiOAuthClient(credentials=standalone_creds)
                    self._configured = True
                    logger.info(f"GeminiProvider {self.name} initialized with Custom REST Client (OAuth).")
                    return
                except Exception as e:
                    logger.warning(f"Gemini Custom OAuth init failed: {e}")

        # 3. ADC Fallback (Custom REST Client)
        if mode in ("oauth", "auto"):
            if mode == "auto" and self._configured: return
            try:
                creds, project = google.auth.default()
                self.client = GeminiOAuthClient(credentials=creds)
                self._configured = True
                logger.info(f"GeminiProvider {self.name} initialized with Custom REST Client (ADC).")
                return
            except Exception as e:
                logger.error(f"Gemini ADC init failed: {e}")

        if not self._configured:
            logger.error(f"GeminiProvider {self.name} failed to initialize. Check auth_mode.")

    def _load_standalone_creds(self) -> Optional[Credentials]:
        # ... (Reuse existing logic)
        paths = [
            os.path.expanduser("~/.plexir/oauth_creds.json"),
            os.path.expanduser("~/.gemini/oauth_creds.json") 
        ]
        client_secrets_path = os.path.expanduser("~/.plexir/client_secrets.json")
        client_info = self._load_client_info(client_secrets_path)

        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    if client_info:
                        if 'client_id' not in data: data['client_id'] = client_info.get('client_id')
                        if 'client_secret' not in data: data['client_secret'] = client_info.get('client_secret')
                        if 'token_uri' not in data: data['token_uri'] = client_info.get('token_uri', "https://oauth2.googleapis.com/token")
                    return Credentials.from_authorized_user_info(data)
                except Exception:
                    pass
        return None

    def _load_client_info(self, path: str) -> Optional[Dict[str, str]]:
        """Extracts client_id and client_secret from a client_secrets.json file."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if "installed" in data: return data["installed"]
            elif "web" in data: return data["web"]
            return None
        except Exception:
            return None

    async def generate(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        if not self.client:
            raise ValueError("Gemini Client not initialized.")

        # Map Tools
        tool_dicts = self.tools.to_gemini_toolbox()
        gemini_tools = [types.Tool(function_declarations=tool_dicts)] if tool_dicts else None
        
        # Prepare Config
        # enable_thought=True might be needed for 2.0/3.0 thinking models?
        # For now, let's stick to standard.
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            temperature=0.7 # Default
        )

        # Map History
        # We need to ensure history matches google.genai.types.Content structure
        # The dict structure is mostly compatible but 'function_response' key needs checking.
        # google-genai expects part keys: text, function_call, function_response, executable_code, code_execution_result
        
        contents = []
        for msg in history:
            role = msg.get("role", "user")
            parts = []
            
            raw_content = msg.get("content", "")
            if raw_content:
                parts.append(types.Part(text=raw_content))
            
            if "parts" in msg:
                for p in msg["parts"]:
                    if "text" in p:
                        parts.append(types.Part(text=p["text"]))
                    elif "thought" in p:
                        # Required for models that use thought signatures
                        parts.append(types.Part(thought=True, text=p["thought"]))
                    elif "function_call" in p:
                        fc = p["function_call"]
                        parts.append(types.Part(function_call=types.FunctionCall(name=fc["name"], args=fc["args"])))
                    elif "function_response" in p:
                        fr = p["function_response"]
                        # name, response (dict)
                        parts.append(types.Part(function_response=types.FunctionResponse(name=fr["name"], response=fr["response"])))
            
            if parts:
                contents.append(types.Content(role=role, parts=parts))
        
        if not contents:
            contents = [types.Content(role="user", parts=[types.Part(text="Hello")])]

        try:
            # Branch logic for Custom Client vs SDK
            if isinstance(self.client, GeminiOAuthClient):
                stream_generator = self.client.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )
            else:
                # SDK 1.0+ async usage
                stream_generator = await self.client.aio.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )

            async for chunk in stream_generator:
                # Handle Usage
                if chunk.usage_metadata:
                    yield {
                        "type": "usage",
                        "prompt_tokens": chunk.usage_metadata.prompt_token_count,
                        "completion_tokens": chunk.usage_metadata.candidates_token_count,
                        "total_tokens": chunk.usage_metadata.total_token_count
                    }

                if not chunk.candidates: continue
                candidate = chunk.candidates[0]
                
                if not candidate.content or not candidate.content.parts: continue
                
                for part in candidate.content.parts:
                    # Handle Thinking/Reasoning
                    if getattr(part, 'thought', None):
                        # Wrap in <think> tags for Plexir UI
                        yield f"<think>{part.text}</think>"
                    
                    if part.text and not getattr(part, 'thought', None):
                        yield part.text
                    
                    if part.function_call:
                        yield {
                            "type": "tool_call",
                            "name": part.function_call.name,
                            "args": part.function_call.args
                        }

        except Exception as e:
            logger.error(f"Gemini GenAI Error: {e}")
            raise e

class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI, Groq, Ollama, and other compatible APIs."""
    
    def __init__(self, config: ProviderConfig, tools: ToolRegistry):
        super().__init__(config, tools)
        self.model_name = config.model_name
        api_key = config.get_api_key() or "MISSING_KEY"
        
        base_url = config.base_url
        if config.type == "groq" and not base_url:
            self.client = AsyncGroq(api_key=api_key)
            return
        elif config.type == "cerebras" and not base_url:
            base_url = "https://api.cerebras.ai/v1"
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1"
        )

    async def generate(
        self, 
        history: List[Dict[str, Any]], 
        system_instruction: str = ""
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        if not self.config.get_api_key() and self.config.type != "ollama":
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
            create_params = {
                "messages": messages,
                "model": self.model_name,
                "tools": openai_tools if openai_tools else None,
                "tool_choice": "auto" if openai_tools else None,
                "stream": True,
            }
            
            # Only OpenAI (and possibly others) support stream_options for usage
            if self.config.type == "openai":
                create_params["stream_options"] = {"include_usage": True}

            stream = await self.client.chat.completions.create(**create_params)
            
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
            create_params = {
                "messages": messages,
                "model": self.model_name,
                "tools": openai_tools if openai_tools else None,
                "tool_choice": "auto" if openai_tools else None,
                "stream": True,
            }
            
            # Only OpenAI (and possibly others) support stream_options for usage
            if self.config.type == "openai":
                create_params["stream_options"] = {"include_usage": True}

            stream = await self.client.chat.completions.create(**create_params)
            
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