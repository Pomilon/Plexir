"""
Skill and Memory manager for Plexir.
Loads PLEXIR.md, MEMO.md, and custom skills from the filesystem.
"""

import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class SkillManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.memory_files = ["PLEXIR.md", "ARCHITECTURE.md", "MEMO.md", "CLAUDE.md", "GEMINI.md"]
        self.project_context: str = ""

    def load_project_context(self) -> str:
        """Aggregates content from all known memory/guideline files."""
        context_parts = []
        
        for filename in self.memory_files:
            path = os.path.join(self.workspace_root, filename)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            context_parts.append(f"--- FILE: {filename} ---\n{content}")
                except Exception as e:
                    logger.warning(f"Failed to read memory file {filename}: {e}")
        
        self.project_context = "\n\n".join(context_parts)
        return self.project_context

    def get_git_snapshot(self) -> str:
        """Captures a brief snapshot of the current git state."""
        import subprocess
        try:
            # Check if it's a git repo
            if not os.path.exists(os.path.join(self.workspace_root, ".git")):
                return ""
                
            status = subprocess.check_output(
                ["git", "status", "--short"], 
                cwd=self.workspace_root, 
                text=True, 
                stderr=subprocess.STDOUT
            ).strip()
            
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], 
                cwd=self.workspace_root, 
                text=True, 
                stderr=subprocess.STDOUT
            ).strip()
            
            return f"Current Branch: {branch}\nGit Status:\n{status}" if status else f"Current Branch: {branch}\nGit Status: Clean"
        except Exception:
            return ""

    def get_system_injection(self) -> str:
        """Returns the full context to be injected into the system prompt."""
        context = self.load_project_context()
        git = self.get_git_snapshot()
        
        injection = ""
        if context:
            injection += f"\n# Project Guidelines & Memory\n{context}\n"
        if git:
            injection += f"\n# Current Git State\n{git}\n"
            
        return injection
