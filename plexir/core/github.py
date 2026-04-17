"""
GitHub API Integration for Plexir.
Handles secure interaction with GitHub for Issues and PRs.
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from plexir.core.config_manager import config_manager

logger = logging.getLogger(__name__)

class GitHubClient:
    BASE_URL = "https://api.github.com"

    @staticmethod
    def _get_config() -> tuple[Optional[str], List[str]]:
        """Retrieves token and allowed_repos from config."""
        token = config_manager.get_tool_config("github", "token")
        allowed_str = config_manager.get_tool_config("github", "allowed_repos") or ""
        allowed_repos = [r.strip().lower() for r in allowed_str.split(",") if r.strip()]
        return token, allowed_repos

    @staticmethod
    def _validate_access(repo: str) -> Optional[str]:
        """Checks if the repo is in the allowed list."""
        token, allowed_repos = GitHubClient._get_config()
        if not token:
            return "Error: GitHub token not configured. Use `/config tool github token <YOUR_PAT>`."
        
        # Normalize repo name to owner/repo
        repo = repo.strip().lower()
        if repo not in allowed_repos:
            return (f"Error: Repository '{repo}' is not in the allowed list.\n"
                    f"Use `/config tool github allowed_repos {repo}` (comma-separated) to authorize.")
        return None

    @staticmethod
    def create_issue(repo: str, title: str, body: str, labels: List[str] = None) -> str:
        """Creates an issue in the specified repository."""
        error = GitHubClient._validate_access(repo)
        if error: return error
        
        token, _ = GitHubClient._get_config()
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{GitHubClient.BASE_URL}/repos/{repo}/issues"
        data = {
            "title": title,
            "body": body,
            "labels": labels or []
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 201:
                issue_data = response.json()
                return f"Issue created successfully: {issue_data.get('html_url')}"
            else:
                return f"Failed to create issue ({response.status_code}): {response.text}"
        except Exception as e:
            return f"Error connecting to GitHub: {e}"

    @staticmethod
    def create_pull_request(repo: str, title: str, body: str, head: str, base: str) -> str:
        """Creates a Pull Request."""
        error = GitHubClient._validate_access(repo)
        if error: return error
        
        token, _ = GitHubClient._get_config()
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{GitHubClient.BASE_URL}/repos/{repo}/pulls"
        data = {
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 201:
                pr_data = response.json()
                return f"PR created successfully: {pr_data.get('html_url')}"
            else:
                return f"Failed to create PR ({response.status_code}): {response.text}"
        except Exception as e:
            return f"Error connecting to GitHub: {e}"

    @staticmethod
    def generate_repo_map(root_path: str, max_depth: int = 3) -> str:
        """Generates a high-level map of the repository structure."""
        import os
        
        repo_map = [f"Repository Map (Root: {os.path.basename(root_path)})"]
        
        for root, dirs, files in os.walk(root_path):
            # Ignore common noise
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "venv", "__pycache__", "target", "build"]]
            
            level = root.replace(root_path, "").count(os.sep)
            if level >= max_depth:
                continue
                
            indent = "  " * level
            repo_map.append(f"{indent}📁 {os.path.basename(root)}/")
            
            sub_indent = "  " * (level + 1)
            # Only show high-signal files
            for f in files[:10]: # Limit files per dir
                if f.endswith((".py", ".ts", ".tsx", ".rs", ".go", ".c", ".cpp", ".h", ".md", ".json")):
                    repo_map.append(f"{sub_indent}📄 {f}")
            
            if len(files) > 10:
                repo_map.append(f"{sub_indent}... ({len(files) - 10} more files)")

        return "\n".join(repo_map)
