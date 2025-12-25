"""
Modal screens for the Plexir TUI.
Includes confirmation dialogs for critical actions.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.containers import Vertical, Horizontal

class ConfirmToolCall(ModalScreen[bool]):
    """Modal screen that requests user confirmation before executing critical tools."""
    
    def __init__(self, tool_name: str, args: dict):
        super().__init__()
        self.tool_name = tool_name
        self.args = args

    def compose(self) -> ComposeResult:
        """Composes the confirmation dialog layout."""
        with Vertical(id="confirm-modal"):
            yield Label("⚠️ [bold]CRITICAL ACTION[/bold]")
            yield Label(f"Tool: [cyan]{self.tool_name}[/cyan]")
            yield Static(f"Arguments:\n{self.args}", id="confirm-args")
            
            with Horizontal(id="confirm-buttons"):
                yield Button("CONFIRM", variant="success", id="confirm-btn")
                yield Button("CANCEL", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button clicks and returns the result."""
        self.dismiss(event.button.id == "confirm-btn")