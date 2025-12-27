
import asyncio
import sys
import os
import pytest

# Add project root to sys.path
sys.path.append(os.getcwd())

from plexir.tools.definitions import WebSearchTool, BrowseURLTool

@pytest.mark.asyncio
async def test_web_search_fallback():
    """Test WebSearchTool fallback (DuckDuckGo)."""
    search_tool = WebSearchTool()
    results = await search_tool.run("Python programming")
    assert "Python" in results
    assert "URL:" in results

@pytest.mark.asyncio
async def test_browse_url_extraction():
    """Test BrowseURLTool content extraction."""
    browse_tool = BrowseURLTool()
    # Test with a known static page
    content = await browse_tool.run("https://www.python.org/about/")
    assert len(content) > 500
    assert "Python" in content

if __name__ == "__main__":
    # Allow running manually
    async def run_manual():
        await test_web_search_fallback()
        await test_browse_url_extraction()
        print("Manual tests passed!")
    
    asyncio.run(run_manual())
