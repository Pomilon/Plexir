
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from plexir.core.router import Router, RouterEvent
from plexir.core.config_manager import config_manager
from plexir.core.context import get_messages_to_summarize

@pytest.mark.asyncio
async def test_token_tracking_and_cost():
    """Verify that Router correctly tracks tokens and calculates costs."""
    router = Router()
    # Mock a provider that yields usage data
    class MockUsageProvider:
        name = "MockUsage"
        model_name = "gemini-2.0-flash" # 0.10 input, 0.40 output per 1M
        async def generate(self, h, s):
            yield {
                "type": "usage",
                "prompt_tokens": 1000000,
                "completion_tokens": 1000000,
                "total_tokens": 2000000
            }
            yield "Done"

    router.providers = [MockUsageProvider()]
    
    events = []
    async for chunk in router.route([]):
        if isinstance(chunk, RouterEvent) and chunk.type == RouterEvent.USAGE:
            events.append(chunk)
            
    assert router.session_usage["prompt_tokens"] == 1000000
    assert router.session_usage["completion_tokens"] == 1000000
    # 1M prompt ($0.10) + 1M completion ($0.40) = $0.50
    assert router.session_usage["total_cost"] == 0.50
    assert len(events) == 1

@pytest.mark.asyncio
async def test_budget_enforcement():
    """Verify that the Router stops when the budget is exceeded."""
    router = Router()
    config_manager.config.session_budget = 0.10 # $0.10 budget
    router.session_usage["total_cost"] = 0.15 # Already exceeded
    
    chunks = []
    async for chunk in router.route([]):
        chunks.append(chunk)
        
    assert any("[ERROR] Session budget exceeded" in str(c) for c in chunks)

def test_pinning_logic():
    """Verify that pinned messages are preserved during summarization selection."""
    history = [
        {"role": "user", "content": "Keep me", "pinned": True}, # 0
        {"role": "user", "content": "Delete me", "pinned": False}, # 1
        {"role": "user", "content": "Delete me too", "pinned": False}, # 2
    ]
    # Simulate history long enough to trigger (logic keeps last 10, so we pad it)
    full_history = history + [{"role": "model", "content": f"msg {i}"} for i in range(15)]
    
    # We want to summarize the first 3
    to_summarize, to_keep = get_messages_to_summarize(full_history, 3)
    
    # The pinned message should NOT be in to_summarize
    assert not any(m.get("content") == "Keep me" for m in to_summarize)
    # The pinned message SHOULD be in to_keep
    assert any(m.get("content") == "Keep me" for m in to_keep)

@pytest.mark.asyncio
async def test_rolling_summarization_trigger():
    """Verify that Router triggers summarization when history is too long."""
    router = Router()
    router.MAX_HISTORY_MESSAGES = 5
    history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
    
    # Mock summarize_session to be an async function
    async def mock_summarize(h):
        return None

    with patch.object(router, 'summarize_session', wraps=mock_summarize) as mock_sum:
        # Mock provider with an async generator
        class MockProvider:
            name = "Test"
            model_name = "test"
            async def generate(self, h, s):
                yield "chunk"

        router.providers = [MockProvider()]
        
        async for _ in router.route(history):
            pass
            
        assert mock_sum.call_count == 1
