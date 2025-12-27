"""
Standard MCP (Model Context Protocol) Client for Plexir.
Implements JSON-RPC 2.0 communication over stdio.
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional, Union
from subprocess import SubprocessError

from plexir.core.config_manager import config_manager, ProviderConfig
from plexir.tools.base import Tool, ToolRegistry
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

class JSONRPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC Error {code}: {message} - {data}")

class MCPClient:
    """
    A robust JSON-RPC 2.0 client for the Model Context Protocol.
    Supports stdio transport, lifecycle management, tools, and resources.
    """
    def __init__(self, config: ProviderConfig, tool_registry: ToolRegistry):
        self.config = config
        self.tool_registry = tool_registry
        self.process = None
        self.running = False
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task = None
        self._stderr_task = None
        self.resources: List[Dict[str, Any]] = []
        self.resource_templates: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []
        logger.info(f"MCP Client initialized for {config.name}.")

    async def connect(self):
        """Establishes connection and performs MCP handshake."""
        if not self.config.base_url or not self.config.base_url.startswith("stdio://"):
            logger.warning(f"MCP Client {self.config.name}: Invalid/Missing stdio URL.")
            return

        command_str = self.config.base_url[len("stdio://"):]
        logger.info(f"Starting MCP server: {command_str}")
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command_str.split(), 
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.running = True
            self._read_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._read_stderr())
            
            # --- MCP Handshake ---
            # 1. Initialize
            logger.info(f"MCP {self.config.name}: Sending initialize...")
            init_result = await self.send_request("initialize", {
                "protocolVersion": "2024-11-05", 
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                    "logging": {}
                },
                "clientInfo": {"name": "Plexir", "version": "1.4.0"}
            })
            logger.info(f"MCP {self.config.name} Initialized. Server: {init_result.get('serverInfo', 'Unknown')}")
            
            # 2. Initialized Notification
            await self.send_notification("notifications/initialized")
            
            # 3. List Tools, Resources & Prompts
            await asyncio.gather(
                self.refresh_tools(),
                self.refresh_resources(),
                self.refresh_prompts()
            )
            
        except FileNotFoundError:
            logger.error(f"MCP Client {self.config.name} failed: Command not found.")
            await self.disconnect()
        except Exception as e:
            logger.error(f"MCP Connection failed: {e}")
            await self.disconnect()

    async def refresh_tools(self):
        """Fetches and registers tools from the server."""
        try:
            result = await self.send_request("tools/list")
            tools = result.get("tools", [])
            self._register_mcp_tools(tools)
            logger.info(f"MCP {self.config.name}: Registered {len(tools)} tools.")
        except Exception as e:
            logger.error(f"Failed to list tools for {self.config.name}: {e}")

    async def refresh_resources(self):
        """Fetches resources and templates from the server."""
        try:
            res_list = await self.send_request("resources/list")
            self.resources = res_list.get("resources", [])
            
            tmpl_list = await self.send_request("resources/templates/list")
            self.resource_templates = tmpl_list.get("resourceTemplates", [])

            if self.resources or self.resource_templates:
                self._register_resource_tool()
                logger.info(f"MCP {self.config.name}: Found {len(self.resources)} resources and {len(self.resource_templates)} templates.")
        except Exception as e:
            logger.debug(f"MCP {self.config.name} resources/list failed: {e}")

    async def refresh_prompts(self):
        """Fetches prompts from the server."""
        try:
            result = await self.send_request("prompts/list")
            self.prompts = result.get("prompts", [])
            if self.prompts:
                self._register_prompt_tool()
                logger.info(f"MCP {self.config.name}: Found {len(self.prompts)} prompts.")
        except Exception as e:
            logger.debug(f"MCP {self.config.name} prompts/list failed: {e}")

    def _register_resource_tool(self):
        """Registers a tool that allows the agent to list and read MCP resources."""
        client = self
        server_name = self.config.name

        class MCPResourceSchema(BaseModel):
            action: str = Field(..., description="Action: 'list' or 'read'")
            uri: Optional[str] = Field(None, description="The URI of the resource to read (required for 'read')")

        class MCPResourceTool(Tool):
            name = f"mcp_{server_name.lower().replace(' ', '_')}_resources"
            description = f"List or read resources (including templates) from the {server_name} MCP server."
            args_schema = MCPResourceSchema

            async def run(self, action: str, uri: Optional[str] = None) -> str:
                if action == "list":
                    await client.refresh_resources()
                    output = [f"Available Resources on {server_name}:"]
                    for res in client.resources:
                        output.append(f"- {res.get('name')} ({res.get('uri')}): {res.get('description', '')}")
                    
                    if client.resource_templates:
                        output.append("\nResource Templates:")
                        for t in client.resource_templates:
                            output.append(f"- {t.get('name')} ({t.get('uriTemplate')}): {t.get('description', '')}")
                    
                    return "\n".join(output) if len(output) > 1 else "No resources found."
                
                elif action == "read":
                    if not uri: return "Error: URI is required for 'read' action."
                    try:
                        res = await client.send_request("resources/read", {"uri": uri})
                        contents = res.get("contents", [])
                        output = []
                        for item in contents:
                            if "text" in item: output.append(item["text"])
                            elif "blob" in item: output.append(f"[Binary Content: {len(item['blob'])} bytes]")
                        return "\n\n".join(output) if output else "Resource is empty."
                    except Exception as e:
                        return f"Failed to read resource: {e}"
                return f"Unknown action: {action}"

        self.tool_registry.register(MCPResourceTool())

    def _register_prompt_tool(self):
        """Registers a tool that allows the agent to list and use MCP prompts."""
        client = self
        server_name = self.config.name

        class MCPPromptSchema(BaseModel):
            action: str = Field(..., description="Action: 'list' or 'get'")
            name: Optional[str] = Field(None, description="The name of the prompt (required for 'get')")
            arguments: Optional[Dict[str, str]] = Field(None, description="Arguments for the prompt (optional for 'get')")

        class MCPPromptTool(Tool):
            name = f"mcp_{server_name.lower().replace(' ', '_')}_prompts"
            description = f"List or retrieve prompt templates from the {server_name} MCP server."
            args_schema = MCPPromptSchema

            async def run(self, action: str, name: Optional[str] = None, arguments: Optional[Dict[str, str]] = None) -> str:
                if action == "list":
                    await client.refresh_prompts()
                    if not client.prompts: return "No prompts available."
                    output = [f"Available Prompts on {server_name}:"]
                    for p in client.prompts:
                        args_str = ", ".join([f"{a['name']}" for a in p.get("arguments", [])])
                        output.append(f"- {p.get('name')}: {p.get('description', '')} (Args: {args_str})")
                    return "\n".join(output)
                
                elif action == "get":
                    if not name: return "Error: Prompt name is required for 'get' action."
                    try:
                        res = await client.send_request("prompts/get", {"name": name, "arguments": arguments or {}})
                        description = res.get("description", "")
                        messages = res.get("messages", [])
                        output = [f"Prompt: {name}\n{description}\n"]
                        for msg in messages:
                            role = msg.get("role", "system")
                            content = msg.get("content", {})
                            if content.get("type") == "text":
                                output.append(f"[{role.upper()}]: {content.get('text')}")
                        return "\n".join(output)
                    except Exception as e:
                        return f"Failed to get prompt: {e}"
                return f"Unknown action: {action}"

        self.tool_registry.register(MCPPromptTool())

    async def send_request(self, method: str, params: Optional[Dict] = None) -> Any:
        """Sends a JSON-RPC request and waits for the result."""
        if not self.running:
            raise RuntimeError("MCP Client is not connected.")

        self._request_id += 1
        req_id = self._request_id
        future = asyncio.Future()
        self._pending_requests[req_id] = future
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id
        }
        
        await self._write_json(payload)
        
        # Simple timeout mechanism
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            del self._pending_requests[req_id]
            raise TimeoutError(f"MCP Request '{method}' timed out.")

    async def send_notification(self, method: str, params: Optional[Dict] = None):
        """Sends a JSON-RPC notification (no ID, no response expected)."""
        if not self.running: return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        await self._write_json(payload)

    async def _write_json(self, data: Dict):
        """Writes JSON payload to stdin."""
        try:
            json_str = json.dumps(data) + "\n"
            self.process.stdin.write(json_str.encode())
            await self.process.stdin.drain()
        except Exception as e:
            logger.error(f"Write error {self.config.name}: {e}")
            raise

    async def _read_loop(self):
        """Reads stdout, parses JSON-RPC messages, and resolves futures."""
        buffer = ""
        while self.running and self.process.stdout:
            try:
                line = await self.process.stdout.readline()
                if not line: break # EOF
                
                # Check for debug logs mixed in stdout (common in some servers)
                line_str = line.decode().strip()
                if not line_str: continue
                
                try:
                    message = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning(f"MCP {self.config.name} Non-JSON output: {line_str}")
                    continue

                if "id" in message:
                    # It's a response (or request from server, but we act as client)
                    req_id = message["id"]
                    if req_id in self._pending_requests:
                        future = self._pending_requests.pop(req_id)
                        if "error" in message:
                            err = message["error"]
                            future.set_exception(JSONRPCError(err.get("code"), err.get("message"), err.get("data")))
                        elif "result" in message:
                            future.set_result(message["result"])
                        else:
                            future.set_result(None) # Ack?
                else:
                    # Notification or request from server
                    method = message.get("method")
                    if method == "ping":
                        # Auto-reply to ping if server initiates (rare for stdio)
                        pass
                    # logger.debug(f"MCP Notification: {method}")

            except Exception as e:
                logger.error(f"Read loop error {self.config.name}: {e}")
                break
        
        logger.info(f"MCP {self.config.name} read loop ended.")
        await self.disconnect()

    async def _read_stderr(self):
        """Logs stderr from the server process."""
        while self.running and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line: break
            logger.warning(f"MCP STDERR [{self.config.name}]: {line.decode().strip()}")

    def _register_mcp_tools(self, tool_definitions: List[Dict[str, Any]]):
        """Dynamically creates Tool classes for MCP tools."""
        for tool_def in tool_definitions:
            try:
                name = tool_def.get("name")
                description = tool_def.get("description", "MCP Tool")
                input_schema = tool_def.get("inputSchema") # Standard MCP uses inputSchema, not schema

                if not name or not input_schema:
                    logger.warning(f"Skipping invalid MCP tool def: {tool_def}")
                    continue

                # Factory to capture closure
                def create_tool_class(t_name, t_desc, t_schema, client):
                    class DynamicMCPTool(Tool):
                        name = t_name
                        description = t_desc
                        # Reconstruct Pydantic model from JSON schema
                        try:
                            args_schema = BaseModel.model_rebuild(__root__=t_schema)
                        except:
                            # Fallback if complex schema: allow any dict
                            # Real implementation would need a dynamic model builder
                            # For now we skip validation if rebuild fails or use a generic Dict
                            class GenericSchema(BaseModel):
                                pass 
                            # We can't easily map arbitrary JSON Schema to Pydantic dynamically 
                            # without a heavy library like datamodel-code-generator.
                            # Strategy: Use a generic schema that accepts **kwargs but describe it in prompt.
                            args_schema = None 

                        async def run(self, **kwargs) -> str:
                            try:
                                res = await client.send_request("tools/call", {
                                    "name": self.name,
                                    "arguments": kwargs
                                })
                                # MCP result structure: { content: [{type: "text", text: "..."}] }
                                content = res.get("content", [])
                                text_output = []
                                for item in content:
                                    if item.get("type") == "text":
                                        text_output.append(item.get("text", ""))
                                    elif item.get("type") == "image":
                                        text_output.append("[Image returned]")
                                return "\n".join(text_output)
                            except Exception as e:
                                return f"MCP Tool Error: {e}"
                                
                    # Hack: since we can't easily build the Pydantic model dynamically, 
                    # we inject the raw schema into the tool so the Provider can use it directly
                    # for function calling definitions.
                    DynamicMCPTool.args_schema_raw = t_schema
                    return DynamicMCPTool()

                tool_instance = create_tool_class(name, description, input_schema, self)
                self.tool_registry.register(tool_instance)
                
            except Exception as e:
                logger.error(f"Error registering tool {tool_def.get('name')}: {e}")

    async def disconnect(self):
        """Cleanly shuts down the MCP connection."""
        if not self.running: return
        self.running = False
        
        # Cancel pending requests
        for future in self._pending_requests.values():
            future.cancel()
        self._pending_requests.clear()

        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
        logger.info(f"MCP Client {self.config.name} disconnected.")