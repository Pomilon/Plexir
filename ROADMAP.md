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

## ✅ Completed Milestones (v1.3)

### 🧠 Core Intelligence & UI
- [x] **Reasoning Filtering**: Added `<think>` block parsing and collapsible reasoning widgets in the TUI.
- [x] **Live Status Indicator**: Implemented a responsive character-based spinner for "Thinking/Executing" states.

### 🌐 Enhanced Web Capabilities
- [x] **Search API Integration**: Support for Tavily and Serper APIs with DuckDuckGo fallback.
- [x] **Clean Extraction**: `browse_url` now filters out noise (nav, scripts) and supports sandbox-local URLs.

### 🔌 Deep MCP Integration
- [x] **MCP Resource Support**: Implemented "Resources" primitive support with dynamic resource tools for the agent.
- [ ] **Complex Server Support**: Validate against more complex official servers (PostgreSQL, etc.) once environment permits.

## ✅ Completed Milestones (v1.4)

### 📈 Metrics & Economics
- [x] **Token Tracking**: Real-time Input/Output/Total token usage displayed in the sidebar.
- [x] **Cost Estimation**: Automatic session cost calculation based on model pricing.
- [x] **Budgeting**: Enforceable session budget limits via `/config budget`.

### 🔌 Advanced MCP Integration
- [x] **MCP Prompts**: Discovery and retrieval of reusable prompt templates from MCP servers.
- [x] **Resource Templates**: Full discovery of dynamic URI templates for complex servers.

### 🧠 Coherent Memory Management
- [x] **Rolling Summarization**: Automatic background summarization of distant history when context limits are approached.
- [x] **Context Pinning**: Manual control over history via `/session pin` to keep critical messages in focus forever.

---

## ✅ Completed Milestones (v1.5)

### ⚡ Performance & Reliability
- [x] **Non-Blocking I/O**: Asynchronous configuration and session saving to eliminate UI stutter.
- [x] **Exponential Backoff**: Robust retry strategy for handling provider rate limits and transient errors.
- [x] **Intelligent Refresh**: Optimized sidebar file-tree reloading to trigger only on file-modifying actions.
- [x] **MCP Hardening**: Robust fallback schema generation for complex or non-standard MCP tools.

### ✨ Premium UI/UX
- [x] **Modern Aesthetic**: Completely revamped TCSS with distinct role-based styling and improved spacing.
- [x] **Auto-Expanding Input**: Command input grows dynamically from 1 to 5 lines for a smoother experience.
- [x] **Robust Focus**: Resolved invisible text issues and improved cursor visibility in the TUI.

### 🧪 Advanced Verification
- [x] **Robustness Test Suite**: Comprehensive testing for failover, retries, and edge-case tool behaviors.

---

## ✅ Completed Milestones (v1.6)

### 🚀 Core Architecture
- [x] **Provider Abstraction**: Refactored `LLMProvider` to support `gemini`, `openai`, `groq`, and `ollama` seamlessly.
- [x] **Thinking Blocks**: Added support for `<think>` tags to visualize reasoning chains in the TUI.
- [x] **Config Manager**: Centralized configuration with secure secret handling (keyring support).

### 🛠️ Developer Experience
- [x] **Sandbox Integration**: Docker-based sandboxing for safe code execution.
- [x] **MCP Support**: Full integration with Model Context Protocol for extensible tools.

---

## ✅ Completed Milestones (v1.7)

### ⚡ Inference Acceleration
- [x] **Cerebras Support**: Native integration for Cerebras Inference API (Llama 3.1 8B/70B) for ultra-fast generation.

### 🧠 Advanced Capabilities
- [x] **Multi-Agent Delegation**: Formalized the `delegate_to_agent` workflow with dedicated sub-agent contexts.
- [x] **Memory Bank**: Persistent long-term memory using vector stores (Chroma/Qdrant).

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
