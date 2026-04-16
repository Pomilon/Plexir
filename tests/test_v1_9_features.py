import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from typing import List, Dict, Any

from plexir.core.config_manager import config_manager, ProviderConfig
from plexir.core.providers import GeminiProvider, OpenAICompatibleProvider
from plexir.core.router import Router
from plexir.core.context import estimate_token_count

@pytest.fixture
def mock_registry():
    registry = MagicMock()
    registry.list_tools.return_value = []
    registry.to_gemini_toolbox.return_value = []
    registry.to_openai_toolbox.return_value = []
    return registry

@pytest.mark.asyncio
async def test_reasoning_config_persistence():
    """Test that expanded_reasoning config can be toggled and persisted."""
    initial = config_manager.config.expanded_reasoning
    
    config_manager.update_app_setting("expanded_reasoning", not initial)
    assert config_manager.config.expanded_reasoning != initial
    
    # Revert
    config_manager.update_app_setting("expanded_reasoning", initial)
    assert config_manager.config.expanded_reasoning == initial

@pytest.mark.asyncio
async def test_gemini_token_counting():
    """Test Gemini native token counting (mocked)."""
    p_config = ProviderConfig(name="Gemini Test", type="gemini", model_name="gemini-1.5-pro")
    provider = GeminiProvider(p_config, MagicMock())
    
    # Mock SDK client
    mock_client = MagicMock()
    # Mock the async count_tokens call
    # res = await self.client.aio.models.count_tokens(...)
    mock_res = MagicMock()
    mock_res.total_tokens = 123

    # Setup the nested async mock

    provider.client = mock_client
    mock_client.aio.models.count_tokens = AsyncMock(return_value=mock_res)
    
    history = [{"role": "user", "content": "Hello world"}]
    tokens = await provider.count_tokens(history)
    
    assert tokens == 123
    mock_client.aio.models.count_tokens.assert_called_once()

@pytest.mark.asyncio
async def test_word_based_token_estimation():
    """Test the new 1.3 tokens/word heuristic."""
    text = "This is a test message with eight words."
    # 8 words * 1.3 = 10.4 -> 10 + 2 = 12
    expected = 12
    assert estimate_token_count(text) == expected

@pytest.mark.asyncio
async def test_openai_reasoning_parsing():
    """Test that OpenAI reasoning_content is wrapped in <think> tags."""
    p_config = ProviderConfig(name="DeepSeek Test", type="openai", model_name="deepseek-reasoner", api_key="test")
    provider = OpenAICompatibleProvider(p_config, MagicMock())
    
    # Mock the openai client stream
    mock_chunk = MagicMock()
    mock_delta = MagicMock()
    mock_delta.content = "Final answer"
    mock_delta.reasoning_content = "Thinking hard"
    mock_choice = MagicMock()
    mock_choice.delta = mock_delta
    mock_chunk.choices = [mock_choice]
    
    # Mock stream
    async def mock_stream():
        yield mock_chunk

    provider.client.chat.completions.create = AsyncMock(return_value=mock_stream())
    
    chunks = []
    async for chunk in provider.generate([]):
        chunks.append(chunk)
    
    assert "<think>Thinking hard</think>" in chunks
    assert "Final answer" in chunks

@pytest.mark.asyncio
async def test_router_context_enforcement():
    """Test that the router triggers pruning when context is near limit."""
    router = Router()
    
    mock_provider = AsyncMock()
    mock_provider.name = "TestProvider"
    mock_provider.model_name = "test-model"
    mock_provider.config = ProviderConfig(name="Test", type="openai", model_name="test-model", context_limit=100)
    
    # Return 95 tokens (near 100 limit)
    mock_provider.count_tokens.return_value = 95
    # Success on generate
    async def mock_gen(h, s):
        yield "OK"
    mock_provider.generate = mock_gen
    
    router.providers = [mock_provider]
    
    history = [{"role": "user", "content": "A" * 200}] # Long message
    
    with patch("plexir.core.context.enforce_context_limit") as mock_enforce:
        mock_enforce.return_value = [{"role": "user", "content": "pruned"}]
        
        results = []
        async for res in router.route(history):
            results.append(res)
            
        # Should have triggered pruning
        mock_enforce.assert_called_once()
        
        # Check for RouterEvent with system pruning message
        from plexir.core.router import RouterEvent
        has_pruning_msg = any(
            isinstance(r, RouterEvent) and "Pruning" in str(r.data) 
            for r in results
        )
        assert has_pruning_msg
