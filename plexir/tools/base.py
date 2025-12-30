from abc import ABC, abstractmethod
from typing import Dict, Any, List, Type, Callable
from pydantic import BaseModel, Field

class Tool(ABC):
    """
    Abstract base class for all Plexir tools.
    Wraps functionality in a way that can be exposed to LLMs.
    """
    name: str
    description: str
    args_schema: Type[BaseModel]
    is_critical: bool = False
    sandbox: Any = None # Optional PersistentSandbox instance

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Execute the tool asynchronously."""
        pass

    @property
    def to_gemini_schema(self) -> Dict[str, Any]:
        """Converts the tool definition to Gemini's function declaration format."""
        schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": {},
                "required": []
            }
        }
        
        # Handle cases where args_schema is None (e.g., dynamic MCP tools)
        if hasattr(self, 'args_schema') and self.args_schema:
            model_schema = self.args_schema.model_json_schema()
        else:
            model_schema = getattr(self, 'args_schema_raw', {"properties": {}, "required": []})

        properties = model_schema.get("properties", {})
        required = model_schema.get("required", [])

        def map_type(json_type: str) -> str:
            if json_type == "integer": return "INTEGER"
            elif json_type == "number": return "NUMBER"
            elif json_type == "boolean": return "BOOLEAN"
            elif json_type == "array": return "ARRAY"
            elif json_type == "object": return "OBJECT"
            return "STRING"

        for prop, details in properties.items():
            # Map JSON schema types to Gemini types
            json_type = details.get("type", "string")
            gemini_type = map_type(json_type)
            
            prop_schema = {
                "type": gemini_type,
                "description": details.get("description", "")
            }

            if gemini_type == "ARRAY":
                items = details.get("items", {})
                item_type = items.get("type", "string")
                prop_schema["items"] = {
                    "type": map_type(item_type)
                }
            
            schema["parameters"]["properties"][prop] = prop_schema
            
        schema["parameters"]["required"] = required
        return schema

    @property
    def to_openai_schema(self) -> Dict[str, Any]:
        """Converts the tool definition to OpenAI/Groq function format."""
        if hasattr(self, 'args_schema') and self.args_schema:
            parameters = self.args_schema.model_json_schema()
        else:
            parameters = getattr(self, 'args_schema_raw', {"type": "object", "properties": {}})

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            }
        }

class ToolRegistry:
    """Registry to manage available tools."""
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())
    
    def to_gemini_toolbox(self) -> List[Dict[str, Any]]:
        return [t.to_gemini_schema for t in self._tools.values()]

    def to_openai_toolbox(self) -> List[Dict[str, Any]]:
        return [t.to_openai_schema for t in self._tools.values()]