"""
Diff Viewer Widget for Plexir TUI.
Displays a colored unified diff between two text strings.
"""

import difflib
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Static

class DiffViewer(Static):
    """
    A widget that displays a diff between 'old_text' and 'new_text'.
    """

    DEFAULT_CSS = """
    DiffViewer {
        height: auto;
        max-height: 20;
        background: $surface;
        border: solid $primary;
        padding: 1;
        overflow-y: scroll;
    }
    """

    def __init__(self, old_text: str, new_text: str, filename: str = "diff"):
        super().__init__()
        self.old_text = old_text
        self.new_text = new_text
        self.filename = filename

    def on_mount(self):
        """Generates and displays the diff on mount."""
        diff_lines = list(difflib.unified_diff(
            self.old_text.splitlines(),
            self.new_text.splitlines(),
            fromfile=f"a/{self.filename}",
            tofile=f"b/{self.filename}",
            lineterm=""
        ))

        if not diff_lines:
            self.update(Text("No changes detected.", style="bold yellow"))
            return

        # Build a Rich Text object with manual coloring for diff syntax
        # We manually color because standard syntax highlighters might not catch standard diff format perfectly
        # or we want specific colors for our theme.
        
        text = Text()
        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                style = "bold white"
            elif line.startswith("@@"):
                style = "bold cyan"
            elif line.startswith("+"):
                style = "bold green"
            elif line.startswith("-"):
                style = "bold red"
            else:
                style = "dim white"
            
            text.append(line + "\n", style=style)

        self.update(text)
