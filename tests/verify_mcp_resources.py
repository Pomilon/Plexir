import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from plexir.mcp.client import MCPClient
from plexir.core.config_manager import MCPServerConfig
from plexir.tools.base import ToolRegistry

async def verify():
    registry = ToolRegistry()
    db_path = os.path.abspath("tests/test_mcp.db")
    
    # Configure the local mock MCP server
    config = MCPServerConfig(
        command="python3",
        args=[os.path.abspath('tests/mock_mcp_server.py')],
        env={}
    )
    
    client = MCPClient("MockServer", config, registry)
    print(f"Connecting to MCP server at {db_path}...")
    
    try:
        await client.connect()
        
        print("\n--- Listing Tools ---")
        tools = registry.list_tools()
        for t in tools:
            print(f"Tool found: {t.name}")
            
        print("\n--- Listing Resources ---")
        # Find our generated resource tool
        resource_tool = next((t for t in tools if "resources" in t.name), None)
        if resource_tool:
            list_res = await resource_tool.run(action="list")
            print(list_res)
            
            # Try to read a resource (the SQLite server provides URIs like 'sqlite://tests/test_mcp.db/schema')
            # The URI format depends on the server implementation. 
            # We'll parse the URI from the list result.
            import re
            match = re.search(r'\((mock://.*?)\)', list_res)
            if match:
                uri = match.group(1)
                print(f"\n--- Reading Resource: {uri} ---")
                content = await resource_tool.run(action="read", uri=uri)
                print(content)
            else:
                print(f"Could not find a valid URI in list results: {list_res}")
        else:
            print("Resource tool was not registered. (Is the server providing resources?)")
            
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(verify())
