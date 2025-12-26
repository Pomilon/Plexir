# Plexir Roadmap 🌌

---

## ✅ Completed Milestones (v1.2)

We have successfully implemented the core foundation and advanced agentic capabilities.

### 🧠 Core Intelligence & Agentic Workflow
- [x] **RAG / Codebase Context**: Implemented `codebase_search` (keyword-based) and `get_definitions` for rapid file mapping.
- [x] **Persistent Memory**: Added `scratchpad` tool for maintaining context and plans across long sessions.
- [x] **Smart Orchestration**: `Router` handles provider failover, retries, and "Plan First" prompting strategies.
- [x] **Human-in-the-Loop (HITL)**: 
    - Critical tools (`write_file`, `edit_file`, `git_push`) require explicit confirmation.
    - **Skip/Stop**: Granular control to skip a specific tool or stop the entire process.
- [x] **Interruption**: `Ctrl+C` allows immediate cancellation of active generation/tool execution.

### 🛠️ Expanded Toolset
- [x] **Full Git Suite**: `status`, `diff`, `add`, `commit`, `checkout`, `branch`, `push`, `pull`.
- [x] **Secure Auth**: Git tools use configured tokens (`/config tool git token ...`) injected via headers for secure remote operations.
- [x] **GitHub Integration**: Create Issues and Pull Requests on authorized repositories.
- [x] **File Operations**: Robust `edit_file` for precise patching.
- [x] **Sandboxing**: Persistent Docker environment (`plexir --sandbox`) with bind-mounted workspace.

### 🖥️ UX & TUI Polish
- [x] **Visual Diffs**: Confirmation modals show rich, color-coded side-by-side diffs before file modifications.
- [x] **Collapsible Tool Outputs**: Execution logs are wrapped in clean `ToolOutput` widgets to reduce clutter.
- [x] **Command Palette**: Native Textual `Ctrl+P` palette for quick access to actions and themes.
- [x] **Live Workspace**: File tree auto-refreshes on every tool execution.
- [x] **Performance**: Dynamic throttling and smart auto-scroll for smooth rendering of large LLM outputs.
- [x] **Theming**: Dynamic switching between themes.

### ⚙️ Infrastructure
- [x] **Configuration**: Robust JSON-based config system for providers and tools.
- [x] **Session Management**: Save, load, and manage conversation history.
- [x] **Macros**: Record and replay complex command sequences.
- [x] **Documentation**: Comprehensive `COMMANDS.md` and `tools.md` updated for v1.2.

---

## 🚧 In Progress / Next Up (v1.3)

These features are partially implemented or prioritized for the next iteration.

### 1. Enhanced Web Capabilities
- [ ] **Search API Integration**: Replace current scraping (`web_search`) with a robust API (e.g., Tavily, Serper) for reliable, citation-backed results.
- [ ] **Deep Browsing**: Improve `browse_url` to handle dynamic JS-heavy sites (possibly via a headless browser microservice).

### 2. Deep MCP Integration
- [ ] **Complex Server Support**: Validate the existing JSON-RPC client against complex servers like PostgreSQL or SQLite (official implementations).
- [ ] **MCP Resource Support**: Fully implement the "Resources" primitive of the MCP protocol (currently focusing on "Tools").

### 3. Testing & CI/CD
- [ ] **Coverage Expansion**: Increase unit test coverage for UI components (`widgets.py`, `app.py`).
- [ ] **Integration Tests**: Add end-to-end tests running in the actual sandbox.

---

## 🔮 Long Term Vision (v2.0)

### 1. True "IDE-Like" UI
- [ ] **Multi-Tab Interface**: Support multiple open chat buffers or file editors simultaneously.
- [ ] **Split Panes**: Allow viewing chat and code side-by-side.
- [ ] **Integrated Editor**: A lightweight TUI code editor (like `nano` or `micro`) embedded directly in Plexir.

### 2. Advanced Reasoning Engine
- [ ] **Semantic Search (Vector DB)**: Replace keyword search with embeddings for true semantic understanding of the codebase.
- [ ] **Autonomous Agents**: "Set and Forget" mode where the agent runs in a loop to solve a complex task (e.g., "Refactor this module") with self-correction and minimal user intervention.

### 3. Ecosystem
- [ ] **Plugin System**: Allow users to write custom Python plugins/tools that Plexir loads dynamically.
- [ ] **Binary Distribution**: `brew install plexir`, `apt install plexir`.
