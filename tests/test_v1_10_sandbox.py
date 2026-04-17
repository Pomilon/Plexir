import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from plexir.tools.sandbox import PersistentSandbox

@pytest.fixture
def mock_docker_client():
    with patch("docker.from_env") as mock:
        client = mock.return_value
        client.ping.return_value = True
        yield client

@pytest.mark.asyncio
async def test_sandbox_state_siphon(mock_docker_client):
    sandbox = PersistentSandbox()
    sandbox.container = MagicMock()
    
    # Mock exec results for find and ps
    async def mock_exec(cmd):
        if "find" in cmd:
            return "/workspace/src/app.py\n/workspace/tests/test_new.py"
        if "ps" in cmd:
            return "PID COMM ARGS\n1 python3 app.py"
        return ""

    with patch.object(sandbox, "exec", side_effect=mock_exec):
        delta = await sandbox.get_state_delta()
        
        assert "changed_files" in delta
        assert "/workspace/src/app.py" in delta["changed_files"]
        assert "top_processes" in delta
        assert "python3 app.py" in delta["top_processes"]

@pytest.mark.asyncio
async def test_sandbox_stream_exec(mock_docker_client):
    sandbox = PersistentSandbox()
    sandbox.container = MagicMock()
    sandbox.container.id = "test-id"
    
    # Mock Docker API for exec
    mock_docker_client.api.exec_create.return_value = {"Id": "exec-123"}
    mock_docker_client.api.exec_start.return_value = [b"hello ", b"world"]
    
    chunks = []
    async for chunk in sandbox.stream_exec("echo 'hello world'"):
        chunks.append(chunk)
    
    assert chunks == ["hello ", "world"]
    mock_docker_client.api.exec_create.assert_called_once()
