
import asyncio
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.append(os.getcwd())

from plexir.tools.definitions import WebSearchTool, BrowseURLTool

@pytest.mark.asyncio
@patch("plexir.tools.definitions.config_manager.get_tool_config")
@patch("requests.get")
async def test_web_search_fallback(mock_get, mock_config):
    """Test WebSearchTool fallback (DuckDuckGo) with mocked response."""
    # Ensure Tavily/Serper are not "configured"
    mock_config.return_value = None
    
    # Mock DDG HTML response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = """
    <div class="result">
        <a class="result__a" href="https://python.org">Welcome to Python.org</a>
        <a class="result__url" href="https://python.org">python.org</a>
        <a class="result__snippet">Python is a programming language.</a>
    </div>
    """
    mock_get.return_value = mock_response

    search_tool = WebSearchTool()
    results = await search_tool.run("Python programming")
    assert "Python" in results
    assert "URL: https://python.org" in results

@pytest.mark.asyncio
@patch("requests.get")
async def test_browse_url_extraction(mock_get):
    """Test BrowseURLTool content extraction with mocked response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><h1>Python</h1><p>Python is an interpreted language.</p></body></html>"
    mock_get.return_value = mock_response

    browse_tool = BrowseURLTool()
    content = await browse_tool.run("https://example.com")
    assert "Python" in content
    assert "language" in content

if __name__ == "__main__":
    # Allow running manually
    async def run_manual():
        # Note: manual run won't have mocks unless we wrap it here too
        print("Run via pytest to use mocks.")
    
    asyncio.run(run_manual())
