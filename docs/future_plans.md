# Plexir: Future Plans & "Killer" Features

This document outlines ideas and potential features to implement in Plexir, aiming to make it a leading AI Terminal Workspace Assistant ("Claude Code and Gemini CLI Killer").

---

### **I. Core Agentic Functionality & Intelligence**

1.  **True Context Management (Beyond Simple History):**
    *   **Context Distillation Enhancement**: Implement intelligent summarization (e.g., using LLM to summarize previous turns/tool outputs) or "scratchpad" memory for persistent context.
    *   **Relevant File Retrieval (RAG for Codebase)**: Beyond simple `grep`. Plexir should be able to:
        *   Index the project (`ripgrep` for speed, or `ctags`-like).
        *   Perform semantic searches for relevant code snippets based on natural language queries.
        *   Automatically fetch related files when working on a specific task (e.g., "fix bug in auth" -> fetches `auth.py`, `auth_tests.py`, `models.py`).

2.  **Sophisticated Tool Orchestration & Planning**:
    *   **Tool Output Interpretation**: Improve the LLM's ability to interpret complex or lengthy tool outputs (e.g., large `git ls-files`, long error tracebacks).
    *   **Interactive Tool Execution**: More robust "Human-in-the-Loop" confirmations for critical tools (e.g., `write_file`, `run_shell`) with clear diffs displayed *before* execution.
    *   **Tool Chaining & Planning**: LLM should exhibit multi-step reasoning, breaking down complex tasks into chained tool calls (e.g., "implement feature X" -> list files -> read relevant file -> plan changes -> write file -> run tests).
    *   **Tool Timeout/Error Handling**: More sophisticated logic when a tool fails (retry, re-plan, ask user).

3.  **Expanded Toolset**
    *   **`edit_file` (Patching/Inline Edits)**: A more granular file modification tool that allows applying patches or specific line replacements instead of rewriting entire files.
    *   **`git` Operations**: Add dedicated tools for `git diff`, `git add`, `git commit`, `git checkout`, `git branch`, etc.
    *   **Web Browsing / Search**: A tool to access external web information.
    *   **MCP (Model Context Protocol) Implementation**: Fully flesh out `plexir/mcp/client.py` and demonstrate actual integration with external MCP servers (e.g., a mock `Postgres MCP` or `GitHub MCP`). This is a significant differentiator.

---

### **II. User Experience & TUI Polish**

1.  **Dynamic Theming & Customization**:
    *   **Dynamic Theme Application**: Implement logic to apply theme changes immediately without restarting the app.
    *   **Theme Editor**: Allow users to define/customize color palettes within the TUI.

2.  **Rich Visual Feedback & Readability**:
    *   **Syntax Highlighting**: Automatically syntax highlight code blocks in the chat output (both generated code and tool results).
    *   **Inline Diffing**: For `git diff` or `write_file` confirmations, display beautiful side-by-side or unified diffs directly in the chat.
    *   **Collapsible Sections**: For long tool outputs or verbose AI reasoning steps, provide a way to collapse/expand sections to reduce clutter.
    *   **Spinner/Progress Indicators**: More granular visual feedback during lengthy AI generations or tool executions.

3.  **Advanced Keyboard-First Navigation**:
    *   **Omni-Box / Command Palette**: A central, searchable input (`Ctrl+P` or similar) that allows users to quickly execute commands, search history, or navigate.
    *   **Tab/Panel Management**: Implement navigation between different "views" or "panels" (e.g., Chat, File Explorer, Debug Log, Active Tasks).
    *   **Contextual Keybindings**: Keybindings that change based on the active panel or focused widget.
    *   **Clipboard Integration**: Easy copy/paste of code/text to/from the terminal.

4.  **Notifications & Alerts**:
    *   Non-intrusive notifications for background tasks, tool completions, errors.

5.  **Status Bar Enhancements**:
    *   More real-time info: Current working directory, active git branch, notification counts.

---

### **III. Advanced Features & Agentic Capabilities**

1.  **Macro Recording & Playback**:
    *   Record a sequence of user prompts and AI responses/tool actions, and replay them.
2.  **Task Management & Persistent Sessions**:
    *   Plexir should be able to manage multiple ongoing tasks/branches of conversation.
    *   Save/load entire session states (history, context, active tasks).
3.  **"Self-Correction" Loop Visualization**:
    *   When the agent detects an error and self-corrects, make this process transparent to the user (e.g., "Plexir detected error X, replanning...").

---

### **IV. Polish & Deliverability**

1.  **Installer/Distribution**: `pip install plexir`, `conda install plexir`.
2.  **Comprehensive Documentation**: README, usage guides, `/help` always up-to-date.
3.  **Error Resilience**: More specific error handling, user-friendly messages.
4.  **Testing**: More robust unit and integration tests across all components.