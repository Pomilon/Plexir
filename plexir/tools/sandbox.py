"""
Docker-based sandboxing for secure code execution.
Includes a one-off tool and a persistent "own computer" environment.
"""

import asyncio
import logging
import os
from typing import List, Optional
import docker
from docker.errors import ImageNotFound, ContainerError, APIError
from pydantic import BaseModel, Field
from plexir.tools.base import Tool

logger = logging.getLogger(__name__)

class SandboxRunSchema(BaseModel):
    """Schema for the python_sandbox tool."""
    code: str = Field(..., description="The Python code to execute.")

class PythonSandboxTool(Tool):
    """Executes Python code in an isolated Docker container."""
    name = "python_sandbox"
    description = "Executes Python code in a secure, isolated Docker container."
    args_schema = SandboxRunSchema

    def __init__(self):
        self.available = False
        try:
            self.client = docker.from_env()
            self.client.ping() 
            self.available = True
        except (APIError, Exception) as e:
            logger.warning(f"Docker initialization failed: {e}. Sandbox disabled.")

    async def run(self, code: str) -> str:
        """Runs the provided code either in the persistent sandbox or a new container."""
        if self.sandbox:
            safe_code = code.replace("'", "'\\''")
            return await self.sandbox.exec(f"python3 -c '{safe_code}'")

        if not self.available:
            return "Error: Docker is not available."

        container = None
        try:
            container = await asyncio.to_thread(
                self.client.containers.run,
                "python:3.10-slim",
                command=["python", "-c", code],
                detach=True,
                mem_limit="128m",
                cpu_quota=50000,
                network_mode="none"
            )
            
            result = await asyncio.to_thread(container.wait, timeout=10)
            logs = await asyncio.to_thread(container.logs)
            logs_str = logs.decode("utf-8")
            
            if result["StatusCode"] != 0:
                return f"Execution Failed (Exit Code {result['StatusCode']}):\n{logs_str}"
            
            return logs_str if logs_str else "(No output)"

        except ImageNotFound:
            return "Error: Docker image 'python:3.10-slim' not found."
        except ContainerError as e:
            return f"Error: Container execution failed: {e.stderr.decode('utf-8')}"
        except asyncio.TimeoutError:
            return "Error: Sandbox execution timed out."
        except Exception as e:
            logger.error(f"Sandbox error: {e}")
            return f"Error: {e}"
        finally:
            if container:
                try:
                    await asyncio.to_thread(container.remove, force=True)
                except Exception:
                    pass

class PersistentSandbox:
    """
    Manages a long-lived Docker container acting as a persistent Linux workspace.
    """
    CONTAINER_NAME = "plexir-persistent-sandbox"

    def __init__(self, image: str = "python:3.10-slim", mount_path: str = None):
        self.image = image
        self.mount_path = mount_path or os.getcwd()
        self.container = None
        self.client = None
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception:
            logger.error("Docker not available for PersistentSandbox.")

    async def start(self):
        """Starts the persistent sandbox container with volume mounts."""
        if not self.client:
            return
        try:
            # We enforce a fresh container start to ensure the current directory is mounted correctly.
            # "Persistent" here refers to persistence WITHIN the session/lifetime of the app, 
            # and potentially across restarts if we didn't force-recreate, but we need correct mounts.
            try:
                old = await asyncio.to_thread(self.client.containers.get, self.CONTAINER_NAME)
                if old.status == "running":
                    logger.info("Stopping existing sandbox to update mounts...")
                    await asyncio.to_thread(old.stop)
                await asyncio.to_thread(old.remove)
            except docker.errors.NotFound:
                pass
            
            logger.info(f"Creating sandbox: {self.CONTAINER_NAME} (Mounting {self.mount_path} -> /workspace)")
            
            self.container = await asyncio.to_thread(
                self.client.containers.run,
                self.image,
                command="sleep infinity",
                name=self.CONTAINER_NAME,
                detach=True,
                mem_limit="1024m",
                network_mode="bridge",
                volumes={self.mount_path: {'bind': '/workspace', 'mode': 'rw'}},
                working_dir="/workspace"
            )
            
            # Ensure git and basic tools are present
            # We check first to avoid apt-get update delay if image has them (unlikely for slim)
            git_check = await self.exec("git --version")
            if "not found" in git_check or "Error" in git_check:
                logger.info("Installing git/tools in sandbox...")
                # Install git and procps (for ps)
                await self.exec("apt-get update && apt-get install -y git procps")
            
        except Exception as e:
            logger.error(f"Sandbox start failed: {e}")

    async def exec(self, cmd: str) -> str:
        """Executes a command inside the persistent sandbox."""
        if not self.container:
            return "Error: Sandbox container not running."
        try:
            exec_res = await asyncio.to_thread(
                self.container.exec_run,
                ["/bin/sh", "-c", cmd],
                workdir="/workspace"
            )
            return exec_res.output.decode("utf-8")
        except Exception as e:
            logger.error(f"Sandbox exec error: {e}")
            return f"Error: {e}"

    async def stop(self):
        """Stops the persistent sandbox without removing it."""
        if self.container:
            try:
                await asyncio.to_thread(self.container.stop)
                logger.info("Persistent sandbox stopped.")
            except Exception:
                pass
            self.container = None