
"""
Custom REST Client for Gemini AI Studio via OAuth.
Bypasses the SDK's restriction on using OAuth credentials with the AI Studio endpoint.
"""

import logging
import json
import httpx
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from typing import AsyncGenerator, Any, Dict, Optional

logger = logging.getLogger(__name__)

class GeminiRestResponseChunk:
    """Mimics the google.genai response chunk structure for compatibility."""
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.candidates = []
        self.usage_metadata = None
        
        # Parse Candidates
        if "candidates" in data:
            self.candidates = [Candidate(c) for c in data["candidates"]]
            
        # Parse Usage
        if "usageMetadata" in data:
            self.usage_metadata = UsageMetadata(data["usageMetadata"])

class Candidate:
    def __init__(self, data: Dict[str, Any]):
        self.content = Content(data.get("content", {}))
        self.finish_reason = data.get("finishReason")

class Content:
    def __init__(self, data: Dict[str, Any]):
        self.parts = [Part(p) for p in data.get("parts", [])]

class Part:
    def __init__(self, data: Dict[str, Any]):
        self.text = data.get("text")
        self.function_call = FunctionCall(data.get("functionCall")) if "functionCall" in data else None
        
        # Handle "thought" if present (experimental/future proofing)
        self.thought = data.get("thought", False) 

class FunctionCall:
    def __init__(self, data: Dict[str, Any]):
        self.name = data.get("name")
        self.args = data.get("args", {})

class UsageMetadata:
    def __init__(self, data: Dict[str, Any]):
        self.prompt_token_count = data.get("promptTokenCount", 0)
        self.candidates_token_count = data.get("candidatesTokenCount", 0)
        self.total_token_count = data.get("totalTokenCount", 0)

class GeminiOAuthClient:
    """
    A lightweight, async REST client for Gemini that supports OAuth User Credentials.
    """
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.request = google.auth.transport.requests.Request()

    async def _get_valid_token(self) -> str:
        """Ensures the token is valid, refreshing if necessary."""
        if self.credentials.expired:
            logger.info("OAuth token expired, refreshing...")
            self.credentials.refresh(self.request)
        return self.credentials.token

    async def generate_content_stream(
        self, 
        model: str, 
        contents: list, 
        config: Any = None
    ) -> AsyncGenerator[GeminiRestResponseChunk, None]:
        """
        Stream generation content via REST API.
        Mimics the signature of client.aio.models.generate_content_stream
        """
        token = await self._get_valid_token()
        
        # Construct URL
        model_id = model if model.startswith("models/") else f"models/{model}"
        url = f"{self.BASE_URL}/{model_id}:streamGenerateContent?alt=sse"

        # Construct Payload
        payload = {
            "contents": [self._serialize_content(c) for c in contents],
            "generationConfig": self._serialize_config(config) if config else {}
        }
        
        # Move Tools to top-level
        if config and hasattr(config, 'tools') and config.tools:
             payload["tools"] = [self._serialize_tool(t) for t in config.tools]

        # Move System Instruction to top-level
        if config and hasattr(config, 'system_instruction') and config.system_instruction:
             si = config.system_instruction
             if isinstance(si, str):
                 payload["systemInstruction"] = {"parts": [{"text": si}]}
             else:
                 payload["systemInstruction"] = self._serialize_content(si)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Gemini REST Error {response.status_code}: {error_text.decode('utf-8')}")
                    raise Exception(f"Gemini API Error {response.status_code}: {error_text.decode('utf-8')}")

                # Process SSE stream
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        json_str = line[5:].strip()
                        if not json_str: continue
                        try:
                            data = json.loads(json_str)
                            yield GeminiRestResponseChunk(data)
                        except json.JSONDecodeError:
                            continue

    def _serialize_content(self, content: Any) -> Dict:
        """Serializes google.genai.types.Content to dict."""
        # Simple serialization logic
        parts = []
        for part in content.parts:
            p_dict = {}
            if part.text: p_dict["text"] = part.text
            if getattr(part, 'thought', None): p_dict["thought"] = True # Handle thought if supported
            if part.function_call:
                p_dict["functionCall"] = {
                    "name": part.function_call.name,
                    "args": part.function_call.args
                }
            if part.function_response:
                p_dict["functionResponse"] = {
                    "name": part.function_response.name,
                    "response": part.function_response.response
                }
            parts.append(p_dict)
        
        return {"role": content.role, "parts": parts}

    def _dump_pydantic(self, obj: Any) -> Dict:
        """Dumps a Pydantic model to dict, using aliases (camelCase) if available."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json", by_alias=True, exclude_none=True)
        return obj

    def _serialize_tool(self, tool: Any) -> Dict:
        """Serializes Tool."""
        return self._dump_pydantic(tool)

    def _serialize_config(self, config: Any) -> Dict:
        """Serializes GenerationConfig."""
        d = self._dump_pydantic(config)
        
        # Clean up fields that belong at root
        keys_to_pop = ["system_instruction", "systemInstruction", "tools"]
        for k in keys_to_pop:
            if k in d: d.pop(k)

        # Fixup remaining config keys
        if "max_output_tokens" in d: d["maxOutputTokens"] = d.pop("max_output_tokens")
        if "stop_sequences" in d: d["stopSequences"] = d.pop("stop_sequences")
            
        return d
