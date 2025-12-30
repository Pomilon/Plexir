"""
Configuration management for Plexir.
Handles persistence of provider settings, application preferences, and macros.
"""

import json
import logging
import os
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.plexir")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

class ProviderConfig(BaseModel):
    """Configuration for an individual LLM provider."""
    name: str = Field(..., description="Unique name for the provider.")
    type: str = Field(..., description="Type: gemini, openai, groq, ollama, mcp.")
    api_key: Optional[str] = None
    model_name: str
    base_url: Optional[str] = None

class AppConfig(BaseModel):
    """Top-level application configuration."""
    providers: List[ProviderConfig] = [
        ProviderConfig(name="Gemini Primary", type="gemini", model_name="gemini-3-flash-preview"),
        ProviderConfig(name="Gemini Fallback", type="gemini", model_name="gemini-2.5-flash"),
        ProviderConfig(name="Groq Backup", type="groq", model_name="openai/gpt-oss-120b"),
    ]
    active_provider_order: List[str] = ["Gemini Primary", "Gemini Fallback", "Groq Backup"]
    theme: str = "tokyo-night"
    debug_mode: bool = False
    session_budget: float = 0.0 # 0.0 means no limit
    macros: Dict[str, List[str]] = Field(default_factory=dict)
    tool_configs: Dict[str, Dict[str, str]] = Field(default_factory=dict)

class ConfigManager:
    """Manages loading, saving, and updating the application configuration."""
    
    def __init__(self):
        self.config = AppConfig()
        self.load()

    def ensure_config_dir(self):
        """Ensures the configuration directory exists."""
        os.makedirs(CONFIG_DIR, exist_ok=True)

    def load(self):
        """Loads configuration from disk, falling back to defaults on error."""
        self.ensure_config_dir()
        if not os.path.exists(CONFIG_FILE):
            self.save()
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.config = AppConfig(**data)
            logger.info("Configuration loaded.")
        except Exception as e:
            logger.error(f"Config load failed: {e}. Using defaults.")
            self.config = AppConfig()
            self.save()

    def _write_config_file(self, content: str):
        """Helper to write config to file."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def save(self):
        """Persists the current configuration to disk."""
        self.ensure_config_dir()
        try:
            self._write_config_file(self.config.model_dump_json(indent=4))
        except Exception as e:
            logger.error(f"Config save failed: {e}")

    async def save_async(self):
        """Persists the current configuration to disk asynchronously."""
        self.ensure_config_dir()
        try:
            loop = asyncio.get_running_loop()
            content = self.config.model_dump_json(indent=4)
            await loop.run_in_executor(None, self._write_config_file, content)
        except Exception as e:
            logger.error(f"Config save async failed: {e}")

    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """Retrieves a provider configuration by name."""
        return next((p for p in self.config.providers if p.name == name), None)

    def add_provider(self, provider_config: ProviderConfig):
        """Adds a new provider and persists the change."""
        if self.get_provider_config(provider_config.name):
            raise ValueError(f"Provider '{provider_config.name}' already exists.")
        self.config.providers.append(provider_config)
        self.config.active_provider_order.append(provider_config.name)
        self.save()

    def update_provider(self, original_name: str, new_config: ProviderConfig):
        """Updates an existing provider configuration."""
        for i, p in enumerate(self.config.providers):
            if p.name == original_name:
                if original_name != new_config.name and self.get_provider_config(new_config.name):
                    raise ValueError(f"Name '{new_config.name}' is already in use.")
                
                self.config.providers[i] = new_config
                if original_name != new_config.name:
                    try:
                        idx = self.config.active_provider_order.index(original_name)
                        self.config.active_provider_order[idx] = new_config.name
                    except ValueError:
                        pass
                self.save()
                return
        raise ValueError(f"Provider '{original_name}' not found.")

    def delete_provider(self, name: str):
        """Deletes a provider and updates the failover order."""
        self.config.providers = [p for p in self.config.providers if p.name != name]
        self.config.active_provider_order = [n for n in self.config.active_provider_order if n != name]
        self.save()

    def reorder_provider(self, name: str, direction: str):
        """Moves a provider up or down in the failover priority list."""
        try:
            idx = self.config.active_provider_order.index(name)
        except ValueError:
            raise ValueError(f"Provider '{name}' not in active order.")

        if direction == "up" and idx > 0:
            order = self.config.active_provider_order
            order[idx], order[idx - 1] = order[idx - 1], order[idx]
        elif direction == "down" and idx < len(self.config.active_provider_order) - 1:
            order = self.config.active_provider_order
            order[idx], order[idx + 1] = order[idx + 1], order[idx]
        self.save()

    def update_app_setting(self, setting_name: str, value: Any):
        """Updates a top-level application setting."""
        if hasattr(self.config, setting_name):
            setattr(self.config, setting_name, value)
            self.save()
        else:
            raise AttributeError(f"Setting '{setting_name}' does not exist.")

    def save_macro(self, name: str, commands: List[str]):
        """Saves a named command macro."""
        self.config.macros[name] = commands
        self.save()

    def load_macro(self, name: str) -> Optional[List[str]]:
        """Retrieves a macro by name."""
        return self.config.macros.get(name)

    def list_macros(self) -> List[str]:
        """Lists all saved macro names."""
        return list(self.config.macros.keys())

    def delete_macro(self, name: str):
        """Deletes a named macro."""
        if name in self.config.macros:
            del self.config.macros[name]
            self.save()

    def set_tool_config(self, tool_domain: str, key: str, value: str):
        """Sets a configuration value for a specific tool domain (e.g. 'git', 'web')."""
        if tool_domain not in self.config.tool_configs:
            self.config.tool_configs[tool_domain] = {}
        self.config.tool_configs[tool_domain][key] = value
        self.save()

    def get_tool_config(self, tool_domain: str, key: str) -> Optional[str]:
        """Retrieves a tool configuration value."""
        return self.config.tool_configs.get(tool_domain, {}).get(key)

config_manager = ConfigManager()