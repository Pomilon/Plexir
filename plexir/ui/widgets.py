"""
Custom Textual widgets for the Plexir TUI.
Includes MessageBubbles, StatsPanel, and WorkspaceTree.
"""

import itertools
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Static, Label, Markdown as MarkdownWidget, DirectoryTree, Collapsible, LoadingIndicator
from plexir.core.config_manager import config_manager

class MessageContent(MarkdownWidget):
    """Widget to display message content with Markdown support."""
    def __init__(self, content: str = "", **kwargs):
        super().__init__(content, **kwargs)
        self.content = content

    async def update(self, content: str):
        """Updates the widget content and raw storage."""
        self.content = content
        await super().update(content)

class MessageBubble(Container):
    """Wraps a single message (user, AI, or system) with a header and content."""

    class Clicked(events.Event):
        """Event emitted when the bubble is clicked."""
        def __init__(self, bubble: "MessageBubble"):
            super().__init__()
            self.bubble = bubble

    def __init__(self, role: str, content: str = "", **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.initial_content = content
        self.add_class(f"message-{role}")

    def on_click(self, event: events.Click) -> None:
        if "queued" in self.classes:
            event.stop()
            self.post_message(self.Clicked(self))

    def compose(self) -> ComposeResult:
        """Composes the message bubble layout."""
        # Map roles to friendly labels
        role_map = {"user": "👤 YOU", "model": "🤖 AI", "system": "⚙️ SYSTEM"}
        role_label = role_map.get(self.role, self.role.upper())

        with Horizontal(classes="message-header"):
            yield Label(role_label, classes=f"message-author role-{self.role}")

        if self.initial_content:
            yield MessageContent(self.initial_content, id="message-text", classes="message-content")

class StatsPanel(Static):

    """Sidebar panel displaying real-time session statistics."""
    
    model_name = reactive("Model Name")
    status = reactive("Idle")
    latency = reactive(0.0)
    sandbox_active = reactive(False)
    ctx_tokens = reactive(0)
    total_tokens = reactive(0)
    cost = reactive(0.0)

    def compose(self) -> ComposeResult:
        """Composes the statistics panel layout."""
        with Horizontal(classes="stat-row"):
            yield Label("MODEL", classes="stat-label")
            yield Label(self.model_name, id="stat-model", classes="stat-value")
        
        with Horizontal(classes="stat-row"):
            yield Label("STATUS", classes="stat-label")
            yield Label(self.status, id="stat-status", classes="stat-value")

        with Horizontal(classes="stat-row"):
            yield Label("CONTEXT", classes="stat-label")
            yield Label(f"{self.ctx_tokens}", id="stat-ctx-tokens", classes="stat-value")

        with Horizontal(classes="stat-row"):
            yield Label("TOTAL", classes="stat-label")
            yield Label(f"{self.total_tokens}", id="stat-total-tokens", classes="stat-value")

        with Horizontal(classes="stat-row"):
            yield Label("COST", classes="stat-label")
            yield Label(f"${self.cost:.4f}", id="stat-cost", classes="stat-value")

        with Horizontal(classes="stat-row"):
            yield Label("TIME", classes="stat-label")
            yield Label(f"{self.latency:.2f}s", id="stat-latency", classes="stat-value")

        with Horizontal(classes="stat-row"):
            yield Label("SANDBOX", classes="stat-label")
            yield Label("OFF", id="stat-sandbox", classes="stat-value")

    def watch_model_name(self, value: str):
        """Updates the model name label."""
        try:
            self.query_one("#stat-model", Label).update(str(value))
        except Exception:
            pass

    def watch_status(self, value: str):
        """Updates the status label."""
        try:
            self.query_one("#stat-status", Label).update(str(value))
        except Exception:
            pass

    def watch_latency(self, value: float):
        """Updates the latency label."""
        try:
            self.query_one("#stat-latency", Label).update(f"{value:.2f}s")
        except Exception:
            pass

    def watch_ctx_tokens(self, value: int):
        """Updates the context tokens label."""
        try:
            self.query_one("#stat-ctx-tokens", Label).update(str(value))
        except Exception:
            pass

    def watch_total_tokens(self, value: int):
        """Updates the total tokens label."""
        try:
            self.query_one("#stat-total-tokens", Label).update(str(value))
        except Exception:
            pass

    def watch_cost(self, value: float):
        """Updates the cost label."""
        try:
            self.query_one("#stat-cost", Label).update(f"${value:.4f}")
        except Exception:
            pass

    def watch_sandbox_active(self, value: bool):
        """Updates the sandbox status label and styling."""
        try:
            label = self.query_one("#stat-sandbox", Label)
            label.update("ON" if value else "OFF")
            label.set_class(value, "success-text")
        except Exception:
            pass

class ToolStatus(Static):
    """A status bar displayed at the top during tool execution."""
    
    def on_mount(self) -> None:
        self._spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        self._message = ""
        self._running = False
        self.set_interval(0.1, self._update_spinner)

    def _update_spinner(self) -> None:
        if self._running:
            s = next(self._spinner)
            self.update(f"{s} {self._message}")
            self.refresh()

    def set_status(self, message: str, running: bool = True):
        """Updates the status message and visibility."""
        self.display = True
        self._message = message
        self._running = running
        if not running:
            self.update(f"✓ {message}")
        self.refresh()

class WorkspaceTree(Container):
    """A wrapper for DirectoryTree displayed in the sidebar."""
    def compose(self) -> ComposeResult:
        """Composes the workspace tree layout."""
        yield Label("WORKSPACE", classes="sidebar-header")
        yield DirectoryTree("./", id="file-tree")

class SubAgentProgress(Container):
    """Container for a single sub-agent's lifecycle (thoughts, tools, output)."""
    def __init__(self, agent_name: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.add_class("subagent-progress")

    def compose(self) -> ComposeResult:
        yield Label(f"🤖 [bold]{self.agent_name.upper()}[/bold] WORKING...", classes="subagent-header")

class SummarizationBlock(Static):
    """Informative notice displayed when conversation is summarized."""
    def __init__(self, current_tokens: int, limit: int, message_count: int):
        super().__init__()
        self.current_tokens = current_tokens
        self.limit = limit
        self.message_count = message_count
        self.add_class("summarization-block")

    def compose(self) -> ComposeResult:
        yield Label("🔄 CONTEXT CONDENSATION", classes="summary-header")
        yield Label(
            f"Threshold reached: {self.current_tokens:,} tokens ({self.message_count} msgs).\n"
            f"Condensing to ~30% of context window ({self.limit:,} tokens) to maintain peak performance.",
            classes="summary-details"
        )

class ToolOutput(Container):
    """Widget to display tool execution details and output (Always visible)."""
    def __init__(self, tool_name: str, args: str, result: str):
        super().__init__()
        self.tool_name = tool_name
        self.args_str = args
        self.result_str = result
        self.add_class("tool-output")
    def compose(self) -> ComposeResult:
        """Composes the tool output layout."""
        # Title/Header
        yield Label(f"🛠️ {self.tool_name}", classes="tool-header")

        verbosity = config_manager.config.verbosity

        # Args
        safe_args = str(self.args_str)
        if verbosity == 0 and len(safe_args) > 120: 
            safe_args = safe_args[:120] + "..."
        yield Label(f"Args: {safe_args}", classes="tool-args")

        # Result
        result_str = str(self.result_str)
        if verbosity == 0 and len(result_str) > 2000:
             result_str = result_str[:2000] + "\n... (truncated)"

        yield MarkdownWidget(f"```text\n{result_str}\n```", classes="tool-result")

