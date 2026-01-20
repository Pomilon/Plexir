"""
Modal screens for the Plexir TUI.
Includes confirmation dialogs for critical actions.
"""

import os
import datetime
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, Input
from textual.containers import Vertical, Horizontal
from plexir.ui.diff_viewer import DiffViewer

class ConfirmToolCall(ModalScreen[str]):
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
            
            # Logic for DiffViewer
            diff_widget = None
            
            if self.tool_name == "edit_file":
                old = self.args.get("old_text", "")
                new = self.args.get("new_text", "")
                diff_widget = DiffViewer(old, new, filename=self.args.get("file_path", "snippet"))
            
            elif self.tool_name == "write_file":
                path = self.args.get("file_path", "")
                new_content = self.args.get("content", "")
                old_content = ""
                if path and os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            old_content = f.read()
                    except Exception as e:
                        old_content = f"(Error reading existing file for diff: {e})"
                elif path:
                     old_content = "" 
                
                diff_widget = DiffViewer(old_content, new_content, filename=path)

            if diff_widget:
                yield Label("Proposed Changes:", classes="section-title")
                yield diff_widget
            else:
                yield Static(f"Arguments:\n{self.args}", id="confirm-args")
            
            with Horizontal(id="confirm-buttons"):
                yield Button("CONFIRM", variant="success", id="confirm-btn")
                yield Button("SKIP", variant="primary", id="skip-btn")
                yield Button("STOP", variant="error", id="stop-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button clicks and returns the result."""
        if event.button.id == "confirm-btn":
            self.dismiss("confirm")
        elif event.button.id == "skip-btn":
            self.dismiss("skip")
        else:
            self.dismiss("stop")

class SandboxSyncScreen(ModalScreen[str]):
    """Modal screen to handle sandbox export on exit."""

    def __init__(self):
        super().__init__()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.default_export_path = f"sandbox_export_{timestamp}"

    def compose(self) -> ComposeResult:
        with Vertical(id="sandbox-modal"):
            yield Label("⚠️ [bold]Unsaved Sandbox Changes[/bold]", classes="warning-title")
            yield Label("You are exiting Clone Mode. Sandbox changes will be lost unless saved.")
            
            yield Label("\nExport Path:", classes="section-title")
            yield Input(value=self.default_export_path, id="export-path-input")
            
            with Horizontal(id="sandbox-buttons"):
                yield Button("Export to Path", variant="primary", id="btn-export")
                yield Button("Sync to CWD (Overwrite)", variant="warning", id="btn-sync")
                
            with Horizontal(id="sandbox-actions"):
                yield Button("Discard & Exit", variant="error", id="btn-discard")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export":
            path = self.query_one("#export-path-input", Input).value
            self.dismiss(f"export:{path}")
        elif event.button.id == "btn-sync":
            self.dismiss("sync_cwd")
        elif event.button.id == "btn-discard":
            self.dismiss("discard")
        elif event.button.id == "btn-cancel":
            self.dismiss("cancel")

