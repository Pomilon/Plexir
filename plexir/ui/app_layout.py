"""
Modular layout composition for the Plexir TUI.
Defines the structure of the main interface.
"""

from textual.app import ComposeResult
from textual.widgets import Input, Label, Static, Footer
from textual.containers import Vertical, Horizontal, VerticalScroll, Container
from plexir.ui.widgets import ToolStatus, StatsPanel, WorkspaceTree
from plexir import __version__

def compose_main_layout() -> ComposeResult:
    """Creates the main application layout structure."""
    
    with Container(id="header"):
        yield Static(f"Plexir v{__version__}", classes="header-title")

    with Horizontal(id="main-layout-horizontal"):
        # Sidebar section
        with Vertical(id="sidebar"):
            yield WorkspaceTree()
            yield Label("SYSTEM STATUS", classes="sidebar-header")
            yield StatsPanel(id="stats-panel")
            yield Label("COMMANDS", classes="sidebar-header")
            yield Static("/help, /config, /tools, /session", classes="sidebar-content") 

        # Main interaction area
        with Vertical(id="main-container"):
            yield ToolStatus(id="tool-status")
            
            with VerticalScroll(id="chat-scroll"):
                yield Static(
                    f"INITIALIZING PLEXIR V{__version__}...\nSYSTEM READY.\n\nType `/help` for list of commands.", 
                    classes="welcome-msg"
                )
            
            with Container(id="input-container"):
                yield Input(placeholder="Enter instruction...", id="user-input")
    
    yield Footer(id="footer")
