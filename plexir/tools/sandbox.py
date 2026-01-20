"""
Docker-based sandboxing for secure code execution.
Includes a one-off tool and a persistent "own computer" environment.
"""

import asyncio
import logging
import os
import tarfile
import io
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
                network_mode="none",
                cap_drop=["ALL"],
                cap_add=["DAC_OVERRIDE"],
                security_opt=["no-new-privileges"],
                pids_limit=50
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
    Hardened for security.
    """
    CONTAINER_NAME = "plexir-persistent-sandbox"

    def __init__(self, image: str = "python:3.10-slim", mount_cwd: bool = False, source_path: str = None):
        self.image = image
        self.mount_cwd = mount_cwd
        self.source_path = source_path or os.getcwd()
        self.container = None
        self.client = None
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception:
            logger.error("Docker not available for PersistentSandbox.")

    async def start(self):
        """Starts the persistent sandbox container."""
        if not self.client:
            return
        try:
            try:
                old = await asyncio.to_thread(self.client.containers.get, self.CONTAINER_NAME)
                if old.status == "running":
                    logger.info("Stopping existing sandbox...")
                    await asyncio.to_thread(old.stop)
                await asyncio.to_thread(old.remove)
            except docker.errors.NotFound:
                pass
            
            volumes = {}
            if self.mount_cwd:
                logger.info(f"Mounting host {self.source_path} -> /workspace")
                volumes[self.source_path] = {'bind': '/workspace', 'mode': 'rw'}
            
            logger.info(f"Creating hardened sandbox: {self.CONTAINER_NAME}")
            
            # Security Hardening: Drop all, but add back essentials for file management
            self.container = await asyncio.to_thread(
                self.client.containers.run,
                self.image,
                command="sleep infinity",
                name=self.CONTAINER_NAME,
                detach=True,
                mem_limit="1024m",
                network_mode="bridge",
                volumes=volumes,
                working_dir="/workspace",
                cap_drop=["ALL"],
                cap_add=["DAC_OVERRIDE", "FOWNER", "CHOWN", "SETGID", "SETUID"],
                security_opt=["no-new-privileges"],
                pids_limit=100
            )
            
            # Clone mode: Copy files manually
            if not self.mount_cwd:
                logger.info("Cloning source directory into sandbox...")
                await self._copy_to_container(self.source_path, "/workspace")

            # Install basics
            await self.exec("apt-get update && apt-get install -y git procps tar")
            
        except Exception as e:
            logger.error(f"Sandbox start failed: {e}")

    async def _copy_to_container(self, src_path: str, dest_path: str):
        """Copies a local directory to the container using tar stream."""
        # Create tar in memory
        file_obj = io.BytesIO()
        with tarfile.open(fileobj=file_obj, mode='w') as tar:
            # Add files from src_path, arcname relative to root of tar
            # We want src contents to be inside /workspace. 
            # If we tar contents, we should extract to dest_path.
            tar.add(src_path, arcname=".")
        file_obj.seek(0)
        
        await asyncio.to_thread(
            self.container.put_archive,
            dest_path,
            file_obj
        )

    async def export_workspace(self, target_path: str):
        """Exports the container's /workspace to the host target path."""
        if not self.container: return
        
        logger.info(f"Exporting sandbox workspace to {target_path}...")
        try:
            # get_archive returns a tuple (stream, stat)
            stream, stat = await asyncio.to_thread(self.container.get_archive, "/workspace/.")
            
            file_obj = io.BytesIO()
            for chunk in stream:
                file_obj.write(chunk)
            file_obj.seek(0)
            
            os.makedirs(target_path, exist_ok=True)
            with tarfile.open(fileobj=file_obj, mode='r') as tar:
                tar.extractall(path=target_path)
            
            logger.info("Export complete.")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise e

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