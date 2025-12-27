
import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from plexir.tools.definitions import WebSearchTool, BrowseURLTool

async def test_tools():
    print("--- Testing WebSearchTool (Fallback) ---")
    search_tool = WebSearchTool()
    results = await search_tool.run("Python programming")
    print(f"Results preview:\n{results[:200]}...")
    
    print("\n--- Testing BrowseURLTool (Extraction) ---")
    browse_tool = BrowseURLTool()
    # Test with a known static page
    content = await browse_tool.run("https://www.python.org/about/")
    print(f"Extracted content length: {len(content)}")
    print(f"Content preview:\n{content[:200]}...")

if __name__ == "__main__":
    asyncio.run(test_tools())
