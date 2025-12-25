# Tool Reference

Plexir agents are equipped with a powerful set of tools to interact with the system and the web.

## Filesystem Tools

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `read_file` | Reads the content of a file. | No |
| `write_file` | Creates or overwrites a file. | **Yes** |
| `list_directory` | Lists files and folders in a path. | No |
| `edit_file` | Precise text replacement within a file. | **Yes** |

## Git Tools

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `git_status` | Shows the current working tree status. | No |
| `git_diff` | Shows changes between commits/files. | No |
| `git_add` | Adds file contents to the index. | **Yes** |
| `git_commit` | Records changes to the repository. | **Yes** |

## Web & Information

| Tool | Description | Critical? |
| :--- | :--- | :--- |
| `web_search` | Searches DuckDuckGo for top results. | No |
| `browse_url` | Extracts text content from a URL. | No |

## Code Execution

### `python_sandbox`
Executes Python code in an isolated Docker container. This is useful for performing complex calculations, data processing, or testing logic without affecting your host environment.

## Critical Actions & HITL
Tools marked as **Critical** in the table above will trigger a **Human-in-the-Loop (HITL)** confirmation dialog in the TUI. You must manually click **Confirm** before the action is executed. This prevents the AI from making unwanted changes to your files or repository.
