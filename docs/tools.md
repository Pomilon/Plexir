# Tool Reference

Plexir agents are equipped with a powerful set of tools to interact with the system and the web.

## Filesystem Tools

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `read_file` | Reads the content of a file. | No |
| `write_file` | Creates or overwrites a file. | **Yes** |
| `list_directory` | Lists files and folders in a path. | No |
| `edit_file` | Precise text replacement within a file. | **Yes** |
| `get_definitions` | Summarizes classes and functions in a file. | No |

## Git Tools

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `git_status` | Shows the current working tree status. | No |
| `git_diff` | Shows changes between commits/files. | No |
| `git_add` | Adds file contents to the index. | **Yes** |
| `git_commit` | Records changes to the repository. | **Yes** |
| `git_checkout` | Switches branches or restores files. | **Yes** |
| `git_branch` | Lists, creates, or deletes branches. | No |

## Smart Agent Utilities

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `codebase_search` | Semantically searches code using natural language keywords. | No |
| `scratchpad` | Reads/Writes/Clears a persistent memory file for planning. | No |

## MCP & Extensibility

Plexir dynamically integrates with Model Context Protocol (MCP) servers.

| Tool | Description |
| :--- | :--- |
| `mcp_<server>_resources` | List or read static resources and dynamic URI templates from the server. |
| `mcp_<server>_prompts` | List and retrieve reusable prompt templates (expert configurations) from the server. |

### How it works
When you add an MCP server via `/config add`, Plexir automatically queries its capabilities and registers these tools if supported by the server. 
- **Resources**: Can be database schemas, log files, or internal documentation.
- **Prompts**: Pre-defined system instructions optimized for specific tasks like code review or documentation generation.


## Web & Information

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `web_search` | Searches the web using Tavily/Serper (if configured) or DuckDuckGo. | No |
| `browse_url` | Extracts clean text content from a URL. Supports local sandbox URLs. | No |

## Code Execution

### `python_sandbox`
Executes Python code in an isolated Docker container. This is useful for performing complex calculations, data processing, or testing logic without affecting your host environment.

## Critical Actions & HITL
Tools marked as **Critical** in the table above will trigger a **Human-in-the-Loop (HITL)** confirmation dialog in the TUI. 
*   **Visual Diffs:** For `write_file` and `edit_file`, the confirmation dialog displays a color-coded diff of the proposed changes.
*   You must manually click **Confirm** before the action is executed.