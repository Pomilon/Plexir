"""
Security policy engine for Plexir.
Implements hierarchical rules (Allow/Prompt/Forbidden) for shell commands.
Inspired by Codex's exec_policy.
"""

import os
import re
import logging
import shlex
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class Decision(Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"

class PolicyRule:
    def __init__(self, prefix: str, decision: Decision, justification: Optional[str] = None):
        self.prefix = prefix
        self.decision = decision
        self.justification = justification

class PolicyManager:
    def __init__(self):
        self.rules: List[PolicyRule] = []
        self._load_default_rules()
        self._load_local_rules()

    def _load_default_rules(self):
        """Loads hardcoded safety rules."""
        # Forbidden by default for safety
        self.rules.append(PolicyRule("sudo", Decision.FORBIDDEN, "Root escalation is blocked by default."))
        self.rules.append(PolicyRule("rm -rf /", Decision.FORBIDDEN, "Destructive root deletion is blocked."))
        
        # Prompt for potentially dangerous commands
        self.rules.append(PolicyRule("curl", Decision.PROMPT, "Network access requires approval."))
        self.rules.append(PolicyRule("wget", Decision.PROMPT, "Network access requires approval."))
        self.rules.append(PolicyRule("apt-get", Decision.PROMPT, "Package installation requires approval."))
        self.rules.append(PolicyRule("pip install", Decision.PROMPT, "Package installation requires approval."))

    def _load_local_rules(self):
        """Loads rules from .plexir/rules.txt in the current workspace."""
        rules_path = os.path.join(os.getcwd(), ".plexir", "rules.txt")
        if not os.path.exists(rules_path):
            return

        try:
            with open(rules_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        prefix = parts[0].strip()
                        decision_str = parts[1].strip().lower()
                        justification = parts[2].strip() if len(parts) > 2 else None
                        
                        try:
                            decision = Decision(decision_str)
                            self.rules.append(PolicyRule(prefix, decision, justification))
                        except ValueError:
                            logger.warning(f"Invalid decision in rules: {decision_str}")
        except Exception as e:
            logger.error(f"Failed to load local rules: {e}")

    def evaluate(self, command_parts: List[str]) -> (Decision, Optional[str]):
        """Evaluates a command against the active policies."""
        full_cmd = " ".join(command_parts)
        
        # Sort rules by prefix length (descending) to match the most specific rule first
        sorted_rules = sorted(self.rules, key=lambda r: len(r.prefix), reverse=True)
        
        for rule in sorted_rules:
            if full_cmd.startswith(rule.prefix):
                return rule.decision, rule.justification
        
        # Default policy: ALLOW (assuming sandbox is provideing primary protection)
        return Decision.ALLOW, None

    def decompose_and_evaluate(self, command: str) -> (Decision, Optional[str], Optional[str]):
        """Splits complex commands (&&, ||, ;) and evaluates each segment."""
        # This is a basic implementation of shell decomposition
        segments = re.split(r' && | \|\| | ; ', command)
        
        for segment in segments:
            parts = shlex.split(segment.strip())
            if not parts:
                continue
            
            decision, justification = self.evaluate(parts)
            if decision != Decision.ALLOW:
                return decision, justification, segment
        
        return Decision.ALLOW, None, None

    def add_rule(self, prefix: str, decision: Decision, justification: Optional[str] = None):
        """Adds a new rule to the manager."""
        self.rules.append(PolicyRule(prefix, decision, justification))

    def persist_rules(self):
        """Persists custom rules to .plexir/rules.txt in the current workspace."""
        rules_dir = os.path.join(os.getcwd(), ".plexir")
        os.makedirs(rules_dir, exist_ok=True)
        rules_path = os.path.join(rules_dir, "rules.txt")

        # Extract only the non-default rules
        default_prefixes = ["sudo", "rm -rf /", "curl", "wget", "apt-get", "pip install"]
        custom_rules = [r for r in self.rules if r.prefix not in default_prefixes]

        try:
            with open(rules_path, "w") as f:
                f.write("# Plexir Security Rules\n")
                f.write("# Format: <prefix> : <decision> : <justification>\n\n")
                for rule in custom_rules:
                    just = f" : {rule.justification}" if rule.justification else ""
                    f.write(f"{rule.prefix} : {rule.decision.value}{just}\n")
        except Exception as e:
            logger.error(f"Failed to persist rules: {e}")

policy_manager = PolicyManager()
