import pytest
import os
import shutil
from plexir.core.policy import PolicyManager, Decision
from plexir.core.agents import get_agent_role, SUB_AGENTS
from plexir.core.skills import SkillManager

@pytest.fixture
def policy_manager():
    return PolicyManager()

def test_policy_default_rules(policy_manager):
    # Test built-in forbidden rules
    decision, justification = policy_manager.evaluate(["sudo", "apt", "update"])
    assert decision == Decision.FORBIDDEN
    
    decision, justification = policy_manager.evaluate(["rm", "-rf", "/"])
    assert decision == Decision.FORBIDDEN

    # Test built-in prompt rules
    decision, justification = policy_manager.evaluate(["curl", "http://example.com"])
    assert decision == Decision.PROMPT

def test_policy_custom_rules(policy_manager):
    policy_manager.add_rule("git push", Decision.PROMPT, "Manual check for push")
    
    decision, _ = policy_manager.evaluate(["git", "push", "origin", "main"])
    assert decision == Decision.PROMPT
    
    decision, _ = policy_manager.evaluate(["git", "status"])
    assert decision == Decision.ALLOW # Default fallback

def test_policy_decomposition(policy_manager):
    # Test command chaining
    cmd = "ls -l && sudo rm -rf /"
    decision, justification, segment = policy_manager.decompose_and_evaluate(cmd)
    assert decision == Decision.FORBIDDEN
    assert "sudo rm -rf /" in segment

def test_agent_registry():
    coder = get_agent_role("coder")
    assert coder is not None
    assert "write_file" in coder.tool_whitelist
    
    investigator = get_agent_role("codebase_investigator")
    assert "get_repo_map" in investigator.tool_whitelist
    
    assert get_agent_role("non_existent") is None

@pytest.fixture
def workspace_setup(tmp_path):
    # Create mock memory files
    (tmp_path / "PLEXIR.md").write_text("Rule 1: Be helpful.")
    (tmp_path / "MEMO.md").write_text("Fact: The project name is Plexir.")
    return tmp_path

def test_skill_manager(workspace_setup):
    manager = SkillManager(workspace_root=str(workspace_setup))
    context = manager.load_project_context()
    
    assert "Rule 1: Be helpful." in context
    assert "Fact: The project name is Plexir." in context
    assert "PLEXIR.md" in context

def test_system_injection(workspace_setup):
    manager = SkillManager(workspace_root=str(workspace_setup))
    injection = manager.get_system_injection()
    
    assert "# Project Guidelines & Memory" in injection
    assert "Rule 1: Be helpful." in injection
