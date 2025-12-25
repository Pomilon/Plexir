"""
Standard tool implementations for Plexir.
Includes file system operations, shell execution, and git integration.
All tools support optional redirection to a persistent Docker sandbox.
"""

import asyncio
import logging
import os
import subprocess
from typing import List, Any
from pydantic import BaseModel, Field
from plexir.tools.base import Tool

logger = logging.getLogger(__name__)

# --- Schemas ---

class ReadFileSchema(BaseModel):
    file_path: str = Field(..., description="Path to the file to read.")

class WriteFileSchema(BaseModel):
    file_path: str = Field(..., description="Path to the file to write.")
    content: str = Field(..., description="Content to write to the file.")

class ListDirSchema(BaseModel):
    dir_path: str = Field(".", description="Directory path to list. Defaults to current directory.")

class RunShellSchema(BaseModel):
    command: str = Field(..., description="Shell command to execute.")

class GrepSchema(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for.")
    path: str = Field(".", description="Path to search in (file or directory).")
    recursive: bool = Field(True, description="Whether to search recursively.")

class EditFileSchema(BaseModel):
    file_path: str = Field(..., description="Path to the file to edit.")
    old_text: str = Field(..., description="The exact text to be replaced. MUST match exactly.")
    new_text: str = Field(..., description="The text to replace it with.")

class GitCommitSchema(BaseModel):
    message: str = Field(..., description="The commit message.")

class WebSearchSchema(BaseModel):
    query: str = Field(..., description="The search query.")

# --- File System Tools ---

class ReadFileTool(Tool):
    """Reads the content of a file."""
    name = "read_file"
    description = "Reads the content of a file from the local filesystem."
    args_schema = ReadFileSchema

    async def run(self, file_path: str) -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"cat '{file_path}'")
        try:
            return await asyncio.to_thread(self._sync_read_file, file_path)
        except Exception as e:
            return f"Error reading file '{file_path}': {e}"
    
    def _sync_read_file(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

class WriteFileTool(Tool):
    """Creates or overwrites a file with new content."""
    name = "write_file"
    description = "Writes content to a file. Overwrites if exists. CAUTION: Modifies filesystem."
    args_schema = WriteFileSchema
    is_critical = True

    async def run(self, file_path: str, content: str) -> str:
        if self.sandbox:
            safe_content = content.replace("'", "'\\''")
            dir_path = os.path.dirname(file_path)
            cmd = f"mkdir -p '{dir_path}' && printf '%s' '{safe_content}' > '{file_path}'"
            return await self.sandbox.exec(cmd) or f"Successfully wrote to {file_path} in sandbox."
        try:
            return await asyncio.to_thread(self._sync_write_file, file_path, content)
        except Exception as e:
            return f"Error writing file '{file_path}': {e}"

    def _sync_write_file(self, file_path: str, content: str) -> str:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"

class ListDirTool(Tool):
    """Lists files and directories in a path."""
    name = "list_directory"
    description = "Lists files and directories in the specified path."
    args_schema = ListDirSchema

    async def run(self, dir_path: str = ".") -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"ls -F '{dir_path}'")
        try:
            return await asyncio.to_thread(self._sync_list_dir, dir_path)
        except Exception as e:
            return f"Error listing directory '{dir_path}': {e}"

    def _sync_list_dir(self, dir_path: str) -> str:
        entries = os.listdir(dir_path)
        result = [f"{e}/" if os.path.isdir(os.path.join(dir_path, e)) else e for e in entries]
        return "\n".join(result)

class EditFileTool(Tool):
    """Performs precise text replacement in a file."""
    name = "edit_file"
    description = "Replaces a specific block of text in a file. Use for precise edits."
    args_schema = EditFileSchema
    is_critical = True

    async def run(self, file_path: str, old_text: str, new_text: str) -> str:
        if self.sandbox:
            py_code = f"""
import os
if not os.path.exists('{file_path}'): print('Error: File not found')
else:
    with open('{file_path}', 'r') as f: content = f.read()
    if '{old_text}' not in content: print('Error: old_text not found')
    else:
        with open('{file_path}', 'w') as f: f.write(content.replace('{old_text}', '{new_text}', 1))
        print('Successfully updated')
"""
            safe_py_code = py_code.replace("'", "'\\''")
            return await self.sandbox.exec(f"python3 -c '{safe_py_code}'")

        try:
            return await asyncio.to_thread(self._sync_edit_file, file_path, old_text, new_text)
        except Exception as e:
            return f"Error editing file: {e}"

    def _sync_edit_file(self, file_path: str, old_text: str, new_text: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if old_text not in content:
            return f"Error: 'old_text' not found in {file_path}. Match must be exact."
        new_content = content.replace(old_text, new_text, 1)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Successfully updated {file_path}."

# --- System Tools ---

class RunShellTool(Tool):
    """Executes a shell command."""
    name = "run_shell"
    description = "Executes a shell command on the host machine. CAUTION: Dangerous."
    args_schema = RunShellSchema
    is_critical = True

    async def run(self, command: str) -> str:
        if self.sandbox:
            return await self.sandbox.exec(command)
        try:
            return await asyncio.to_thread(self._sync_run_shell, command)
        except Exception as e:
            return f"Error executing shell command: {e}"

    def _sync_run_shell(self, command: str) -> str:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        return output

class GrepTool(Tool):
    """Searches for patterns in files."""
    name = "grep_search"
    description = "Searches for a text pattern in files using grep."
    args_schema = GrepSchema

    async def run(self, pattern: str, path: str = ".", recursive: bool = True) -> str:
        if self.sandbox:
            flags = "-rn" if recursive else "-n"
            return await self.sandbox.exec(f"grep {flags} '{pattern}' '{path}'")
        
        cmd = ["grep", "-rn" if recursive else "-n", pattern, path]
        try:
            return await asyncio.to_thread(self._sync_grep, cmd)
        except Exception as e:
            return f"Error during grep search: {e}"

    def _sync_grep(self, cmd: List[str]) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 1:
            return "No matches found."
        return result.stdout[:5000]

class WebSearchTool(Tool):
    """Performs a web search using DuckDuckGo."""
    name = "web_search"
    description = "Searches the web for information using DuckDuckGo and returns top results (title and URL)."
    args_schema = WebSearchSchema

    async def run(self, query: str) -> str:
        if self.sandbox:
            # In sandbox, use curl to fetch the DDG HTML page
            cmd = f"curl -s -L -H 'User-Agent: Mozilla/5.0' 'https://duckduckgo.com/html/?q={query}'"
            return await self.sandbox.exec(cmd)

        try:
            import requests
            from bs4 import BeautifulSoup
            
            def sync_search():
                search_url = f"https://duckduckgo.com/html/?q={query}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(search_url, headers=headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                results = []
                for result_div in soup.find_all("div", class_="result"):
                    title_tag = result_div.find("a", class_="result__a")
                    link_tag = result_div.find("a", class_="result__url")
                    if title_tag and link_tag:
                        results.append(f"Title: {title_tag.get_text(strip=True)}\nURL: {link_tag['href']}")
                    if len(results) >= 5:
                        break
                return "\n\n".join(results) if results else "No results found."

            return await asyncio.to_thread(sync_search)
        except Exception as e:
            return f"Search failed: {e}"

class BrowseURLSchema(BaseModel):
    url: str = Field(..., description="The URL to browse.")

class BrowseURLTool(Tool):
    """Fetches and extracts text content from a specific URL."""
    name = "browse_url"
    description = "Fetches the content of a specific web page and returns the extracted text."
    args_schema = BrowseURLSchema

    async def run(self, url: str) -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"curl -s -L '{url}'")

        try:
            import requests
            from bs4 import BeautifulSoup

            def sync_browse():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Extract text from common tags
                parts = [p.get_text(strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "li"])]
                text = "\n".join(p for p in parts if p)
                
                if not text:
                    return "No readable text content found."
                
                # Truncate to avoid context overflow
                return text[:8000]

            return await asyncio.to_thread(sync_browse)
        except Exception as e:
            return f"Failed to browse URL: {e}"

# --- Git Tools ---

class GitStatusTool(Tool):
    """Shows the current git status."""
    name = "git_status"
    description = "Shows the working tree status."
    args_schema = ListDirSchema

    async def run(self, dir_path: str = ".") -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"cd '{dir_path}' && git status")
        try:
            result = await asyncio.to_thread(subprocess.run, ["git", "status"], cwd=dir_path, capture_output=True, text=True)
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error during git status: {e}"

class GitDiffTool(Tool):
    """Shows git differences."""
    name = "git_diff"
    description = "Shows changes between commits, commit and working tree, etc."
    args_schema = ListDirSchema

    async def run(self, dir_path: str = ".") -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"cd '{dir_path}' && git diff")
        try:
            result = await asyncio.to_thread(subprocess.run, ["git", "diff"], cwd=dir_path, capture_output=True, text=True)
            return result.stdout or "No differences."
        except Exception as e:
            return f"Error during git diff: {e}"

class GitAddTool(Tool):
    """Adds files to the git index."""
    name = "git_add"
    description = "Adds file contents to the index."
    args_schema = ReadFileSchema
    is_critical = True

    async def run(self, file_path: str) -> str:
        if self.sandbox:
            return await self.sandbox.exec(f"git add '{file_path}'")
        try:
            await asyncio.to_thread(subprocess.run, ["git", "add", file_path], check=True)
            return f"Added {file_path} to index."
        except Exception as e:
            return f"Error during git add: {e}"

class GitCommitTool(Tool):
    """Commits changes to the git repository."""
    name = "git_commit"
    description = "Records changes to the repository."
    args_schema = GitCommitSchema
    is_critical = True

    async def run(self, message: str) -> str:
        if self.sandbox:
            safe_msg = message.replace("'", "'\\''")
            return await self.sandbox.exec(f"git commit -m '{safe_msg}'")
        try:
            await asyncio.to_thread(subprocess.run, ["git", "commit", "-m", message], check=True)
            return f"Committed with message: {message}"
        except Exception as e:
            return f"Error during git commit: {e}"
