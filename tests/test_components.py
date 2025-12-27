import pytest
import asyncio
from plexir.core.context import distill
from plexir.config import settings
from plexir.core.router import Router, RouterEvent
from textual.app import App, ComposeResult
from plexir.ui.widgets import StatsPanel
from textual.widgets import Label

# --- Config Tests ---
def test_config_loading():
    """Verify settings are loaded correctly."""
    assert settings.APP_NAME == "Plexir"
    # API key might be None in CI, so we just check if it's reachable
    assert hasattr(settings, "GEMINI_API_KEY")

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
    """Test the router logic by mocking providers."""
    router = Router()
    
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
    
    # Check for FAILOVER event in the results
    assert any(isinstance(c, RouterEvent) and c.type == RouterEvent.FAILOVER for c in results)
    assert "Success" in results

# --- UI Logic Tests ---

class StatsPanelTestApp(App):
    def compose(self) -> ComposeResult:
        yield StatsPanel(id="stats-panel")

@pytest.mark.asyncio
async def test_statspanel_updates():
    """Verify StatsPanel reactive attributes update correctly."""
    app = StatsPanelTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one("#stats-panel", StatsPanel)
        panel.model_name = "Test Model"
        panel.status = "Busy"
        panel.latency = 1.23
        panel.sandbox_active = True
        
        await pilot.pause()
        
        assert str(app.query_one("#stat-model", Label).render()) == "Test Model"
        assert str(app.query_one("#stat-status", Label).render()) == "Busy"
        assert str(app.query_one("#stat-latency", Label).render()) == "1.23s"
        assert str(app.query_one("#stat-sandbox", Label).render()) == "ON"

def test_ui_imports():
    from plexir.ui.widgets import MessageBubble, StatsPanel, ToolStatus, ToolOutput
    assert MessageBubble is not None
    assert StatsPanel is not None
    assert ToolStatus is not None
    assert ToolOutput is not None