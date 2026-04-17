"""
Modal screens for the Plexir TUI.
Includes confirmation dialogs for critical actions.
"""

import os
import datetime
import asyncio
from typing import List, Optional, Any
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, Input, TextArea, OptionList, Checkbox, LoadingIndicator
from textual.widgets.option_list import Option
from textual.containers import Vertical, Horizontal
from plexir.ui.diff_viewer import DiffViewer

class ModelPicker(ModalScreen[str]):
    """Interactive model selection screen for provider and model."""
    
    def __init__(self, providers: list, active_index: int):
        super().__init__()
        self.providers = providers
        self.active_index = active_index
        self.current_provider_index = active_index
        self.showing_providers = False
        self.is_loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker-modal"):
            yield Label("", id="picker-title", classes="modal-title")
            with Vertical(id="picker-container"):
                yield OptionList(id="picker-list")
                yield LoadingIndicator(id="picker-loading", classes="hidden")
            with Horizontal(classes="modal-buttons"):
                yield Button("SELECT", variant="primary", id="btn-select")
                yield Button("BACK", id="btn-back", disabled=True)
                yield Button("CANCEL", id="btn-cancel")

    async def on_mount(self) -> None:
        """Initialize the list with models of current provider."""
        await self._show_models()

    async def _show_models(self) -> None:
        """Displays the model list for the current provider."""
        self.showing_providers = False
        provider = self.providers[self.current_provider_index]
        self.query_one("#picker-title", Label).update(f"Select Model for [bold]{provider.name}[/bold]")
        
        ol = self.query_one("#picker-list", OptionList)
        loader = self.query_one("#picker-loading", LoadingIndicator)
        
        ol.add_class("hidden")
        loader.remove_class("hidden")
        self.is_loading = True
        
        # Add "Switch Provider" as first option
        options = [Option("[bold]🔄 Switch Provider[/bold]", id="switch_provider")]
        
        try:
            # Get actual models from API with a timeout
            models = await asyncio.wait_for(provider.get_available_models(), timeout=10.0)
            if not models:
                models = [provider.model_name]
                
            for m in models:
                options.append(Option(m, id=m))
        except asyncio.TimeoutError:
            options.append(Option(f"{provider.model_name} (Timeout fetching others)", id=provider.model_name))
        except Exception as e:
            options.append(Option(f"{provider.model_name} (Error: {e})", id=provider.model_name))
        finally:
            self.is_loading = False
            ol.remove_class("hidden")
            loader.add_class("hidden")
        
        ol.clear_options()
        ol.add_options(options)
        
        # Try to highlight current model if in list
        for i, opt in enumerate(options):
            if opt.id == provider.model_name:
                ol.highlighted = i
                break
        
        self.query_one("#btn-back", Button).disabled = True

    def _show_providers(self) -> None:
        """Displays the provider selection list."""
        if self.is_loading: return

        self.showing_providers = True
        self.query_one("#picker-title", Label).update("Select LLM Provider")
        
        options = [
            Option(f"{p.name} ({p.model_name})", id=str(i)) 
            for i, p in enumerate(self.providers)
        ]
        
        ol = self.query_one("#picker-list", OptionList)
        ol.clear_options()
        ol.add_options(options)
        ol.highlighted = self.current_provider_index
        self.query_one("#btn-back", Button).disabled = False

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle enter or double click."""
        if self.is_loading: return
        await self._handle_selection(event.option)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.is_loading: return

        if event.button.id == "btn-select":
            ol = self.query_one("#picker-list", OptionList)
            if ol.highlighted is not None:
                await self._handle_selection(ol.get_option_at_index(ol.highlighted))
        elif event.button.id == "btn-back":
            self._show_providers()
        else:
            self.dismiss("cancel")

    async def _handle_selection(self, option: Option) -> None:
        if self.showing_providers:
            self.current_provider_index = int(option.id)
            await self._show_models()
        else:
            if option.id == "switch_provider":
                self._show_providers()
            else:
                # Return provider_index:model_name
                self.dismiss(f"{self.current_provider_index}:{option.id}")

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
            
            # ... (diff logic remains same)
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
                    except Exception: pass
                diff_widget = DiffViewer(old_content, new_content, filename=path)

            if diff_widget:
                yield Label("Proposed Changes:", classes="section-title")
                yield diff_widget
            else:
                yield Static(f"Arguments:\n{self.args}", id="confirm-args")
            
            # JIT Policy Amendment Option
            if self.tool_name == "run_shell":
                cmd = self.args.get("command", "")
                yield Checkbox(f"Always allow commands starting with '{cmd[:20]}...'", id="chk-always-allow")
            
            with Horizontal(id="confirm-buttons"):
                yield Button("CONFIRM", variant="success", id="confirm-btn")
                yield Button("SKIP", variant="primary", id="skip-btn")
                yield Button("STOP", variant="error", id="stop-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button clicks and returns the result."""
        always_allow = False
        if self.tool_name == "run_shell":
            try:
                always_allow = self.query_one("#chk-always-allow", Checkbox).value
            except Exception: pass

        if event.button.id == "confirm-btn":
            self.dismiss("confirm_always" if always_allow else "confirm")
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

