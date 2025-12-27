import json
import sys
import asyncio

async def handle_request(req):
    method = req.get("method")
    req_id = req.get("id")
    
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "serverInfo": {"name": "MockServer", "version": "1.0.0"}
        }
    
    elif method == "tools/list":
        return {
            "tools": [
                {
                    "name": "echo_tool",
                    "description": "Echoes back the input",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}}
                    }
                }
            ]
        }
    
    elif method == "resources/list":
        return {
            "resources": [
                {
                    "uri": "mock://database/schema",
                    "name": "Mock Database Schema",
                    "description": "A fake database schema for testing.",
                    "mimeType": "text/x-sql"
                }
            ]
        }
    
    elif method == "resources/read":
        uri = req.get("params", {}).get("uri")
        if uri == "mock://database/schema":
            return {
                "contents": [
                    {
                        "uri": "mock://database/schema",
                        "mimeType": "text/x-sql",
                        "text": "CREATE TABLE users (id INT, name TEXT);"
                    }
                ]
            }
        return {"error": {"code": -32602, "message": "Invalid URI"}}

    return {"error": {"code": -32601, "message": "Method not found"}}

async def main():
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        
        try:
            req = json.loads(line)
            if "id" in req:
                # Request
                result = await handle_request(req)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req["id"]
                }
                if "error" in result:
                    resp["error"] = result["error"]
                else:
                    resp["result"] = result
                
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            else:
                # Notification
                pass
        except Exception as e:
            # sys.stderr.write(f"Error: {e}\n")
            pass

if __name__ == "__main__":
    asyncio.run(main())
