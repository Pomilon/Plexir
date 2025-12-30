
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from typing import List, Dict, Any, AsyncGenerator

from plexir.core.router import Router, RouterEvent, is_retryable_error
from plexir.core.config_manager import ConfigManager, AppConfig, ProviderConfig
from plexir.core.session import SessionManager
from plexir.tools.base import Tool
from pydantic import BaseModel

# --- Mocks ---

class MockProvider:
    def __init__(self, name, should_fail=False, fail_count=0, error_type="429"):
        self.name = name
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.current_fails = 0
        self.error_type = error_type
        self.model_name = "mock-model"

    async def generate(self, history, system_instruction) -> AsyncGenerator[Any, None]:
        if self.should_fail:
            raise Exception("Fatal Error")
        
        if self.current_fails < self.fail_count:
            self.current_fails += 1
            if self.error_type == "429":
                raise Exception("429 Too Many Requests")
            else:
                raise Exception("500 Internal Server Error")
        
        yield "Success"

# --- Router Tests ---

@pytest.mark.asyncio
async def test_router_retry_logic():
    """Test that router retries on transient errors."""
    router = Router()
    # Mock provider that fails 2 times with 429 then succeeds
    mock_provider = MockProvider("RetryProvider", fail_count=2, error_type="429")
    router.providers = [mock_provider]
    
    events = []
    response = ""
    async for chunk in router.route([], "sys"):
        if isinstance(chunk, RouterEvent):
            events.append(chunk)
        elif isinstance(chunk, str):
            response += chunk
            
    # Should see 2 retry events
    retry_events = [e for e in events if e.type == RouterEvent.RETRY]
    assert len(retry_events) == 2
    assert response == "Success"
    assert retry_events[0].data["attempt"] == 1
    assert retry_events[1].data["attempt"] == 2

@pytest.mark.asyncio
async def test_router_failover_logic():
    """Test that router fails over to the next provider on fatal/persistent errors."""
    router = Router()
    
    # P1 always fails (fatal)
    p1 = MockProvider("Primary", should_fail=True)
    # P2 succeeds
    p2 = MockProvider("Backup")
    
    router.providers = [p1, p2]
    
    events = []
    response = ""
    async for chunk in router.route([], "sys"):
        if isinstance(chunk, RouterEvent):
            events.append(chunk)
        elif isinstance(chunk, str):
            response += chunk
            
    # Should see failover event
    failover_events = [e for e in events if e.type == RouterEvent.FAILOVER]
    assert len(failover_events) == 1
    assert failover_events[0].data == "Backup"
    assert response == "Success"
    # Active provider should be updated
    assert router.active_provider_index == 1

@pytest.mark.asyncio
async def test_router_exhaustion():
    """Test behavior when ALL providers fail."""
    router = Router()
    p1 = MockProvider("P1", should_fail=True)
    p2 = MockProvider("P2", should_fail=True)
    router.providers = [p1, p2]
    
    with pytest.raises(RuntimeError, match="Failover exhausted"):
        async for chunk in router.route([], "sys"):
            pass

def test_is_retryable_error():
    """Verify error classification."""
    assert is_retryable_error(Exception("429 Too Many Requests")) is True
    assert is_retryable_error(Exception("503 Service Unavailable")) is True
    assert is_retryable_error(Exception("Quota exceeded")) is False
    assert is_retryable_error(Exception("Fatal error")) is False

# --- Async Core Tests ---

@pytest.mark.asyncio
async def test_config_save_async(tmp_path):
    """Test asynchronous config saving."""
    with patch("plexir.core.config_manager.CONFIG_FILE", str(tmp_path / "config.json")):
        cm = ConfigManager()
        cm.ensure_config_dir = MagicMock() # Prevent actual dir creation logic affecting test env
        
        # Modify config
        cm.config.theme = "test-theme"
        await cm.save_async()
        
        # Verify file content
        import json
        with open(str(tmp_path / "config.json"), "r") as f:
            data = json.load(f)
            assert data["theme"] == "test-theme"

@pytest.mark.asyncio
async def test_session_save_async(tmp_path):
    """Test asynchronous session saving."""
    with patch("plexir.core.session.SESSION_DIR", str(tmp_path)):
        sm = SessionManager()
        history = [{"role": "user", "content": "hello"}]
        
        result = await sm.save_session_async(history, "test_session")
        assert "saved as 'test_session'" in result
        
        import json
        with open(str(tmp_path / "test_session.json"), "r") as f:
            data = json.load(f)
            assert data == history

# --- Tool Robustness Tests ---

class SchemaModel(BaseModel):
    arg1: str

class NormalTool(Tool):
    name = "normal"
    description = "desc"
    args_schema = SchemaModel
    async def run(self, **kwargs): pass

class DynamicTool(Tool):
    name = "dynamic"
    description = "desc"
    args_schema = None
    args_schema_raw = {"properties": {"dyn_arg": {"type": "string"}}}
    async def run(self, **kwargs): pass

class BrokenTool(Tool):
    name = "broken"
    description = "desc"
    args_schema = None
    # No raw schema either
    async def run(self, **kwargs): pass

def test_tool_schema_generation():
    """Test schema generation for normal and dynamic tools."""
    
    # 1. Normal Tool
    t1 = NormalTool()
    gemini_schema = t1.to_gemini_schema
    openai_schema = t1.to_openai_schema
    
    assert gemini_schema["name"] == "normal"
    assert "arg1" in gemini_schema["parameters"]["properties"]
    assert openai_schema["function"]["parameters"]["properties"]["arg1"]["type"] == "string"

    # 2. Dynamic Tool (Fallback)
    t2 = DynamicTool()
    gemini_schema_dyn = t2.to_gemini_schema
    openai_schema_dyn = t2.to_openai_schema
    
    assert "dyn_arg" in gemini_schema_dyn["parameters"]["properties"]
    assert "dyn_arg" in openai_schema_dyn["function"]["parameters"]["properties"]

    # 3. Broken Tool (Graceful default)
    t3 = BrokenTool()
    gemini_schema_broken = t3.to_gemini_schema
    openai_schema_broken = t3.to_openai_schema
    
    assert gemini_schema_broken["parameters"]["properties"] == {}
    assert openai_schema_broken["function"]["parameters"]["properties"] == {}

