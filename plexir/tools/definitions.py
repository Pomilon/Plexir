"""
Standard tool implementations for Plexir.
Includes file system operations, shell execution, and git integration.
All tools support optional redirection to a persistent Docker sandbox.
"""

import asyncio
import logging
import os
import subprocess
import base64
import shlex
from typing import List, Any
from pydantic import BaseModel, Field
from plexir.tools.base import Tool
from plexir.core.rag import CodebaseRetriever
from plexir.core.config_manager import config_manager
from plexir.core.github import GitHubClient
from plexir.core.memory import MemoryBank

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
            mkdir_cmd = f"mkdir -p '{dir_path}' && " if dir_path else ""
            cmd = f"{mkdir_cmd}printf '%s' '{safe_content}' > '{file_path}'"
            return await self.sandbox.exec(cmd) or f"Successfully wrote to {file_path} in sandbox."
        try:
            return await asyncio.to_thread(self._sync_write_file, file_path, content)
        except Exception as e:
            return f"Error writing file '{file_path}': {e}"

    def _sync_write_file(self, file_path: str, content: str) -> str:
        if os.path.dirname(file_path):
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
    """Performs a web search using Tavily (primary) or DuckDuckGo (fallback)."""
    name = "web_search"
    description = "Searches the web for information and returns top results. Uses Tavily if API key is configured, otherwise falls back to DuckDuckGo."
    args_schema = WebSearchSchema

    async def run(self, query: str) -> str:
        # Check for Tavily API key in config
        tavily_key = config_manager.get_tool_config("web", "tavily_api_key")
        serper_key = config_manager.get_tool_config("web", "serper_api_key")

        if tavily_key:
            return await self._search_tavily(query, tavily_key)
        elif serper_key:
            return await self._search_serper(query, serper_key)
        
        # Fallback to DuckDuckGo (scraping)
        return await self._search_ddg_fallback(query)

    async def _search_tavily(self, query: str, api_key: str) -> str:
        import requests
        url = "https://api.tavily.com/search"
        data = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": True
        }
        try:
            # We run on host to use installed requests and api key
            response = await asyncio.to_thread(requests.post, url, json=data, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            
            output = []
            if res_json.get("answer"):
                output.append(f"💡 **Direct Answer:** {res_json['answer']}\n")
            
            results = res_json.get("results", [])
            for res in results:
                output.append(f"Title: {res['title']}\nURL: {res['url']}\nSnippet: {res.get('content', '')}")
            
            return "\n\n".join(output) if output else "No results found."
        except Exception as e:
            logger.warning(f"Tavily search failed, falling back: {e}")
            return await self._search_ddg_fallback(query)

    async def _search_serper(self, query: str, api_key: str) -> str:
        import requests
        url = "https://google.serper.dev/search"
        headers = {
            'X-API-KEY': api_key,
            'Content-Type': 'application/json'
        }
        data = {"q": query, "num": 5}
        try:
            response = await asyncio.to_thread(requests.post, url, headers=headers, json=data, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            
            output = []
            # Handle knowledge graph if present
            if "knowledgeGraph" in res_json:
                kg = res_json["knowledgeGraph"]
                output.append(f"💡 **Info:** {kg.get('title')} - {kg.get('description')}\n")

            for res in res_json.get("organic", []):
                output.append(f"Title: {res.get('title')}\nURL: {res.get('link')}\nSnippet: {res.get('snippet')}")
            
            return "\n\n".join(output) if output else "No results found."
        except Exception as e:
            logger.warning(f"Serper search failed, falling back: {e}")
            return await self._search_ddg_fallback(query)

    async def _search_ddg_fallback(self, query: str) -> str:
        """DuckDuckGo scraping fallback logic."""
        # If in sandbox, we could curl, but for structured results it's better to scrape on host
        # even if sandboxed, as web search is global.
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
                    snippet_tag = result_div.find("a", class_="result__snippet")
                    if title_tag and link_tag:
                        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                        results.append(f"Title: {title_tag.get_text(strip=True)}\nURL: {link_tag['href']}\nSnippet: {snippet}")
                    if len(results) >= 5:
                        break
                return "\n\n".join(results) if results else "No results found."

            return await asyncio.to_thread(sync_search)
        except Exception as e:
            return f"Search failed (all methods exhausted): {e}"

class BrowseURLSchema(BaseModel):
    url: str = Field(..., description="The URL to browse.")

class BrowseURLTool(Tool):
    """Fetches and extracts text content from a specific URL."""
    name = "browse_url"
    description = "Fetches the content of a web page and returns the extracted text. Support local URLs if in sandbox."
    args_schema = BrowseURLSchema

    async def run(self, url: str) -> str:
        # If in sandbox and URL is local (localhost/127.0.0.1), we must fetch FROM sandbox
        is_local = "localhost" in url or "127.0.0.1" in url or url.startswith("/")
        
        if self.sandbox and is_local:
            # Fetch HTML via curl in sandbox, then parse on host
            html = await self.sandbox.exec(f"curl -s -L '{url}'")
            if html.startswith("Error") or not html.strip():
                return f"Failed to fetch {url} from sandbox."
            return self._extract_text(html)

        try:
            import requests
            def sync_fetch():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                return response.text

            html = await asyncio.to_thread(sync_fetch)
            return self._extract_text(html)
        except Exception as e:
            return f"Failed to browse URL: {e}"

    def _extract_text(self, html: str) -> str:
        """Helper to extract clean text from HTML using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Remove scripts, styles, and nav elements
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            
            # Get text and clean whitespace
            text = soup.get_text(separator="\n")
            lines = (line.strip() for line in text.splitlines())
            # Drop blank lines and very short snippets
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if len(chunk) > 20)
            
            if not clean_text:
                return "No readable text content found."
            
            # Truncate to avoid context overflow (limit to ~4000 tokens / 12000 chars)
            return clean_text[:12000]
        except Exception as e:
            return f"Extraction failed: {e}"

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
            safe_msg = shlex.quote(message)
            return await self.sandbox.exec(f"git commit -m {safe_msg}")
        try:
            await asyncio.to_thread(subprocess.run, ["git", "commit", "-m", message], check=True)
            return f"Committed with message: {message}"
        except Exception as e:
            return f"Error during git commit: {e}"

class GitCheckoutSchema(BaseModel):
    target: str = Field(..., description="Branch name, tag, or commit hash to checkout.")
    create_new: bool = Field(False, description="If True, create a new branch (-b).")

class GitCheckoutTool(Tool):
    """Switch branches or restore working tree files."""
    name = "git_checkout"
    description = "Switch branches or restore working tree files."
    args_schema = GitCheckoutSchema
    is_critical = True

    async def run(self, target: str, create_new: bool = False) -> str:
        cmd_list = ["git", "checkout"]
        if create_new:
            cmd_list.append("-b")
        cmd_list.append(target)
        
        if self.sandbox:
            # Construct safe shell command
            cmd_str = " ".join(shlex.quote(arg) for arg in cmd_list)
            return await self.sandbox.exec(cmd_str)
        try:
            await asyncio.to_thread(subprocess.run, cmd_list, check=True, capture_output=True, text=True)
            return f"Checked out '{target}' (create_new={create_new})."
        except subprocess.CalledProcessError as e:
            return f"Error during git checkout: {e.stderr}"
        except Exception as e:
            return f"Unexpected error during git checkout: {e}"

class GitBranchSchema(BaseModel):
    action: str = Field(..., description="Action to perform: 'list', 'create', 'delete'.")
    branch_name: str = Field(None, description="Name of the branch (required for create/delete).")

class GitBranchTool(Tool):
    """List, create, or delete branches."""
    name = "git_branch"
    description = "Manage git branches."
    args_schema = GitBranchSchema

    async def run(self, action: str, branch_name: str = None) -> str:
        if action == "list":
            if self.sandbox:
                return await self.sandbox.exec("git branch -a")
            try:
                result = await asyncio.to_thread(subprocess.run, ["git", "branch", "-a"], capture_output=True, text=True)
                return result.stdout
            except Exception as e:
                return f"Error listing branches: {e}"
        
        elif action == "create":
            if not branch_name: return "Error: branch_name required for 'create'."
            if self.sandbox:
                return await self.sandbox.exec(f"git branch {shlex.quote(branch_name)}")
            try:
                await asyncio.to_thread(subprocess.run, ["git", "branch", branch_name], check=True)
                return f"Branch '{branch_name}' created."
            except Exception as e:
                return f"Error creating branch: {e}"
                
        elif action == "delete":
            if not branch_name: return "Error: branch_name required for 'delete'."
            if self.sandbox:
                return await self.sandbox.exec(f"git branch -D {shlex.quote(branch_name)}")
            try:
                await asyncio.to_thread(subprocess.run, ["git", "branch", "-D", branch_name], check=True)
                return f"Branch '{branch_name}' deleted."
            except Exception as e:
                return f"Error deleting branch: {e}"
        
        return f"Unknown action: {action}"

class CodebaseSearchSchema(BaseModel):
    query: str = Field(..., description="Natural language query or keywords to search for.")
    root_dir: str = Field(".", description="Root directory to search in.")

class CodebaseSearchTool(Tool):
    """Semantic-like search for code snippets."""
    name = "codebase_search"
    description = "Searches the codebase for relevant snippets using keywords from a query."
    args_schema = CodebaseSearchSchema

    async def run(self, query: str, root_dir: str = ".") -> str:
        if self.sandbox:
            # Simple fallback for sandbox: use grep directly since we can't easily inject the python logic
            keywords = query.split() # Naive split
            pattern = "|".join(keywords)
            return await self.sandbox.exec(f"grep -rnE '{pattern}' '{root_dir}' | head -n 20")

        try:
            return await asyncio.to_thread(CodebaseRetriever.search_codebase, query, root_dir)
        except Exception as e:
            return f"Error during search: {e}"

class GetDefinitionsSchema(BaseModel):
    file_path: str = Field(..., description="Path to the python file.")

class GetDefinitionsTool(Tool):
    """Extracts class and function definitions from a file."""
    name = "get_definitions"
    description = "Returns a summary of classes and functions in a Python file. Cheaper than read_file."
    args_schema = GetDefinitionsSchema

    async def run(self, file_path: str) -> str:
        if self.sandbox:
            # Use AST in sandbox via base64 encoded script to avoid quoting issues
            py_code = """
import ast
import sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    definitions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            definitions.append(f"Class: {node.name} (Methods: {', '.join(methods)})")
        elif isinstance(node, ast.FunctionDef):
            definitions.append(f"Function: {node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            definitions.append(f"Async Function: {node.name}")
    if not definitions:
        print("No classes or functions found.")
    else:
        print("\\n".join(definitions))
except Exception as e:
    print(f"Error parsing file: {e}")
"""
            b64_code = base64.b64encode(py_code.encode()).decode()
            # Decode and pipe to python3 -, passing file_path as argument
            cmd = f"echo {b64_code} | base64 -d | python3 - {shlex.quote(file_path)}"
            return await self.sandbox.exec(cmd)

        try:
            return await asyncio.to_thread(CodebaseRetriever.get_file_definitions, file_path)
        except Exception as e:
            return f"Error getting definitions: {e}"

class GetRepoMapSchema(BaseModel):
    root_dir: str = Field(".", description="Root directory to map.")
    max_depth: int = Field(3, description="Maximum depth to traverse.")

class GetRepoMapTool(Tool):
    """Generates a high-level map of the codebase structure."""
    name = "get_repo_map"
    description = "Generates a tree-like map of the codebase, including file names and key symbols (classes/functions) for Python files."
    args_schema = GetRepoMapSchema

    async def run(self, root_dir: str = ".", max_depth: int = 3) -> str:
        if self.sandbox:
            # Inject the full Python logic into the sandbox via base64
            # This avoids dependencies like 'tree' and gives us AST parsing inside the container
            py_script = r"""
import os
import ast
import sys

def generate_map(root_dir, max_depth):
    ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.env', '.venv', 'dist', 'build'}
    output = []
    
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        level = root.replace(root_dir, '').count(os.sep)
        if level > max_depth: continue
        
        indent = "  " * level
        output.append(f"{indent}{os.path.basename(root)}/")
        
        for file in files:
            if file.startswith('.'): continue
            file_path = os.path.join(root, file)
            output.append(f"{indent}  {file}")
            
            if file.endswith(".py"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                    symbols = []
                    for node in tree.body:
                        if isinstance(node, ast.ClassDef):
                            symbols.append(f"C:{node.name}")
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append(f"F:{node.name}")
                    if symbols:
                        symbol_str = ", ".join(symbols[:5])
                        if len(symbols) > 5: symbol_str += "..."
                        output.append(f"{indent}    └─ [{symbol_str}]")
                except:
                    pass
    print("\n".join(output))

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    generate_map(root, depth)
"""
            b64_code = base64.b64encode(py_script.encode("utf-8")).decode("utf-8")
            cmd = f"echo {b64_code} | base64 -d | python3 - '{root_dir}' {max_depth}"
            return await self.sandbox.exec(cmd)

        try:
            return await asyncio.to_thread(CodebaseRetriever.generate_repo_map, root_dir, max_depth)
        except Exception as e:
            return f"Error generating repo map: {e}"

class ScratchpadSchema(BaseModel):
    action: str = Field(..., description="Action: 'read', 'append', 'clear'.")
    content: str = Field(None, description="Content to append (required for 'append').")

class ScratchpadTool(Tool):
    """Persistent scratchpad for the agent to store plans and notes."""
    name = "scratchpad"
    description = "Use this to store plans, notes, or findings that you need to remember for later steps."
    args_schema = ScratchpadSchema

    def __init__(self):
        self.file_path = os.path.expanduser("~/.plexir/scratchpad.md")
    
    async def run(self, action: str, content: str = None) -> str:
        # Note: Scratchpad is always on the host, even if sandboxed, 
        # because it's the AGENT'S memory, not the project's.
        
        if action == "read":
            if not os.path.exists(self.file_path):
                return "(Scratchpad is empty)"
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading scratchpad: {e}"
        
        elif action == "append":
            if not content: return "Error: content required for append."
            try:
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(f"\n- {content}")
                return "Note appended to scratchpad."
            except Exception as e:
                return f"Error appending to scratchpad: {e}"
                
        elif action == "clear":
            try:
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                return "Scratchpad cleared."
            except Exception as e:
                return f"Error clearing scratchpad: {e}"
        
        return f"Unknown action: {action}"

class GitRemoteSchema(BaseModel):
    remote: str = Field("origin", description="Remote name (default: origin).")
    branch: str = Field(None, description="Branch name (default: current).")

class GitPushTool(Tool):
    """Pushes changes to a remote repository."""
    name = "git_push"
    description = "Push changes to remote. Uses configured token if available."
    args_schema = GitRemoteSchema
    is_critical = True

    async def run(self, remote: str = "origin", branch: str = None) -> str:
        cmd = ["git", "push", remote]
        if branch:
            cmd.append(branch)
            
        token = config_manager.get_tool_config("git", "token")
        if token:
            # Inject Basic Auth header for HTTPS remotes
            # Username: x-access-token (common for GitHub PATs), Password: token
            auth_str = f"x-access-token:{token}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            cmd.insert(1, "-c")
            cmd.insert(2, f"http.extraHeader=Authorization: Basic {b64_auth}")

        if self.sandbox:
             # Basic quoting for sandbox shell
             safe_cmd = " ".join(shlex.quote(c) for c in cmd)
             return await self.sandbox.exec(safe_cmd)

        try:
            # We don't print the command to logs to avoid leaking token
            res = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Push successful:\n{res.stdout}"
            return f"Push failed:\n{res.stderr}"
        except Exception as e:
            return f"Error pushing: {e}"

class GitPullTool(Tool):
    """Pulls changes from a remote repository."""
    name = "git_pull"
    description = "Pull changes from remote."
    args_schema = GitRemoteSchema

    async def run(self, remote: str = "origin", branch: str = None) -> str:
        cmd = ["git", "pull", remote]
        if branch:
            cmd.append(branch)
            
        token = config_manager.get_tool_config("git", "token")
        if token:
            auth_str = f"x-access-token:{token}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            cmd.insert(1, "-c")
            cmd.insert(2, f"http.extraHeader=Authorization: Basic {b64_auth}")

        if self.sandbox:
             safe_cmd = " ".join(shlex.quote(c) for c in cmd)
             return await self.sandbox.exec(safe_cmd)

        try:
            res = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Pull successful:\n{res.stdout}"
            return f"Pull failed:\n{res.stderr}"
        except Exception as e:
            return f"Error pulling: {e}"

class GitHubIssueSchema(BaseModel):
    repo: str = Field(..., description="Repository name in format 'owner/repo'.")
    title: str = Field(..., description="Issue title.")
    body: str = Field(..., description="Issue description.")
    labels: List[str] = Field(default=[], description="List of labels.")

class GitHubCreateIssueTool(Tool):
    """Creates a GitHub Issue."""
    name = "github_create_issue"
    description = "Creates an issue in a specified GitHub repository."
    args_schema = GitHubIssueSchema
    is_critical = True

    async def run(self, repo: str, title: str, body: str, labels: List[str] = None) -> str:
        # Run on host to use configured client
        return await asyncio.to_thread(GitHubClient.create_issue, repo, title, body, labels)

class GitHubPRSchema(BaseModel):
    repo: str = Field(..., description="Repository name 'owner/repo'.")
    title: str = Field(..., description="PR title.")
    body: str = Field(..., description="PR description.")
    head: str = Field(..., description="The branch with your changes.")
    base: str = Field("main", description="The branch to merge into.")

class GitHubCreatePRTool(Tool):
    """Creates a GitHub Pull Request."""
    name = "github_create_pr"
    description = "Creates a Pull Request in a specified GitHub repository."
    args_schema = GitHubPRSchema
    is_critical = True

    async def run(self, repo: str, title: str, body: str, head: str, base: str = "main") -> str:
        return await asyncio.to_thread(GitHubClient.create_pull_request, repo, title, body, head, base)

class ExportSandboxSchema(BaseModel):
    target_path: str = Field(..., description="Local path to export the sandbox workspace to.")

class ExportSandboxTool(Tool):
    """Exports the contents of the sandbox workspace to the host."""
    name = "export_sandbox"
    description = "Exports the entire /workspace from the sandbox to a local directory. Use this to save changes in Clone Mode."
    args_schema = ExportSandboxSchema
    is_critical = True

    async def run(self, target_path: str) -> str:
        if not self.sandbox:
            return "Error: No sandbox active."
        try:
            await self.sandbox.export_workspace(target_path)
            return f"Successfully exported workspace to {target_path}."
        except Exception as e:
            return f"Export failed: {e}"

class DelegateToAgentSchema(BaseModel):
    agent_name: str = Field(..., description="A descriptive name for the sub-agent (e.g., 'codebase_investigator').")
    objective: str = Field(..., description="The comprehensive and detailed goal for the sub-agent.")

class DelegateToAgentTool(Tool):
    """Formalizes the delegation of a complex sub-task to a specialized sub-agent."""
    name = "delegate_to_agent"
    description = "Delegates a complex sub-task to a specialized sub-agent. The sub-agent will work on the objective and return a structured report."
    args_schema = DelegateToAgentSchema

    async def run(self, agent_name: str, objective: str) -> str:
        # In this version, we simulate the delegation by logging it and returning a prompt for the user
        # In a future version, this could spawn a separate Router instance.
        logger.info(f"Delegating task to agent '{agent_name}': {objective}")
        return f"TASK DELEGATED TO {agent_name.upper()}\nObjective: {objective}\n\nPlease proceed with this sub-task and report back when finished."

class SaveMemorySchema(BaseModel):
    content: str = Field(..., description="The fact or information to remember.")
    category: str = Field("general", description="Optional category (e.g., 'preference', 'fact', 'code_pattern').")

class SaveMemoryTool(Tool):
    """Saves a piece of information to the long-term vector memory."""
    name = "save_memory"
    description = "Saves a fact, preference, or piece of information to long-term memory."
    args_schema = SaveMemorySchema

    async def run(self, content: str, category: str = "general") -> str:
        # MemoryBank is singleton
        bank = MemoryBank()
        return await asyncio.to_thread(bank.add, content, {"category": category})

class SearchMemorySchema(BaseModel):
    query: str = Field(..., description="The query to search for in memory.")

class SearchMemoryTool(Tool):
    """Searches the long-term vector memory."""
    name = "search_memory"
    description = "Semantic search over long-term memory to retrieve relevant facts or context."
    args_schema = SearchMemorySchema

    async def run(self, query: str) -> str:
        bank = MemoryBank()
        results = await asyncio.to_thread(bank.search, query)
        if not results:
            return "No relevant memories found."
        
        output = ["Found memories:"]
        for res in results:
            output.append(f"- [{res['score']:.2f}] {res['content']} (ID: {res['id']})")
        return "\n".join(output)
