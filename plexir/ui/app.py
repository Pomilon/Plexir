"""
Main application class for the Plexir TUI.
Orchestrates the UI, router, and command processing.
"""

import asyncio
import logging
import os
import time
from typing import List, Dict, Any, Optional

from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Static, Footer, DirectoryTree
from textual.containers import VerticalScroll
from textual.theme import Theme
from textual import work

from plexir.ui.widgets import MessageContent, ToolStatus, StatsPanel, MessageBubble, ToolOutput
from plexir.ui.app_layout import compose_main_layout
from plexir.ui.screens import ConfirmToolCall
from plexir.core.router import Router, RouterEvent
from plexir.core.commands import CommandProcessor
from plexir.core.config_manager import config_manager
from plexir.core.session import SessionManager

logger = logging.getLogger(__name__)

class PlexirApp(App):
    """The main Plexir TUI Application."""
    
    CSS_PATH = "styles.tcss"
    TITLE = "Plexir Terminal"
    SCREENS = {} 

    # --- Themes ---
    TOKYO_NIGHT = Theme(
        name="tokyo-night",
        background="#1a1b26",
        surface="#16161e",
        panel="#24283b",
        primary="#7aa2f7",
        secondary="#bb9af7",
        accent="#7aa2f7",
        foreground="#c0caf5",
        success="#9ece6a",
        warning="#e0af68",
        error="#f7768e",
        boost="#565f89",
        variables={"divider": "#414868"}
    )

    HACKER = Theme(
        name="hacker",
        background="#000000",
        surface="#050505",
        panel="#0a0a0a",
        primary="#00ff00",
        secondary="#00cc00",
        accent="#00ff00",
        foreground="#00ff00",
        success="#00ff00",
        warning="#ffff00",
        error="#ff0000",
        boost="#00aa00",
        variables={"divider": "#00ff00"}
    )

    PLEXIR_LIGHT = Theme(
        name="plexir-light",
        background="#f0f0f0",
        surface="#e0e0e0",
        panel="#ffffff",
        primary="#2b5797",
        secondary="#603cba",
        accent="#2b5797",
        foreground="#333333",
        success="#2d862d",
        warning="#ff9900",
        error="#cc0000",
        boost="#666666",
        dark=False,
        variables={"divider": "#cccccc"}
    )

    BINDINGS = [
        ("ctrl+r", "reload_providers", "Reload Providers"),
        ("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
        ("ctrl+y", "copy_last_response", "Copy AI"),
        ("ctrl+c", "interrupt_or_quit", "Stop/Quit"),
        ("ctrl+f", "focus_input", "Focus Input"),
    ]

    def __init__(self, sandbox_enabled: bool = False):
        super().__init__()
        self.register_theme(self.TOKYO_NIGHT)
        self.register_theme(self.HACKER)
        self.register_theme(self.PLEXIR_LIGHT)
        
        self.router = Router(sandbox_enabled=sandbox_enabled)
        self.session_manager = SessionManager()
        self.command_processor = CommandProcessor(self, self.session_manager)
        self.history: List[Dict[str, Any]] = []
        self.generation_worker = None
        
        # Macro state
        self.is_recording_macro = False
        self.current_macro_name: Optional[str] = None
        self.recorded_commands: List[str] = []

    async def on_mount(self) -> None:
        """Initializes providers, UI state, and theme on startup."""
        await self.router.reload_providers()
        
        stats = self.query_one("#stats-panel", StatsPanel)
        stats.sandbox_active = self.router.sandbox_enabled

        initial_theme = config_manager.config.theme or "tokyo-night"
        
        # Migration for old theme names
        theme_map = {"dark": "tokyo-night", "light": "plexir-light"}
        initial_theme = theme_map.get(initial_theme, initial_theme)
            
        try:
            self.theme = initial_theme
        except Exception:
            self.theme = "tokyo-night"

    def compose(self) -> ComposeResult:
        """Composes the main application layout."""
        yield from compose_main_layout()

    # --- Actions ---

    async def action_reload_providers(self):
        """Reloads LLM providers from configuration."""
        await self.router.reload_providers()
        self.notify("Providers reloaded from config.")
        self.query_one("#user-input", Input).focus()

    def action_toggle_sidebar(self):
        """Toggles sidebar visibility."""
        sidebar = self.query_one("#sidebar")
        sidebar.toggle_class("-hidden")
        self.query_one("#user-input", Input).focus()

    def action_interrupt_or_quit(self):
        """Interrupts current generation or quits the app."""
        if self.generation_worker and self.generation_worker.is_running:
            self.generation_worker.cancel()
            self.notify("Interrupted generation.", severity="warning")
            # Reset UI status
            self.query_one("#tool-status", ToolStatus).set_status("Interrupted", running=False)
            self.query_one("#stats-panel", StatsPanel).status = "Idle"
        else:
            self.action_quit()

    async def action_quit(self):
        """Cleanly exits the application, stopping any background sandboxes."""
        if self.router.sandbox:
            self.notify("Stopping sandbox container...")
            await self.router.sandbox.stop()
        self.exit()

    def action_focus_input(self):
        """Focuses the main command input."""
        self.query_one("#user-input", Input).focus()

    def action_copy_last_response(self):
        """Copies the content of the last AI message to the clipboard."""
        for msg in reversed(self.history):
            if msg.get("role") == "model" and msg.get("content"):
                self.copy_to_clipboard(msg["content"])
                self.notify("AI response copied to clipboard.")
                return
        self.notify("No AI response found to copy.", severity="warning")

    def action_set_theme(self, theme_name: str):
        """Sets the application theme dynamically."""
        try:
            self.theme = theme_name
            config_manager.update_app_setting("theme", theme_name)
            self.notify(f"Theme set to '{theme_name}'.")
        except Exception as e:
            self.notify(f"Failed to set theme '{theme_name}': {e}", severity="error")

    def action_clear_chat(self):
        """Clears the chat display and resets the conversation history."""
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        for child in list(chat_scroll.children):
            if isinstance(child, MessageBubble) or (isinstance(child, Static) and "welcome-msg" not in child.classes):
                child.remove()
        chat_scroll.mount(Static("Chat cleared.", classes="welcome-msg"))
        self.router.reset_provider()
        self.notify("Chat history cleared.")

    # --- Event Handlers ---

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Persists theme changes to configuration when updated."""
        if new_theme != old_theme:
            try:
                config_manager.update_app_setting("theme", new_theme)
                logger.info(f"Theme persisted: {new_theme}")
            except Exception as e:
                logger.error(f"Failed to persist theme change: {e}")

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Handles user input from the main text field."""
        user_text = message.value
        if not user_text.strip():
            return

        input_widget = self.query_one("#user-input", Input)
        input_widget.value = ""

        # 1. Process slash commands
        command_response = await self.command_processor.process(user_text)
        if command_response:
             if command_response == "Exiting...":
                 return
             elif "Session history cleared." in command_response:
                 self.action_clear_chat()
                 self._add_message("user", user_text)
                 self._add_message("system", command_response)
                 input_widget.focus()
                 return
             elif "loaded. Chat history updated." in command_response:
                 self.action_clear_chat()
                 self._load_history_to_chat(self.history)
                 self._add_message("user", user_text)
                 self._add_message("system", command_response)
                 input_widget.focus()
                 return

             self._add_message("user", user_text)
             self._add_message("system", command_response)
             input_widget.focus()
             return

        # 2. Add to history and update UI
        self.history.append({"role": "user", "content": user_text})
        self._add_message("user", user_text)

        # 3. Trigger AI response
        self.generation_worker = self.generate_response()

    # --- Macro Support ---

    def start_macro_recording(self, name: str):
        """Starts recording user commands into a macro."""
        self.is_recording_macro = True
        self.current_macro_name = name
        self.recorded_commands = []
        self.notify(f"Started recording macro: {name}")

    def stop_macro_recording(self) -> List[str]:
        """Stops recording and returns the captured commands."""
        commands = self.recorded_commands
        self.is_recording_macro = False
        self.current_macro_name = None
        self.recorded_commands = []
        self.notify("Macro recording stopped.")
        return commands

    def record_macro_command(self, command: str):
        """Appends a command to the current macro recording."""
        if self.is_recording_macro:
            self.recorded_commands.append(command)

    async def play_macro(self, commands: List[str]):
        """Executes a list of commands sequentially."""
        self.notify("Playing macro...")
        input_widget = self.query_one("#user-input", Input)
        for cmd in commands:
            input_widget.value = cmd
            await self.on_input_submitted(Input.Submitted(input_widget, cmd))
            await asyncio.sleep(0.5)
        self.notify("Macro playback finished.")

    # --- UI Helpers ---

    def _add_message(self, role: str, content: str) -> MessageContent:
        """Mounts a new message bubble in the chat scroll area."""
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        bubble = MessageBubble(role=role)
        chat_scroll.mount(bubble)
        content_widget = bubble.query_one(MessageContent)
        content_widget.update(content)
        chat_scroll.scroll_end(animate=True)
        return content_widget

    def _load_history_to_chat(self, history: List[Dict[str, Any]]):
        """Reconstructs the chat UI from a history list."""
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        for child in list(chat_scroll.children):
            child.remove()
        
        chat_scroll.mount(Static("Session history loaded.", classes="welcome-msg"))

        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # Format tool parts for display
            if "parts" in msg:
                for part in msg["parts"]:
                    if "function_call" in part:
                        fc = part["function_call"]
                        content = f"> 🛠️ **Executing:** `{fc['name']}` with args: `{fc['args']}`"
                        role = "model"
                    elif "function_response" in part:
                        fr = part["function_response"]
                        result_display = str(fr["response"].get("result", "(no result)"))
                        if len(result_display) > 500:
                            result_display = result_display[:500] + "\n... (truncated)"
                        content = f"```text\n{result_display}\n```\n"
                        role = "model"
            
            if content:
                self._add_message(role, content)

    # --- AI Orchestration ---

    @work(exclusive=True)
    async def generate_response(self) -> None:
        """Background worker that handles LLM generation and tool execution loop."""
        stats = self.query_one("#stats-panel", StatsPanel)
        tool_status = self.query_one("#tool-status", ToolStatus)
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        
        # Start a new bubble for this generation session
        model_bubble = MessageBubble(role="model")
        await chat_scroll.mount(model_bubble)
        
        current_text_widget = model_bubble.query_one(MessageContent)
        current_text_buffer = ""
        
        # Optimization: Dynamic Throttling
        last_update_time = 0
        
        # Base interval
        base_interval = 0.05 

        start_time = time.monotonic()
        stats.status = "Generating"
        stats.latency = 0.0
        tool_status.set_status("Thinking...", running=True)
        
        try:
            if not self.router.providers:
                await self.router.reload_providers()
                
            if not self.router.providers:
                stats.model_name = "None"
                tool_status.set_status("No active provider.", running=False)
                current_text_widget.update(
                    "[ERROR] No LLM providers configured or available.\n\n"
                    "Please check your API keys and provider settings using `/config list`."
                )
                return
                
            if self.router.active_provider_index >= len(self.router.providers):
                self.router.active_provider_index = 0
                
            active_provider = self.router.providers[self.router.active_provider_index]
            stats.model_name = active_provider.name
        except Exception as e:
            logger.error(f"Initialization error in generate_response: {e}")
            current_text_widget.update(f"[ERROR] Failed to initialize providers: {e}")
            return

        try:
            while True:
                tool_called = False
                
                async for chunk in self.router.route(self.history):
                    stats.latency = time.monotonic() - start_time
                    
                    if isinstance(chunk, RouterEvent):
                        if chunk.type == RouterEvent.FAILOVER:
                            new_name = chunk.data or "Backup"
                            stats.model_name = new_name
                            warning = Static(f"⚠️ FAILOVER: SWITCHING TO [bold]{new_name}[/bold]...", classes="failover-warning")
                            await chat_scroll.mount(warning)
                            chat_scroll.scroll_end(animate=False)
                        elif chunk.type == RouterEvent.RETRY:
                            data = chunk.data
                            retry_msg = f"⏳ [yellow]RATE LIMIT HIT[/yellow] on {data['provider']}. Retrying ({data['attempt']}/{data['max']})..."
                            tool_status.set_status(retry_msg, running=True)
                        continue
                    
                    if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                        if current_text_buffer.strip():
                            current_text_widget.update(current_text_buffer)
                            self.history.append({"role": "model", "content": current_text_buffer})
                            current_text_buffer = "" 

                        tool_name = chunk["name"]
                        args = chunk["args"]
                        tool_id = chunk.get("id", f"call_{int(time.time())}")
                        
                        tool_instance = self.router.get_tool(tool_name)
                        if tool_instance and tool_instance.is_critical:
                            tool_status.set_status(f"WAITING FOR CONFIRMATION: {tool_name}", running=False)
                            # ConfirmToolCall returns: "confirm", "skip", "stop"
                            action = await self.push_screen_wait(ConfirmToolCall(tool_name, args))
                            
                            if action == "stop":
                                tool_status.set_status("Stopped", running=False)
                                current_text_widget.update(current_text_buffer + "\n\n[Stopped by User]")
                                stats.status = "Idle"
                                return # Exit generation loop
                            
                            elif action == "skip":
                                result = "Action skipped by user."
                                tool_status.set_status("Skipped", running=False)
                            
                            else: # "confirm"
                                tool_status.set_status(f"EXECUTING: {tool_name}", running=True)
                                result = await self.router.providers[self.router.active_provider_index].execute_tool(tool_name, args)
                        else:
                            tool_status.set_status(f"EXECUTING: {tool_name}", running=True)
                            result = await self.router.providers[self.router.active_provider_index].execute_tool(tool_name, args)
                        
                        try:
                            self.query_one("#file-tree", DirectoryTree).reload()
                        except Exception:
                            pass 

                        tool_widget = ToolOutput(tool_name, str(args), str(result))
                        await model_bubble.mount(tool_widget)
                        tool_status.set_status("Ready", running=False)
                        
                        self.history.append({
                            "role": "model", 
                            "parts": [{"function_call": {"name": tool_name, "args": args, "id": tool_id}}]
                        }) 
                        self.history.append({
                            "role": "user", 
                            "parts": [{"function_response": {"name": tool_name, "response": {"result": result}, "id": tool_id}}]
                        })
                        
                        current_text_widget = MessageContent("")
                        await model_bubble.mount(current_text_widget)
                        last_update_time = 0 # Reset throttling for new widget
                        
                        tool_called = True
                        break 
                    
                    if isinstance(chunk, str):
                        current_text_buffer += chunk
                        
                        now = time.monotonic()
                        
                        # Dynamic Throttling (Tweaked for better performance):
                        buf_len = len(current_text_buffer)
                        if buf_len < 1000: update_interval = 0.1
                        elif buf_len < 3000: update_interval = 0.2
                        elif buf_len < 8000: update_interval = 0.5
                        else: update_interval = 1.0
                        
                        if now - last_update_time > update_interval:
                            dist_from_bottom = chat_scroll.max_scroll_y - chat_scroll.scroll_y
                            should_scroll = dist_from_bottom <= 2 or last_update_time == 0
                            
                            current_text_widget.update(current_text_buffer)
                            
                            if should_scroll:
                                # Scroll the WIDGET into view, which is more reliable for "pushing up"
                                self.call_after_refresh(current_text_widget.scroll_visible, animate=False, top=False)
                                
                            last_update_time = now

                if not tool_called:
                    current_text_widget.update(current_text_buffer)
                    # Final scroll to ensure bottom is visible
                    self.call_after_refresh(current_text_widget.scroll_visible, animate=False, top=False)
                    if current_text_buffer.strip():
                        self.history.append({"role": "model", "content": current_text_buffer})
                    break

            tool_status.set_status("Ready", running=False)
            stats.status = "Idle"
            
        except Exception as e:
            current_text_widget.update(f"\n\n[ERROR]: {str(e)}")
            tool_status.set_status("Error", running=False)
            stats.status = "Error"

def run(sandbox_enabled: bool = False):
    """Entry point to start the Plexir TUI application."""
    app = PlexirApp(sandbox_enabled=sandbox_enabled)
    app.run()

if __name__ == "__main__":
    run()