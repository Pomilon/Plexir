"""
Specialized Sub-Agent definitions for Plexir.
Defines roles, prompts, and tool whitelists for delegated tasks.
"""

from typing import List, Dict, Optional

class AgentRole:
    def __init__(self, name: str, description: str, system_prompt: str, tool_whitelist: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tool_whitelist = tool_whitelist # None means all tools

SUB_AGENTS = {
    "codebase_investigator": AgentRole(
        name="codebase_investigator",
        description="Specialist in analyzing codebase structure, finding symbols, and mapping dependencies.",
        system_prompt=(
            "You are a Codebase Investigator. Your goal is to map the project architecture and find specific implementation details.\n"
            "Use tools like `get_repo_map`, `codebase_search`, and `get_definitions` extensively.\n"
            "Provide a structured report of your findings. DO NOT perform any file edits unless strictly necessary for exploration."
        ),
        tool_whitelist=["get_repo_map", "codebase_search", "get_definitions", "read_file", "list_directory", "grep_search", "scratchpad"]
    ),
    "coder": AgentRole(
        name="coder",
        description="Specialist in implementing features, fixing bugs, and adding documentation.",
        system_prompt=(
            "You are a Coder Agent. Your goal is to write high-quality, maintainable code and documentation. "
            "Follow the project's coding style and ensure all changes are precise and correct. "
            "When adding docstrings, use Google style."
        ),
        tool_whitelist=["write_file", "edit_file", "read_file", "list_directory", "grep_search", "scratchpad"]
    ),
    "tester": AgentRole(
        name="tester",
        description="Specialist in creating and running tests to verify behavior or reproduce bugs.",
        system_prompt=(
            "You are a Quality Assurance Agent. Your goal is to ensure code correctness.\n"
            "Create test files, run them in the sandbox, and analyze failures.\n"
            "If a test fails, explain why and provide a reproduction script."
        ),
        tool_whitelist=["write_file", "run_shell", "python_sandbox", "read_file", "list_directory", "scratchpad"]
    ),
    "researcher": AgentRole(
        name="researcher",
        description="Specialist in web search and documentation analysis.",
        system_prompt=(
            "You are a Research Agent. Your goal is to find information from external sources.\n"
            "Use `web_search` and `browse_url` to find documentation, latest library versions, or solution patterns."
        ),
        tool_whitelist=["web_search", "browse_url", "scratchpad"]
    ),
    "reviewer": AgentRole(
        name="reviewer",
        description="Specialist in reviewing code changes for correctness, style, and documentation.",
        system_prompt=(
            "You are a Reviewer Agent. Your goal is to verify that code changes meet the requirements and maintain high quality. "
            "Check for bugs, style issues, and missing documentation. Provide a detailed report of your findings."
        ),
        tool_whitelist=["read_file", "list_directory", "grep_search", "scratchpad"]
    )
}

def get_agent_role(name: str) -> Optional[AgentRole]:
    return SUB_AGENTS.get(name.lower())
