# Plexir Slash Command Reference

This document provides a comprehensive guide to all available slash commands in Plexir.

---

## 🚀 General Commands

### `/help`
Displays a summary of all primary slash commands.

### `/clear`
Clears the chat display and current conversation history. This cannot be undone.

### `/tools`
Lists all tools currently registered and available to the AI agent.

### `/reload`
Forces a reload of all provider configurations from `~/.plexir/config.json`. Useful after manually editing the config file.

### `/quit` or `/exit`
Exits the Plexir application cleanly, stopping the sandbox if it's running.

---

## ⚙️ Configuration (`/config`)

Manages providers, tool settings, and application preferences.

#### `/config list`
Shows the current provider failover order, tool configurations, and other app settings.

#### `/config set <provider_name> <key> <value>`
Updates a specific property for a provider.
- **`<provider_name>`**: The name of the provider (e.g., `"Gemini Primary"`). Use quotes if it contains spaces.
- **`<key>`**: The property to change (`api_key`, `model_name`, `type`, `base_url`).
- **`<value>`**: The new value.
- **Example**: `/config set "Gemini Primary" api_key ghp_...`
- **Example**: `/config set "Groq Backup" model_name llama3-70b-8192`

#### `/config tool <domain> <key> <value>`
Sets a configuration value for a specific tool suite. This is how you provide tokens for external services.
- **`<domain>`**: The tool domain (e.g., `git`, `github`).
- **`<key>`**: The configuration key (e.g., `token`, `allowed_repos`).
- **`<value>`**: The configuration value.
- **Example (Git PAT)**: `/config tool git token ghp_...`
- **Example (GitHub Permissions)**: `/config tool github token ghp_...`
- **Example (GitHub Permissions)**: `/config tool github allowed_repos pomilon/plexir,another/repo`
- **Example (Web Search)**: `/config tool web tavily_api_key tvly-XXXX`
- **Example (Web Search)**: `/config tool web serper_api_key XXXX`

#### `/config add <name> <type> <model> [options]`
Adds a new LLM provider.
- **`<name>`**: A unique name (e.g., `"My OpenAI"`).
- **`<type>`**: Provider type (`openai`, `gemini`, `groq`, `ollama`, `mcp`).
- **`<model>`**: The model identifier (e.g., `gpt-4o`, `gemini-1.5-pro-latest`).
- **`[options]`**: Optional `api_key=...` and `base_url=...` for self-hosted models.
- **Example**: `/config add "Local LLM" ollama llama3 base_url=http://localhost:11434`

#### `/config delete <name>`
Removes a provider from your configuration.
- **Example**: `/config delete "Groq Backup"`

#### `/config reorder <name> <up|down>`
Changes the failover priority of a provider.
- **Example**: `/config reorder "Local LLM" up`

---

## 💾 Session Management (`/session`)

Saves and loads chat histories.

#### `/session list`
Lists all saved session files.

#### `/session save [name]`
Saves the current conversation history to a file. If `[name]` is omitted, a timestamp is used.
- **Example**: `/session save my-feature-dev`

#### `/session load <name>`
Clears the current chat and loads a saved session.
- **Example**: `/session load my-feature-dev`

#### `/session delete <name>`
Deletes a saved session file.
- **Example**: `/session delete old-session`

---

## 📹 Macro Management (`/macro`)

Records and plays back sequences of commands and prompts.

#### `/macro record <name>`
Starts recording all subsequent inputs into a macro named `<name>`.
- **Example**: `/macro record setup-env`

#### `/macro stop`
Stops the current recording and saves the macro.

#### `/macro play <name>`
Executes all the commands from a saved macro in sequence.
- **Example**: `/macro play setup-env`

#### `/macro list`
Lists all saved macros.

#### `/macro delete <name>`
Deletes a saved macro.
- **Example**: `/macro delete old-macro`
