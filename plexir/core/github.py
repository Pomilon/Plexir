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
    def list_issues(repo: str, state: str = "open") -> str:
        """Lists issues in a repo (useful for context)."""
        # Note: Listing might be allowed even if creating isn't? 
        # For safety, we restrict ALL interactions to allowed_repos.
        error = GitHubClient._validate_access(repo)
        if error: return error

        token, _ = GitHubClient._get_config()
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{GitHubClient.BASE_URL}/repos/{repo}/issues"
        params = {"state": state, "per_page": 10}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                issues = response.json()
                if not issues: return "No issues found."
                
                result = []
                for i in issues:
                    # Distinguish PRs from Issues (GitHub API mixes them)
                    type_str = "PR" if "pull_request" in i else "Issue"
                    result.append(f"#{i['number']} [{type_str}] {i['title']} ({i['state']})")
                return "\n".join(result)
            else:
                return f"Failed to list issues: {response.text}"
        except Exception as e:
            return f"Error connecting to GitHub: {e}"
