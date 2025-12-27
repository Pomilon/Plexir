"""
Custom Textual widgets for the Plexir TUI.
Includes MessageBubbles, StatsPanel, and WorkspaceTree.
"""

import itertools
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Static, Label, Markdown as MarkdownWidget, DirectoryTree, Collapsible, LoadingIndicator

class MessageContent(MarkdownWidget):
    """Widget to display message content with Markdown support."""
    pass

class MessageBubble(Container):
    """Wraps a single message (user, AI, or system) with a header and content."""
    
    def __init__(self, role: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.add_class(f"message-{role}")

    def compose(self) -> ComposeResult:
        """Composes the message bubble layout."""
        role_map = {"user": "User", "model": "Plexir", "system": "System"}
        role_label = role_map.get(self.role, self.role.capitalize())
        
        with Horizontal(classes="message-header"):
            yield Label(role_label, classes=f"message-author role-{self.role}")
            
        yield MessageContent("", classes="message-content")

class StatsPanel(Static):
    """Sidebar panel displaying real-time session statistics."""
    
    model_name = reactive("Model Name")
    status = reactive("Idle")
    latency = reactive(0.0)
    sandbox_active = reactive(False)
    tokens = reactive(0)
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
            yield Label("TOKENS", classes="stat-label")
            yield Label(f"{self.tokens}", id="stat-tokens", classes="stat-value")

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

    def watch_tokens(self, value: int):
        """Updates the tokens label."""
        try:
            self.query_one("#stat-tokens", Label).update(str(value))
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

class ToolOutput(Container):
    """Widget to display tool execution details and output (Always visible)."""
    def __init__(self, tool_name: str, args: str, result: str):
        super().__init__()
        self.tool_name = tool_name
        self.args_str = args
        self.result_str = result
        self.add_class("tool-output")

    def compose(self) -> ComposeResult:
        # Title/Header
        yield Label(f"🛠️ {self.tool_name}", classes="tool-header")
        
        # Args
        safe_args = str(self.args_str)
        if len(safe_args) > 80: safe_args = safe_args[:80] + "..."
        yield Label(f"Args: {safe_args}", classes="tool-args")
        
        # Result
        result_str = str(self.result_str)
        if len(result_str) > 2000:
             result_str = result_str[:2000] + "\n... (truncated)"
             
        yield MarkdownWidget(f"```text\n{result_str}\n```", classes="tool-result")
