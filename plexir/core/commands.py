"""
Slash command processing for the Plexir TUI.
Handles user-entered commands starting with '/'.
"""

import asyncio
import shlex
import os
import sys
from typing import List, Optional
from plexir.core.config_manager import config_manager, ProviderConfig
from plexir.core.session import SessionManager

class CommandProcessor:
    """
    Parses and executes slash commands, interacting with config, sessions, and macros.
    """
    
    def __init__(self, app, session_manager: SessionManager):
        """
        Initializes the CommandProcessor. 
        
        Args:
            app: The main PlexirApp instance.
            session_manager: The session manager instance.
        """
        self.app = app
        self.session_manager = session_manager

    async def process(self, text: str) -> Optional[str]:
        """
        Processes a line of input. If it's a command, executes it and returns a response.
        
        Args:
            text: The raw user input string.
        """
        if not text.startswith("/"):
            if self.app.is_recording_macro:
                self.app.record_macro_command(text)
            return None

        try:
            parts = shlex.split(text)
        except ValueError as e:
            return f"Error parsing command: {e}"

        if not parts:
            return None

        cmd = parts[0].lower()
        args = parts[1:]

        # Record command if macro recording is active (except /macro itself)
        if self.app.is_recording_macro and cmd != "/macro":
            self.app.record_macro_command(text)
            
        if cmd == "/help":
            return self._help()
        elif cmd == "/clear":
            return self._clear()
        elif cmd == "/tools":
            return self._tools()
        elif cmd == "/config":
            return await self._config(args)
        elif cmd == "/session":
            return await self._session(args)
        elif cmd == "/macro":
            return self._macro(args)
        elif cmd == "/auth":
            return await self._auth(args)
        elif cmd == "/yolo":
            return self._yolo(args)
        elif cmd == "/reload":
            await self.app.action_reload_providers()
            return "Providers reloaded from config."
        elif cmd in ("/quit", "/exit"):
            await self.app.action_quit()
            return "Exiting..."
        else:
            return f"Unknown command: {cmd}. Type /help for list."

    def _help(self) -> str:
        """Returns the general help message."""
        return """
**Plexir Commands:**
- `/help`: Show this help message.
- `/clear`: Clear the session history.
- `/tools`: List available tools.
- `/config [subcommand]`: Manage application settings.
- `/auth [subcommand]`: Manage Google OAuth (ADC).
- `/session [subcommand]`: Manage conversation sessions.
- `/macro [subcommand]`: Manage user input macros.
- `/reload`: Reload LLM providers from configuration.
- `/quit`: Exit the application.
"""

    def _clear(self) -> str:
        """Clears the current session history."""
        self.app.history = []
        self.session_manager.current_session_file = None
        self.app.router.reset_provider()
        return "Session history cleared."

    # --- Auth Management ---

    async def _auth(self, args: List[str]) -> str:
        """Handles /auth subcommands for Google OAuth."""
        if not args or args[0] == "help":
            return self._auth_help()
        
        subcommand = args[0].lower()
        
        if subcommand == "login":
            return (
                "⚠️ **Authentication Required**\n\n"
                "To authenticate with Google and unlock high quotas (1000 req/day):\n"
                "1. Open a **NEW** terminal window.\n"
                "2. Run this command:\n"
                f"`{sys.executable} -m plexir.auth_helper`\n"
                "3. Follow the browser instructions to log in.\n"
                "4. Return here and run: `/reload`."
            )

        elif subcommand == "status":
            adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            standalone_path = os.path.expanduser("~/.plexir/oauth_creds.json")
            gemini_cli_path = os.path.expanduser("~/.gemini/oauth_creds.json")
            
            msg = "**Authentication Status:**\n"
            if os.path.exists(standalone_path):
                msg += f"- ✅ Standalone Credentials: `{standalone_path}`\n"
            if os.path.exists(gemini_cli_path):
                msg += f"- ✅ Gemini CLI Credentials: `{gemini_cli_path}`\n"
            if os.path.exists(adc_path):
                msg += f"- ✅ ADC (gcloud) Credentials: `{adc_path}`\n"
            
            if "✅" not in msg:
                return "❌ No credentials found. Run `/auth login`."
            return msg
        
        elif subcommand == "project":
            if not args:
                return "Usage: `/auth project <PROJECT_ID>` (Sets the quota project for ADC)."
            
            project_id = args[0]
            cmd = ["gcloud", "auth", "application-default", "set-quota-project", project_id]
            try:
                ret_code = await self.app.action_run_interactive(cmd)
                if ret_code == 0:
                    return f"✅ Quota project set to '{project_id}'."
                else:
                    return f"❌ Failed to set quota project (Code {ret_code})."
            except Exception as e:
                return f"Error: {e}"

        else:
            return f"Unknown subcommand: {subcommand}"

    def _auth_help(self) -> str:
        return """
**`/auth` Commands:**
- `/auth login`: Show instructions for authentication.
- `/auth status`: Check for existing credentials.
- `/auth project <id>`: Set the quota project for ADC (Vertex).
"""

    def _auth_help(self) -> str:
        return """
**`/auth` Commands:**
- `/auth login`: Authenticate with Google. 
  - (Priority 1) Uses `~/.plexir/client_secrets.json` if present.
  - (Priority 2) Falls back to `gcloud auth application-default login`.
- `/auth status`: Check for existing credentials.
"""

    # --- YOLO Mode ---

    def _yolo(self, args: List[str]) -> str:
        """Handles /yolo subcommands."""
        if not args or args[0] == "help":
            return self._yolo_help()
        
        subcommand = args[0].lower()
        if subcommand == "start":
            self.app.yolo_mode = True
            return "🚀 YOLO Mode ENABLED. HITL confirmations disabled. Be careful!"
        elif subcommand == "stop":
            self.app.yolo_mode = False
            return "🛑 YOLO Mode DISABLED. HITL confirmations re-enabled."
        elif subcommand == "status":
            state = "ENABLED" if self.app.yolo_mode else "DISABLED"
            return f"YOLO Mode is currently **{state}**."
        else:
            return f"Unknown subcommand: {subcommand}"

    def _yolo_help(self) -> str:
        return """
**`/yolo` Commands:**
- `/yolo start`: Enable YOLO mode (disable safety checks).
- `/yolo stop`: Disable YOLO mode (enable safety checks).
- `/yolo status`: Check status.
"""

    def _tools(self) -> str:
        """Lists all registered tools."""
        tools = self.app.router.registry.list_tools()
        msg = "**Available Tools:**\n"
        if not tools:
            msg += "No tools registered.\n"
        else:
            for t in tools:
                msg += f"- `{t.name}`: {t.description}\n"
        return msg
    
    # --- Config Management ---

    async def _config(self, args: List[str]) -> str:
        """Handles /config subcommands."""
        if not args or args[0] == "help":
            return self._config_help()
        
        subcommand = args[0].lower()
        sub_args = args[1:]

        try:
            if subcommand == "list":
                return self._config_list()
            elif subcommand == "set":
                return await self._config_set(sub_args)
            elif subcommand == "add":
                return await self._config_add(sub_args)
            elif subcommand == "delete":
                return await self._config_delete(sub_args)
            elif subcommand == "reorder":
                return await self._config_reorder(sub_args)
            elif subcommand == "debug":
                return self._config_debug(sub_args)
            elif subcommand == "budget":
                return self._config_budget(sub_args)
            elif subcommand == "tool":
                return self._config_tool(sub_args)
            else:
                return f"Unknown /config subcommand: {subcommand}."
        except Exception as e:
            return f"[ERROR] Config error: {e}"

    def _config_budget(self, args: List[str]) -> str:
        """Sets the session cost limit."""
        if not args: return "Usage: `/config budget <value>`"
        try:
            val = float(args[0])
            config_manager.update_app_setting("session_budget", val)
            return f"Session budget set to ${val:.2f}."
        except ValueError:
            return "Error: Budget must be a number."

    def _config_help(self) -> str:
        """Returns help for /config command."""
        return """
**`/config` Commands:**
- `/config list`: List all providers and failover order.
- `/config set <name> <key> <value>`: Set a provider property.
- `/config tool <domain> <key> <value>`: Set a tool property (e.g. `tool git token X`).
- `/config add <name> <type> <model> [api_key=<key>] [base_url=<url>]`: Add new provider.
- `/config delete <name>`: Delete a provider.
- `/config reorder <name> <up|down>`: Change failover order.
- `/config debug <on|off>`: Toggle debug mode.
- `/config budget <value>`: Set session cost limit (e.g. 0.50). 0 for no limit.
"""

    def _config_tool(self, args: List[str]) -> str:
        """Configures tool settings."""
        if len(args) < 3:
            return "Usage: `/config tool <domain> <key> <value>`"
        domain, key, value = args[0], args[1], " ".join(args[2:])
        config_manager.set_tool_config(domain, key, value)
        return f"Tool config updated: {domain}.{key} = {value}"

    def _config_list(self) -> str:
        """Lists current configuration settings."""
        msg = "**Current Configuration:**\n\n"
        msg += "--- Providers (Failover Order) ---\n"
        order = config_manager.config.active_provider_order
        for i, name in enumerate(order):
            p = config_manager.get_provider_config(name)
            if p:
                key_status = "Set" if p.api_key else "Not Set"
                msg += f"{i+1}. **{p.name}** ({p.type}): Model='{p.model_name}' (Key: {key_status})\n"
        
        msg += "\n--- Application Settings ---\n"
        msg += f"Theme: `{config_manager.config.theme}`\n"
        msg += f"Debug Mode: `{'On' if config_manager.config.debug_mode else 'Off'}`\n"
        msg += f"Session Budget: `${config_manager.config.session_budget:.2f}`\n"
        
        # Tool specific configs
        if config_manager.config.tool_configs:
            msg += "\n--- Tool Configurations ---\n"
            for domain, settings in config_manager.config.tool_configs.items():
                msg += f"[{domain.upper()}]\n"
                for k, v in settings.items():
                    # Mask tokens/keys
                    display_v = v if "key" not in k.lower() and "token" not in k.lower() else "********"
                    msg += f"  - {k}: {display_v}\n"

        return msg

    async def _config_set(self, args: List[str]) -> str:
        """Updates a provider property."""
        if len(args) < 3:
            return "Usage: `/config set <name> <key> <value>`"
        
        name, key, value = args[0], args[1], " ".join(args[2:])
        p_config = config_manager.get_provider_config(name)
        if not p_config:
            return f"Error: Provider '{name}' not found."
        
        if key == "api_key": p_config.api_key = value
        elif key == "model_name": p_config.model_name = value
        elif key == "base_url": p_config.base_url = value
        elif key == "type":
             if value not in ("gemini", "openai", "groq", "ollama", "mcp"):
                 return f"Error: Invalid type '{value}'."
             p_config.type = value
        elif key == "auth_mode":
            if value not in ("auto", "api_key", "oauth"):
                return f"Error: Invalid auth_mode '{value}'. Use: auto, api_key, oauth."
            p_config.auth_mode = value
        else:
            return f"Error: Unknown property '{key}'."
        
        config_manager.update_provider(name, p_config)
        await self.app.action_reload_providers()
        return f"Updated '{key}' for provider '{name}'."

    async def _config_add(self, args: List[str]) -> str:
        """Adds a new provider to the configuration."""
        if len(args) < 3:
            return "Usage: `/config add <name> <type> <model> [api_key=...] [base_url=...]`"

        name, type_val, model = args[0], args[1].lower(), args[2]
        api_key, base_url = None, None

        for arg in args[3:]:
            if arg.startswith("api_key="): api_key = arg.split("=", 1)[1]
            elif arg.startswith("base_url="): base_url = arg.split("=", 1)[1]

        if type_val not in ("gemini", "openai", "groq", "ollama", "mcp"):
            return f"Error: Invalid type '{type_val}'."

        new_p = ProviderConfig(name=name, type=type_val, model_name=model, api_key=api_key, base_url=base_url)
        config_manager.add_provider(new_p)
        await self.app.action_reload_providers()
        return f"Provider '{name}' added."

    async def _config_delete(self, args: List[str]) -> str:
        """Deletes a provider from the configuration."""
        if not args: return "Usage: `/config delete <name>`"
        name = args[0]
        try:
            config_manager.delete_provider(name)
            await self.app.action_reload_providers()
            return f"Provider '{name}' deleted."
        except Exception as e:
            return f"Error: {e}"

    async def _config_reorder(self, args: List[str]) -> str:
        """Changes the priority of a provider in the failover order."""
        if len(args) < 2: return "Usage: `/config reorder <name> <up|down>`"
        name, direction = args[0], args[1].lower()
        try:
            config_manager.reorder_provider(name, direction)
            await self.app.action_reload_providers()
            return f"Provider '{name}' moved {direction}."
        except Exception as e:
            return f"Error: {e}"

    def _config_debug(self, args: List[str]) -> str:
        """Toggles debug mode on or off."""
        if not args: return "Usage: `/config debug <on|off>`"
        state = args[0].lower()
        if state in ("on", "off"):
            config_manager.update_app_setting("debug_mode", state == "on")
            return f"Debug mode set to {state}."
        return "Error: State must be 'on' or 'off'."

    # --- Session Management ---

    async def _session(self, args: List[str]) -> str:
        """Handles /session subcommands."""
        if not args or args[0] == "help":
            return self._session_help()
        
        subcommand = args[0].lower()
        sub_args = args[1:]

        try:
            if subcommand == "save":
                return await self.session_manager.save_session_async(self.app.history, sub_args[0] if sub_args else None)
            elif subcommand == "load":
                if not sub_args: return "Usage: `/session load <name>`"
                name = sub_args[0]
                self.app.history = self.session_manager.load_session(name)
                return f"Session '{name}' loaded. Chat history updated."
            elif subcommand == "list":
                sessions = self.session_manager.list_sessions()
                return "**Saved Sessions:**\n" + "\n".join([f"- {s}" for s in sessions]) if sessions else "No sessions."
            elif subcommand == "delete":
                if not sub_args: return "Usage: `/session delete <name>`"
                return self.session_manager.delete_session(sub_args[0])
            elif subcommand == "pin":
                if not sub_args: return "Usage: `/session pin <index>`"
                try:
                    idx = int(sub_args[0]) - 1
                    if 0 <= idx < len(self.app.history):
                        self.app.history[idx]["pinned"] = True
                        return f"Message {idx+1} pinned."
                    return "Error: Invalid message index."
                except ValueError:
                    return "Error: Index must be a number."
            elif subcommand == "unpin":
                if not sub_args: return "Usage: `/session unpin <index>`"
                try:
                    idx = int(sub_args[0]) - 1
                    if 0 <= idx < len(self.app.history):
                        self.app.history[idx]["pinned"] = False
                        return f"Message {idx+1} unpinned."
                    return "Error: Invalid message index."
                except ValueError:
                    return "Error: Index must be a number."
            else:
                return f"Unknown /session subcommand: {subcommand}."
        except Exception as e:
            return f"[ERROR] Session error: {e}"

    def _session_help(self) -> str:
        """Returns help for /session command."""
        return """
**`/session` Commands:**
- `/session save [name]`: Save current history.
- `/session load <name>`: Load a saved history.
- `/session list`: List all saved sessions.
- `/session delete <name>`: Delete a saved session.
- `/session pin <index>`: Pin a message to prevent summarization.
- `/session unpin <index>`: Unpin a message.
"""

    # --- Macro Management ---

    def _macro(self, args: List[str]) -> str:
        """Handles /macro subcommands."""
        if not args or args[0] == "help":
            return self._macro_help()
        
        subcommand = args[0].lower()
        sub_args = args[1:]

        try:
            if subcommand == "record":
                if not sub_args: return "Usage: `/macro record <name>`"
                name = sub_args[0]
                if self.app.is_recording_macro:
                    return f"Already recording macro '{self.app.current_macro_name}'."
                self.app.start_macro_recording(name)
                return f"Recording macro '{name}'. Use `/macro stop` to finish."
            elif subcommand == "stop":
                if not self.app.is_recording_macro: return "No macro recording active."
                name = self.app.current_macro_name
                commands = self.app.stop_macro_recording()
                if commands:
                    config_manager.save_macro(name, commands)
                    return f"Macro '{name}' saved ({len(commands)} commands)."
                return f"Macro '{name}' stopped (no commands recorded)."
            elif subcommand == "play":
                if not sub_args: return "Usage: `/macro play <name>`"
                name = sub_args[0]
                cmds = config_manager.load_macro(name)
                if not cmds: return f"Macro '{name}' not found."
                asyncio.create_task(self.app.play_macro(cmds))
                return f"Playing macro '{name}'."
            elif subcommand == "list":
                macros = config_manager.list_macros()
                return "**Saved Macros:**\n" + "\n".join([f"- {m}" for m in macros]) if macros else "No macros."
            elif subcommand == "delete":
                if not sub_args: return "Usage: `/macro delete <name>`"
                config_manager.delete_macro(sub_args[0])
                return f"Macro '{sub_args[0]}' deleted."
            else:
                return f"Unknown /macro subcommand: {subcommand}."
        except Exception as e:
            return f"[ERROR] Macro error: {e}"

    def _macro_help(self) -> str:
        """Returns help for /macro command."""
        return """
**`/macro` Commands:**
- `/macro record <name>`: Start recording commands.
- `/macro stop`: Stop recording and save.
- `/macro play <name>`: Execute a saved macro.
- `/macro list`: List all saved macros.
- `/macro delete <name>`: Delete a saved macro.
"""