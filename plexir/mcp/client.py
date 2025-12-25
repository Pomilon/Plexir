import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional
from subprocess import SubprocessError

from plexir.core.config_manager import config_manager, ProviderConfig
from plexir.tools.base import Tool, ToolRegistry
from pydantic import BaseModel, Field, ValidationError # Specific Pydantic exception

logger = logging.getLogger(__name__)

# Basic MCP tool schema for communication
class MCPToolRequest(BaseModel):
    tool_name: str
    args: Dict[str, Any]

class MCPToolResponse(BaseModel):
    result: str
    error: Optional[str] = None

class MCPClient:
    """
    A basic client for connecting to a Model Context Protocol (MCP) server.
    This version focuses on stdio communication for simplicity.
    """
    def __init__(self, config: ProviderConfig, tool_registry: ToolRegistry):
        self.config = config
        self.tool_registry = tool_registry
        self.process = None # To hold the subprocess
        self.running = False
        logger.info(f"MCP Client initialized for {config.name} ({config.base_url or 'stdio'}).")

    async def connect(self):
        """Establishes connection to the MCP server (e.g., starts subprocess)."""
        if not self.config.base_url or not self.config.base_url.startswith("stdio://"):
            logger.warning(f"MCP Client {self.config.name} has no stdio base_url. Not connecting.")
            return

        command_str = self.config.base_url[len("stdio://"):]
        logger.info(f"Connecting to MCP via stdio: {command_str}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command_str.split(), # Assumes command is space-separated
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.running = True
            asyncio.create_task(self._read_stderr()) # Start reading stderr in background
            logger.info(f"MCP Client {self.config.name} connected via stdio.")
            
            # Initial handshake: Request tools (MCP standard)
            await self._send_command({"command": "list_tools"})
            
        except FileNotFoundError:
            logger.error(f"MCP Client {self.config.name} failed: Command '{command_str.split()[0]}' not found.")
            self.running = False
        except SubprocessError as e:
            logger.error(f"MCP Client {self.config.name} subprocess error: {e}")
            self.running = False
        except Exception as e:
            logger.error(f"Unexpected error connecting MCP Client {self.config.name}: {e}")
            self.running = False

    async def _read_stderr(self):
        """Reads stderr from the subprocess and logs it."""
        while self.process.stderr and self.running:
            line = await self.process.stderr.readline()
            if not line: break
            logger.warning(f"MCP STDERR [{self.config.name}]: {line.decode().strip()}")

    async def _send_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sends a JSON command to the MCP server via stdin and waits for response."""
        if not self.running or not self.process.stdin or not self.process.stdout:
            logger.error(f"MCP Client {self.config.name} not running or pipes not available.")
            return None
        
        try:
            cmd_json = json.dumps(command) + "\n"
            self.process.stdin.write(cmd_json.encode())
            await self.process.stdin.drain()
            
            response_line = await self.process.stdout.readline()
            if not response_line:
                logger.warning(f"MCP Client {self.config.name} received empty response for {command.get('command')}.")
                return None
            
            response_data = json.loads(response_line.decode())
            
            if command.get("command") == "list_tools" and "tools" in response_data:
                self._register_mcp_tools(response_data["tools"])

            return response_data
            
        except json.JSONEncodeError as e:
            logger.error(f"Error encoding JSON command for MCP Client {self.config.name}: {e}")
            return {"error": f"Invalid command format: {e}"}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from MCP Client {self.config.name}: {e}")
            return {"error": f"Invalid response format: {e}"}
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"MCP Client {self.config.name} pipe error: {e}. Disconnected.")
            self.running = False
            return {"error": "MCP server disconnected."}
        except asyncio.IncompleteReadError as e:
            logger.error(f"MCP Client {self.config.name} incomplete read error: {e}. Possibly disconnected.")
            self.running = False
            return {"error": "MCP server disconnected unexpectedly."}
        except Exception as e:
            logger.error(f"Unexpected error communicating with MCP Client {self.config.name}: {e}")
            return {"error": f"An unexpected communication error occurred: {e}"}

    def _register_mcp_tools(self, tool_definitions: List[Dict[str, Any]]):
        """Registers tools defined by the MCP server into the global ToolRegistry."""
        for tool_def in tool_definitions:
            try:
                # Validate essential fields
                name = tool_def.get("name")
                description = tool_def.get("description", "MCP-provided tool.")
                schema = tool_def.get("schema")

                if not name or not schema:
                    raise ValueError(f"MCP tool definition missing 'name' or 'schema': {tool_def}")

                # Dynamically create a Tool class based on MCP definition
                def make_mcp_tool_instance(client_instance: 'MCPClient', tool_name: str, tool_description: str, tool_schema: Dict[str, Any]):
                    class GeneratedMCPTool(Tool):
                        name = tool_name
                        description = tool_description
                        args_schema = BaseModel.model_rebuild(__root__=tool_schema)
                        _mcp_client = client_instance # Store client reference
                        
                        async def run(self, **kwargs) -> Any:
                            response = await self._mcp_client._send_command({
                                "command": "execute_tool",
                                "tool_name": self.name,
                                "args": kwargs
                            })
                            if response and "error" in response:
                                raise RuntimeError(response["error"])
                            return response.get("result", "(no result)")
                    return GeneratedMCPTool()

                mcp_tool_instance = make_mcp_tool_instance(self, name, description, schema)
                self.tool_registry.register(mcp_tool_instance)
                logger.info(f"Registered MCP Tool: {name} from {self.config.name}")
            except ValidationError as e:
                logger.error(f"Pydantic validation error for MCP tool {tool_def.get('name', 'Unknown')}: {e}")
            except KeyError as e:
                logger.error(f"Missing key in MCP tool definition {tool_def.get('name', 'Unknown')}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error registering MCP tool {tool_def.get('name', 'Unknown')}: {e}")

    async def disconnect(self):
        """Disconnects the MCP server."""
        if self.running and self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                logger.warning(f"MCP Client {self.config.name} process already terminated.")
            except Exception as e:
                logger.error(f"Error terminating MCP Client {self.config.name} process: {e}")
            finally:
                self.running = False
                logger.info(f"MCP Client {self.config.name} disconnected.")
