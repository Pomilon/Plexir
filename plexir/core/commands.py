"""
Slash command processing for the Plexir TUI.
Handles user-entered commands starting with '/'.
"""

import asyncio
import shlex
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
            return self._session(args)
        elif cmd == "/macro":
            return self._macro(args)
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
            elif subcommand == "tool":
                return self._config_tool(sub_args)
            else:
                return f"Unknown /config subcommand: {subcommand}."
        except Exception as e:
            return f"[ERROR] Config error: {e}"

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

    def _session(self, args: List[str]) -> str:
        """Handles /session subcommands."""
        if not args or args[0] == "help":
            return self._session_help()
        
        subcommand = args[0].lower()
        sub_args = args[1:]

        try:
            if subcommand == "save":
                return self.session_manager.save_session(self.app.history, sub_args[0] if sub_args else None)
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