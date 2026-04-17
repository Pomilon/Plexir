import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from plexir.core.router import Router, RouterEvent

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.name = "TestProvider"
    provider.model_name = "test-model-flash"
    provider.config = MagicMock()
    provider.config.context_limit = 10000
    
    async def mock_gen(*args, **kwargs):
        yield "Flash Response"
        
    provider.generate = mock_gen
    provider.count_tokens = AsyncMock(return_value=100)
    return provider

@pytest.fixture
def mock_pro_provider():
    provider = MagicMock()
    provider.name = "ProProvider"
    provider.model_name = "test-model-pro"
    provider.config = MagicMock()
    provider.config.context_limit = 100000
    
    async def mock_gen(*args, **kwargs):
        yield "Pro Response"
        
    provider.generate = mock_gen
    provider.count_tokens = AsyncMock(return_value=100)
    return provider

@pytest.mark.asyncio
async def test_router_failover(mock_provider, mock_pro_provider):
    router = Router()
    router.providers = [mock_provider, mock_pro_provider]
    
    # "Daily" keyword makes it fatal in is_retryable_error, triggering immediate failover
    async def failing_gen(*args, **kwargs):
        raise Exception("Daily quota exceeded")
        yield ""
        
    mock_provider.generate = failing_gen

    with patch("asyncio.sleep", AsyncMock()):
        events = []
        async for chunk in router.route([{"role": "user", "content": "hello"}]):
            events.append(chunk)

    # Check for failover event
    assert any(isinstance(e, RouterEvent) and e.type == RouterEvent.FAILOVER for e in events)
    assert "Pro Response" in events
    assert router.active_provider_index == 1

@pytest.mark.asyncio
async def test_router_complexity_classification(mock_provider, mock_pro_provider):
    router = Router()
    router.providers = [mock_provider, mock_pro_provider]
    
    # Complex query should trigger pro model prioritization
    history = [{"role": "user", "content": "Refactor this entire module for better performance"}]
    
    with patch("asyncio.sleep", AsyncMock()):
        # Run the generator
        events = []
        async for chunk in router.route(history):
            events.append(chunk)
    
    # The heuristic in router looks for "refactor" and should switch to index 1
    assert router.active_provider_index == 1
    # Should have a SYSTEM event about complexity
    assert any(isinstance(e, RouterEvent) and e.type == RouterEvent.SYSTEM and "Complex task" in str(e.data) for e in events)

@pytest.mark.asyncio
async def test_router_retry_logic(mock_provider):
    router = Router()
    router.providers = [mock_provider]
    
    # Provider fails with rate limit (429) twice then succeeds
    call_count = 0
    async def flaky_gen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("429 Rate Limit")
        yield "Success after retry"

    mock_provider.generate = flaky_gen

    with patch("asyncio.sleep", AsyncMock()):
        events = []
        async for chunk in router.route([{"role": "user", "content": "hello"}]):
            events.append(chunk)

    assert any(isinstance(e, RouterEvent) and e.type == RouterEvent.RETRY for e in events)
    assert "Success after retry" in events
    assert call_count == 3
