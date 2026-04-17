# Security Policy Engine

Plexir v1.10 introduces a hierarchical Security Policy Engine to govern the execution of shell commands, especially when running in autonomous (YOLO) mode.

## Overview

The policy engine evaluates every command (and sub-command in chains like `&&` or `;`) against a set of rules. Rules are checked from most specific to least specific.

## Rule Types

1. **ALLOW**: The command is executed immediately.
2. **PROMPT**: The user is asked for confirmation before execution (Default for critical tools).
3. **FORBIDDEN**: The command is blocked entirely, and the AI is informed of the violation.

## Configuration

Rules are stored in `.plexir/rules.txt` within your workspace. 

### Format
Each line should follow the format:
`<command_prefix> : <decision> : [justification]`

### Example `rules.txt`
```text
# Allow all git commands
git : allow

# Block dangerous deletions
rm -rf / : forbidden : Destructive root deletion is never allowed.

# Prompt for network access
curl : prompt : Network access requires explicit approval.
pip install : prompt : Package installation should be reviewed.
```

## JIT (Just-In-Time) Approvals

When a command triggers a **PROMPT** decision, Plexir will show a confirmation dialog.
- You can check **"Always allow commands starting with..."** to automatically add a new `ALLOW` rule to your local `.plexir/rules.txt`.
- This allows the engine to learn your preferences as you work.

## Hardcoded Safety Defaults

Plexir includes several built-in safety rules that cannot be overridden by local configurations (unless in YOLO mode):
- `sudo` is **FORBIDDEN**.
- `rm -rf /` is **FORBIDDEN**.
- Network tools like `curl`, `wget` defaults to **PROMPT**.
