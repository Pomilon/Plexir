import pytest
import asyncio
import os
from plexir.core.router import Router
from plexir.tools.sandbox import PersistentSandbox

@pytest.mark.asyncio
async def test_sandbox_file_persistence():
    """Verify that files written via tools in the sandbox persist and are readable."""
    # 1. Initialize Router with sandbox AND mount enabled
    router = Router(sandbox_enabled=True, mount_cwd=True)
    await router.sandbox.start()

    try:
        # ... rest of the test ...
        write_tool = router.get_tool("write_file")
        test_file = "sandbox_test.txt"
        test_content = "Hello Sandbox Integration"

        res = await write_tool.run(file_path=test_file, content=test_content)
        assert "Successfully wrote" in res or res == "" # exec_run output might be empty on success

        # 3. Verify file exists in sandbox via run_shell
        shell_tool = router.get_tool("run_shell")
        cat_res = await shell_tool.run(command=f"cat {test_file}")
        assert test_content in cat_res

        # 4. Verify file exists on host (since it's bind mounted)
        assert os.path.exists(test_file)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
        await router.sandbox.stop()

@pytest.mark.asyncio
async def test_sandbox_python_execution():
    """Verify python_sandbox runs in the persistent container."""
    router = Router(sandbox_enabled=True, mount_cwd=True)
    await router.sandbox.start()

    try:
        py_tool = router.get_tool("python_sandbox")
        # Write a file first to verify persistence in the same container
        await router.get_tool("run_shell").run(command="echo 'data' > shared.txt")

        code = "print(open('shared.txt').read().strip())"
        res = await py_tool.run(code=code)
        assert res.strip() == "data"

        if os.path.exists("shared.txt"):
            os.remove("shared.txt")
    finally:
        await router.sandbox.stop()
