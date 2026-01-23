
import pytest
import shutil
import tempfile
import os
import asyncio
from unittest.mock import patch, MagicMock

from plexir.core.config_manager import ProviderConfig
from plexir.core.providers import OpenAICompatibleProvider
from plexir.tools.base import ToolRegistry
from plexir.tools.definitions import DelegateToAgentTool
# Import MemoryBank inside test functions or after patching to avoid side effects if possible,
# but since it's a module level import in definitions, we have to be careful.
from plexir.core import memory

# Mock ToolRegistry
class MockToolRegistry(ToolRegistry):
    def __init__(self):
        pass
    def to_openai_toolbox(self):
        return []

@pytest.mark.asyncio
async def test_cerebras_configuration():
    """Test that Cerebras provider type correctly sets the base URL."""
    print("\n--- Testing Cerebras Configuration ---")
    
    config = ProviderConfig(
        name="Cerebras Test",
        type="cerebras",
        model_name="llama3.1-8b",
        api_key="mock_key"
    )
    
    provider = OpenAICompatibleProvider(config, MockToolRegistry())
    
    # Check base_url (accessing inner client)
    # AsyncOpenAI client stores base_url in .base_url
    client_base_url = str(provider.client.base_url)
    
    print(f"Base URL: {client_base_url}")
    assert "https://api.cerebras.ai/v1" in client_base_url
    
    # Test Override
    config_custom = ProviderConfig(
        name="Cerebras Custom",
        type="cerebras",
        model_name="llama3.1-8b",
        api_key="mock_key",
        base_url="https://custom.cerebras.endpoint"
    )
    provider_custom = OpenAICompatibleProvider(config_custom, MockToolRegistry())
    assert "https://custom.cerebras.endpoint" in str(provider_custom.client.base_url)

@pytest.mark.asyncio
async def test_delegate_to_agent_tool():
    """Test the DelegateToAgent tool output."""
    print("\n--- Testing DelegateToAgent Tool ---")
    
    tool = DelegateToAgentTool()
    agent_name = "researcher"
    objective = "Find the latest papers on transformers."
    
    result = await tool.run(agent_name=agent_name, objective=objective)
    
    print(f"Result: {result}")
    assert "TASK DELEGATED TO RESEARCHER" in result
    assert objective in result

def test_memory_bank_integration():
    """Test MemoryBank persistence and search using a temp directory."""
    print("\n--- Testing MemoryBank Integration ---")
    
    # Create temp dir
    temp_dir = tempfile.mkdtemp()
    print(f"Temp Memory Dir: {temp_dir}")
    
    try:
        # Patch the MEMORY_DIR constant in the module
        with patch('plexir.core.memory.MEMORY_DIR', temp_dir):
            # Reset Singleton
            memory.MemoryBank._instance = None
            
            # Initialize Bank
            bank = memory.MemoryBank()
            
            if not bank.initialized:
                pytest.skip("MemoryBank failed to initialize (likely missing chromadb/torch deps in test env)")
            
            # 1. Add Memory
            fact = "The project code name is Project Chimera."
            res = bank.add(fact, metadata={"category": "secret"})
            print(f"Add Result: {res}")
            assert "ID:" in res
            
            # 2. Search Memory
            # We assume the embedding model works locally. If strict dependencies aren't met, this might fail.
            # But we added them to requirements.
            results = bank.search("What is the code name?")
            print(f"Search Results: {results}")
            
            assert len(results) > 0
            found_content = results[0]['content']
            assert "Project Chimera" in found_content
            
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        # Reset singleton again so subsequent tests don't use the deleted temp dir
        memory.MemoryBank._instance = None

if __name__ == "__main__":
    # Manually run if executed as script
    asyncio.run(test_cerebras_configuration())
    asyncio.run(test_delegate_to_agent_tool())
    test_memory_bank_integration()
