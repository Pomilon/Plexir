import pytest
from plexir.core.context import distill
from plexir.config import settings
from plexir.core.router import GeminiProvider, Router, RouterEvent

# --- Config Tests ---
def test_config_loading():
    """Verify settings are loaded correctly."""
    assert settings.APP_NAME == "Plexir"
    assert settings.GEMINI_API_KEY is not None

# --- Context Tests ---
def test_distill():
    """Verify context distillation works."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "model", "content": "Hi there"}
    ]
    result = distill(history)
    assert "USER: Hello" in result
    assert "MODEL: Hi there" in result

# --- Router Tests ---
@pytest.mark.asyncio
async def test_router_failover_logic():
    """
    Test the router logic by mocking providers.
    We don't want to hit real APIs in unit tests generally, 
    but we verified the real API integration with verify_router.py.
    Here we test the routing logic itself.
    """
    router = Router()
    # Mock providers to force failover
    class MockFailingProvider:
        name = "MockFail"
        async def generate(self, h, s):
            raise ValueError("Simulated Failure")
            yield "Should not reach here"

    class MockSuccessProvider:
        name = "MockSuccess"
        async def generate(self, h, s):
            yield "Success"

    router.providers = [MockFailingProvider(), MockSuccessProvider()]
    
    results = []
    async for chunk in router.route([]):
        results.append(chunk)
    
    # We expect a Failover event then "Success"
    assert RouterEvent.FAILOVER in results
    assert "Success" in results

# --- UI Logic Tests ---
# We can't easily test TUI rendering, but we can test Widget logic if separated.
# For now, ensuring imports work is a good baseline.
def test_ui_imports():
    from plexir.ui.widgets import StreamLog, StatsPanel
    assert StreamLog is not None
    assert StatsPanel is not None
