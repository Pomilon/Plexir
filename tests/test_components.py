import pytest
import asyncio
from unittest.mock import MagicMock
from typing import List, Dict, Any, Union, Optional
from plexir.core.router import Router, RouterEvent
from plexir.core.context import distill

def test_distill():
    """Verify context distillation works."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "model", "content": "Hi there"}
    ]
    result = distill(history)
    # Match new format: [USER]: Hello
    assert "[USER]: Hello" in result
    assert "[MODEL]: Hi there" in result

@pytest.mark.asyncio
async def test_router_failover_logic():
    """Test the router logic by mocking providers."""
    router = Router()

    class MockProvider:
        def __init__(self, name):
            self.name = name
            self.model_name = "test-model"
            self.config = MagicMock()
            self.config.context_limit = 1000
        
        async def count_tokens(self, h, s):
            return 10
            
    class MockFailingProvider(MockProvider):
        async def generate(self, h, s):
            raise ValueError("Simulated Failure")
            yield "Should not reach here"

    class MockSuccessProvider(MockProvider):
        async def generate(self, h, s):
            yield "Success"

    router.providers = [MockFailingProvider("Fail"), MockSuccessProvider("Success")]

    results = []
    async for chunk in router.route([]):
        if isinstance(chunk, str):
            results.append(chunk)
    
    assert "Success" in results
