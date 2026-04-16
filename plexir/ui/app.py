"""
Main application class for the Plexir TUI.
Orchestrates the UI, router, and command processing.
"""

import asyncio
import logging
import os
import time
import threading
from typing import List, Dict, Any, Optional
import subprocess

from textual.app import App, ComposeResult
from textual.widgets import Label, Static, Footer, DirectoryTree, Collapsible, LoadingIndicator, TextArea
from textual.containers import VerticalScroll
from textual.theme import Theme
from textual import work, on, events

from plexir.ui.widgets import MessageContent, ToolStatus, StatsPanel, MessageBubble, ToolOutput
from plexir.ui.app_layout import compose_main_layout
from plexir.ui.screens import ConfirmToolCall, SandboxSyncScreen
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
        ("ctrl+enter", "submit", "Submit"),
    ]

    def __init__(self, sandbox_enabled: bool = False, mount_cwd: bool = False, yolo_mode: bool = False):
        super().__init__()
        self.register_theme(self.TOKYO_NIGHT)
        self.register_theme(self.HACKER)
        self.register_theme(self.PLEXIR_LIGHT)
        
        # Unique session ID for this run
        self.session_id = time.strftime("%Y%m%d_%H%M%S")
        self.router = Router(
            sandbox_enabled=sandbox_enabled, 
            mount_cwd=mount_cwd, 
            session_id=self.session_id
        )
        self.session_manager = SessionManager()
        self.command_processor = CommandProcessor(self, self.session_manager)
        self.history: List[Dict[str, Any]] = []
        self.generation_worker = None
        
        # Modes
        self.yolo_mode = yolo_mode
        if self.yolo_mode:
            logger.info("YOLO Mode enabled: HITL disabled.")
        
        # Macro state
        self.is_recording_macro = False
        self.current_macro_name: Optional[str] = None
        self.recorded_commands: List[str] = []

        # Queue state
        self.message_queue_list: List[str] = []
        self.queue_condition = asyncio.Condition()
        self.queued_bubbles: List[tuple[str, MessageBubble]] = []

    async def on_mount(self) -> None:
        """Initializes providers, UI state, and theme on startup."""
        await self.router.reload_providers()
        
        stats = self.query_one("#stats-panel", StatsPanel)
        stats.sandbox_active = self.router.sandbox_enabled
        
        # Set initial model name
        if self.router.providers:
            stats.model_name = self.router.providers[self.router.active_provider_index].name

        initial_theme = config_manager.config.theme or "tokyo-night"
        
        # Migration for old theme names
        theme_map = {"dark": "tokyo-night", "light": "plexir-light"}
        initial_theme = theme_map.get(initial_theme, initial_theme)
            
        try:
            self.theme = initial_theme
        except Exception:
            self.theme = "tokyo-night"

        # Start queue processor in background worker
        self.process_queue()

    def compose(self) -> ComposeResult:
        """Composes the main application layout."""
        yield from compose_main_layout()

    async def push_screen_wait(self, screen: Any) -> Any:
        """Pushes a modal screen and waits for its result."""
        future: asyncio.Future = asyncio.Future()
        
        def on_dismiss(result: Any) -> None:
            if not future.done():
                if self._thread_id == threading.get_ident():
                    future.set_result(result)
                else:
                    self.call_from_thread(future.set_result, result)
        
        # Check if we are already in the main thread
        if self._thread_id == threading.get_ident():
            self.push_screen(screen, callback=on_dismiss)
        else:
            self.call_from_thread(self.push_screen, screen, on_dismiss)
            
        return await future

    # --- Actions ---

    async def action_reload_providers(self):
        """Reloads LLM providers from configuration."""
        await self.router.reload_providers()
        
        # Update model name in UI
        stats = self.query_one("#stats-panel", StatsPanel)
        if self.router.providers:
            stats.model_name = self.router.providers[self.router.active_provider_index].name
        else:
            stats.model_name = "None"
            
        self.notify("Providers reloaded from config.")
        self.query_one("#user-input", TextArea).focus()

    def action_toggle_sidebar(self):
        """Toggles sidebar visibility."""
        sidebar = self.query_one("#sidebar")
        sidebar.toggle_class("-hidden")
        self.query_one("#user-input", TextArea).focus()

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

    def action_quit(self):
        """Triggers the exit sequence."""
        self.handle_exit()

    @work
    async def handle_exit(self):
        """Cleanly exits the application, handling sandbox sync/stop."""
        if self.router.sandbox:
            # If in Clone Mode, prompt user to sync/export
            if not self.router.mount_cwd:
                action = await self.push_screen_wait(SandboxSyncScreen())
                
                if action == "cancel":
                    self.notify("Exit cancelled.")
                    return
                
                elif action == "sync_cwd":
                    self.notify("Syncing sandbox to current directory...")
                    try:
                        await self.router.sandbox.export_workspace(os.getcwd())
                        self.notify("Sync complete.", severity="information")
                    except Exception as e:
                        self.notify(f"Sync failed: {e}", severity="error")
                        return
                
                elif action.startswith("export:"):
                    path = action.split(":", 1)[1]
                    self.notify(f"Exporting sandbox to {path}...")
                    try:
                        await self.router.sandbox.export_workspace(path)
                        self.notify("Export complete.", severity="information")
                    except Exception as e:
                        self.notify(f"Export failed: {e}", severity="error")
                        return

            self.notify("Stopping sandbox container...")
            await self.router.sandbox.stop()
            
        self.exit()

    def action_focus_input(self):
        """Focuses the main command input."""
        self.query_one("#user-input", TextArea).focus()

    async def action_run_interactive(self, command: List[str]) -> int:
        """Runs a command in the terminal, suspending the TUI."""
        with self.suspend():
            # Clear screen
            print("\033[H\033[J", end="")
            print(f"Running: {' '.join(command)}")
            try:
                # Use synchronous subprocess.run because TUI loop is paused
                result = subprocess.run(command)
                return_code = result.returncode
            except FileNotFoundError:
                print(f"Error: Command not found: {command[0]}")
                return_code = 127
            except KeyboardInterrupt:
                print("\nAborted by user.")
                return_code = 130
            
            return return_code

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

    def action_submit(self):
        """Submits the current input via Ctrl+J or Ctrl+Enter."""
        text_area = self.query_one("#user-input", TextArea)
        user_text = text_area.text
        if not user_text.strip():
            return
        
        text_area.text = ""
        
        # Immediate UI feedback: Mount a "queued" bubble
        bubble = MessageBubble(role="user", content=user_text)
        bubble.add_class("queued")
        self.query_one("#chat-scroll", VerticalScroll).mount(bubble)
        self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=True)

        self.queued_bubbles.append((user_text, bubble))
        asyncio.create_task(self._add_to_queue(user_text))

    async def _add_to_queue(self, text: str):
        """Adds a message to the internal queue and notifies the processor."""
        async with self.queue_condition:
            self.message_queue_list.append(text)
            self.queue_condition.notify_all()

    # --- Event Handlers ---

    def on_key(self, event: events.Key) -> None:
        """Handles global key events, specifically for multi-line input submission."""
        if event.key == "ctrl+enter":
            if self.focused and self.focused.id == "user-input":
                event.stop()
                self.action_submit()

    @on(MessageBubble.Clicked)
    async def on_bubble_clicked(self, event: MessageBubble.Clicked) -> None:
        """Moves the clicked message and all subsequent queued messages back to the input."""
        bubble = event.bubble
        if "queued" not in bubble.classes:
            return
        
        # Find which queued message this is
        target_idx = -1
        for i, (text, b) in enumerate(self.queued_bubbles):
            if b == bubble:
                target_idx = i
                break
        
        if target_idx == -1:
            return

        # We pull back EVERYTHING from target_idx to the end
        async with self.queue_condition:
            # 1. Identify chunks to pull back
            to_pull_back = self.queued_bubbles[target_idx:]
            
            # 2. Update internal lists
            self.message_queue_list = self.message_queue_list[:target_idx]
            self.queued_bubbles = self.queued_bubbles[:target_idx]
            
            # 3. Concatenate text and remove bubbles from UI
            texts = []
            for text, b in to_pull_back:
                texts.append(text)
                b.remove()
            
            combined_text = "\n\n".join(texts)
            
            # 4. Move text to main input and focus
            input_widget = self.query_one("#user-input", TextArea)
            
            # If input already has text, append with double newline
            if input_widget.text.strip():
                input_widget.text = input_widget.text.rstrip() + "\n\n" + combined_text
            else:
                input_widget.text = combined_text
                
            input_widget.focus()
            # Move cursor to end
            final_text = input_widget.text
            input_widget.move_cursor((len(final_text.split("\n")) - 1, len(final_text.split("\n")[-1])))
            
            self.notify(f"Pulled back {len(to_pull_back)} message(s) for editing.")

    @on(TextArea.Changed, "#user-input")
    def on_input_changed(self, event: TextArea.Changed) -> None:
        """Adjusts the input height based on the number of lines."""
        text_area = event.text_area
        # Calculate lines. If empty, count as 1.
        line_count = len(text_area.text.split("\n"))
        
        # Base height of 5 (matching old min-height) + dynamic growth
        # 1 line -> 5 height
        # 2 lines -> 6 height
        # ...
        # 5+ lines -> 9 height (capped)
        new_height = min(line_count, 5) + 4
        
        input_container = self.query_one("#input-container")
        input_container.styles.height = new_height


    @work(exclusive=True)
    async def process_queue(self):
        """Sequentially processes messages from the queue in a background worker."""
        while True:
            async with self.queue_condition:
                while not self.message_queue_list:
                    await self.queue_condition.wait()
                user_text = self.message_queue_list.pop(0)
            
            try:
                await self.handle_user_message(user_text)
            except Exception as e:
                logger.error(f"Error in process_queue: {e}")

    async def handle_user_message(self, user_text: str):
        """Processes a single user message."""
        input_widget = self.query_one("#user-input", TextArea)
        
        # Pull from queued_bubbles if available
        bubble = None
        if self.queued_bubbles and self.queued_bubbles[0][0] == user_text:
            _, bubble = self.queued_bubbles.pop(0)
            bubble.remove_class("queued")
        
        # 1. Process slash commands
        command_response = await self.command_processor.process(user_text)
        if command_response:
             if bubble: 
                 bubble.remove() # Don't keep command bubble usually?
             
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

             # For other commands, we show the command and response
             self._add_message("user", user_text)
             self._add_message("system", command_response)
             input_widget.focus()
             return

        # 2. Add to history and update UI
        self.history.append({"role": "user", "content": user_text})
        if not bubble:
            self._add_message("user", user_text)

        # 3. Trigger AI response and WAIT for it to finish
        try:
            self.generation_worker = self.generate_response()
            await self.generation_worker.wait()
        except Exception as e:
            logger.debug(f"Generation worker ended: {e}")

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Persists theme changes to configuration when updated."""
        if new_theme != old_theme:
            try:
                config_manager.update_app_setting("theme", new_theme)
                logger.info(f"Theme persisted: {new_theme}")
            except Exception as e:
                logger.error(f"Failed to persist theme change: {e}")

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
        for cmd in commands:
            # Mount bubbles for macro commands so they show as queued
            bubble = MessageBubble(role="user", content=cmd)
            bubble.add_class("queued")
            self.query_one("#chat-scroll", VerticalScroll).mount(bubble)
            
            self.queued_bubbles.append((cmd, bubble))
            await self._add_to_queue(cmd)
            
            # small delay to avoid UI hammer
            await asyncio.sleep(0.05)
        
        self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=True)
        self.notify("Macro playback queued.")

    # --- UI Helpers ---

    def _add_message(self, role: str, content: str) -> MessageBubble:
        """Adds a message to the chat scroll."""
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        bubble = MessageBubble(role=role, content=content)
        chat_scroll.mount(bubble)
        
        chat_scroll.scroll_end(animate=True)
        return bubble

    def _load_history_to_chat(self, history: List[Dict[str, Any]]):
        """Reconstructs the chat UI from a history list."""
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        for child in list(chat_scroll.children):
            child.remove()
        
        chat_scroll.mount(Static("Session history loaded.", classes="welcome-msg"))
        verbosity = config_manager.config.verbosity

        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            
            # 1. Handle tool parts
            if "parts" in msg:
                # We want to display tool calls as ToolOutput widgets
                # and tool responses as results.
                model_bubble = MessageBubble(role="model", content="")
                chat_scroll.mount(model_bubble)

                for part in msg["parts"]:
                    if "function_call" in part:
                        fc = part["function_call"]
                        model_bubble.mount(ToolOutput(fc['name'], str(fc['args']), "(Reloaded)"))
                    elif "function_response" in part:
                        fr = part["function_response"]
                        res_obj = fr.get("response", {})
                        result_display = str(res_obj.get("result", "(no result)"))
                        
                        if verbosity == 0 and len(result_display) > 1000:
                            result_display = result_display[:1000] + "\n... (truncated)"
                        
                        model_bubble.mount(MessageContent(f"```text\n{result_display}\n```"))
                continue

            # 2. Handle thinking tags in content
            if content and "<think>" in content:
                bubble = MessageBubble(role=role, content="")
                chat_scroll.mount(bubble)
                
                parts = content.split("<think>")
                # pre-think
                if parts[0].strip():
                    bubble.mount(MessageContent(parts[0]))
                
                for p in parts[1:]:
                    if "</think>" in p:
                        thought, rest = p.split("</think>", 1)
                        is_collapsed = not config_manager.config.expanded_reasoning
                        bubble.mount(Collapsible(MessageContent(thought), title="Reasoning Process", collapsed=is_collapsed))
                        if rest.strip():
                            bubble.mount(MessageContent(rest))
                    else:
                        bubble.mount(MessageContent(f"<think>{p}"))
                continue

            if content:
                self._add_message(role, content)
        
        chat_scroll.scroll_end(animate=False)

    # --- AI Orchestration ---

    @work
    async def generate_response(self) -> None:
        """Background worker that handles LLM generation and tool execution loop."""
        stats = self.query_one("#stats-panel", StatsPanel)
        tool_status = self.query_one("#tool-status", ToolStatus)
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        
        # Start a new bubble for this generation session
        model_bubble = MessageBubble(role="model", content="")
        await chat_scroll.mount(model_bubble)
        
        # Give a tiny bit of time for compose
        await asyncio.sleep(0.01)
        current_text_widget = model_bubble.query_one("#message-text", MessageContent)
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
                
                # Reasoning state
                reasoning_content = ""
                is_thinking = False
                
                async for chunk in self.router.route(self.history):
                    stats.latency = time.monotonic() - start_time
                    
                    if isinstance(chunk, RouterEvent):
                        if chunk.type == RouterEvent.FAILOVER:
                            new_name = chunk.data or "Backup"
                            stats.model_name = new_name
                            warning = Static(f"⚠️ FAILOVER: SWITCHING TO [bold]{new_name}[/bold]...", classes="failover-warning")
                            await chat_scroll.mount(warning)
                            chat_scroll.scroll_end(animate=False)
                            # Reset buffer for new stream
                            current_text_buffer = ""
                            current_text_widget.update("")

                        elif chunk.type == RouterEvent.RETRY:
                            data = chunk.data
                            retry_msg = f"⏳ [yellow]RATE LIMIT HIT[/yellow] on {data['provider']}. Retrying ({data['attempt']}/{data['max']})..."
                            tool_status.set_status(retry_msg, running=True)
                            # Reset buffer for retry
                            current_text_buffer = ""
                            current_text_widget.update("")

                        elif chunk.type == RouterEvent.USAGE:
                            data = chunk.data
                            stats.ctx_tokens = data.get("last_context_tokens", 0)
                            stats.total_tokens = self.router.session_usage["total_tokens"]
                            stats.cost = self.router.session_usage["total_cost"]
                        
                        elif chunk.type == "system":
                            # Handle system messages from router (like pruning notice)
                            self.notify(chunk.data)
                            notice = Static(f"ℹ️ {chunk.data}", classes="system-notice")
                            await chat_scroll.mount(notice)
                            chat_scroll.scroll_end(animate=True)
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
                            if self.yolo_mode:
                                tool_status.set_status(f"YOLO: EXECUTING {tool_name}", running=True)
                                result = await self.router.providers[self.router.active_provider_index].execute_tool(tool_name, args)
                            else:
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
                        
                        # Optimize: Only reload file tree for modifying tools
                        modifying_prefixes = ("write", "edit", "git", "run_shell", "python_sandbox")
                        if tool_name.startswith(modifying_prefixes):
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
                        text_to_process = chunk
                        while text_to_process:
                            if not is_thinking:
                                if "<think>" in text_to_process:
                                    pre, post = text_to_process.split("<think>", 1)
                                    current_text_buffer += pre
                                    is_thinking = True
                                    tool_status.set_status("Thinking...", running=True)
                                    text_to_process = post
                                    
                                    # Update visible text before thinking
                                    current_text_widget.update(current_text_buffer)
                                else:
                                    current_text_buffer += text_to_process
                                    text_to_process = ""
                            else: # is_thinking
                                if "</think>" in text_to_process:
                                    thought, post = text_to_process.split("</think>", 1)
                                    reasoning_content += thought
                                    is_thinking = False
                                    
                                    # Render reasoning
                                    if reasoning_content.strip():
                                        is_collapsed = not config_manager.config.expanded_reasoning
                                        reasoning_widget = Collapsible(
                                            MessageContent(reasoning_content), 
                                            title="Reasoning Process",
                                            collapsed=is_collapsed
                                        )
                                        await model_bubble.mount(reasoning_widget)
                                        
                                        # Create new text widget for post-reasoning content
                                        current_text_widget = MessageContent("")
                                        await model_bubble.mount(current_text_widget)
                                        current_text_buffer = "" 
                                        last_update_time = 0

                                    tool_status.set_status("Generating", running=True)
                                    text_to_process = post
                                else:
                                    reasoning_content += text_to_process
                                    text_to_process = ""

                        # Update UI if not thinking
                        if not is_thinking:
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
                                    # Scroll the WIDGET into view
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
            self.refresh()
            
        except Exception as e:
            current_text_widget.update(f"\n\n[ERROR]: {str(e)}")
            tool_status.set_status("Error", running=False)
            stats.status = "Error"
            self.refresh()

def run(sandbox_enabled: bool = False, mount_cwd: bool = False, yolo_mode: bool = False):
    """Entry point to start the Plexir TUI application."""
    app = PlexirApp(sandbox_enabled=sandbox_enabled, mount_cwd=mount_cwd, yolo_mode=yolo_mode)
    app.run()

if __name__ == "__main__":
    run()