# Configuring Providers

Plexir is designed to be provider-agnostic, supporting multiple LLM services with a robust failover mechanism.

## The Configuration File

Settings are stored in JSON format at `~/.plexir/config.json`. This file is automatically secured with `0o600` permissions (owner read/write only).

## Provider Types

- **`gemini`**: Google's Gemini models. Supports **API Key** (AI Studio) and **OAuth** (Vertex AI/Standalone).
- **`groq`**: Ultra-fast inference for Llama 3 and Mistral models. Requires a Groq API key.
- **`cerebras`**: High-performance inference provider (OpenAI-compatible). Requires a Cerebras API key.
- **`openai`**: Supports official OpenAI models or any OpenAI-compatible API (like local Ollama instances).

## Authentication Modes (`auth_mode`)

For Gemini providers, you can specify how Plexir should authenticate:

- **`auto` (Default)**: Attempts API Key first, then looks for Standalone OAuth tokens (`oauth_creds.json`).
- **`api_key`**: Strictly use the provided `api_key`.
- **`oauth`**: Strictly use standalone OAuth credentials (using the custom REST client bypass for AI Studio access).

### Secure Secrets
Instead of plain text, you can use:
- `env:VARIABLE_NAME`: Read from environment variables.
- `keyring:username`: Read from the system keyring (service: `plexir`).

## Context Management

Plexir automatically manages the context window to prevent model errors when conversations get too long.

### Automatic Limits
Plexir comes with pre-configured token limits for popular models (e.g., 2M tokens for Gemini 1.5 Pro, 128k for GPT-4o). When the conversation history exceeds this limit, Plexir will:
1.  **Preserve** the most recent messages.
2.  **Preserve** system instructions.
3.  **Summarize/Distill** the older parts of the conversation to save space while retaining context.

### Manual Configuration (`context_limit`)
You can override the default limit for any provider. This is useful for:
- Testing how models behave with shorter context.
- Forcing stricter limits on "Preview" models to save costs.

To set a strict 50,000 token limit on a provider:
```bash
/config set "Gemini Primary" context_limit 50000
```
*Set to `0` or `null` to use the model's default.*

## Failover & Retries

Plexir manages providers using a priority order defined in your config.

1. **Jittered Retries**: If a provider returns a rate limit error (429) or transient server error (503), Plexir will retry with a smart exponential backoff (e.g., `2^attempt + jitter`).
2. **Explicit Delay**: Plexir parses "Retry-After" hints from the Google API (e.g., "retry in 17s") and waits the exact duration required.
3. **Instant Fallback**: If retries are exhausted or a hard "Fatal" error occurs, Plexir immediately switches to the next provider in the list.

## Dynamic Pricing

Plexir allows you to configure token prices per model in `config.json`. This ensures cost estimation remains accurate as providers update their pricing.

```json
"pricing": {
    "gemini-2.0-flash": [0.10, 0.40],
    "gpt-4o": [2.50, 10.00]
}
```
*(Format: [Input price per 1M, Output price per 1M])*

## Managing via CLI

You can manage your providers without leaving the TUI using slash commands:

### List all providers
```bash
/config list
```

### Add a new provider
```bash
/config add "My Backup" groq llama3-70b-8192 api_key=YOUR_KEY
```

### Set an API key
```bash
/config set "Gemini Primary" api_key env:GEMINI_KEY
```

### Change auth mode
```bash
/config set "Gemini Primary" auth_mode oauth
```

### Reorder priorities
```bash
/config reorder "Groq Backup" up
```

## Economics & Budgeting

Plexir tracks real-time token usage and estimates costs based on the active provider's pricing. 

### Set a session budget
To prevent unexpected costs during long sessions, you can set a maximum dollar amount for the current session. If exceeded, Plexir will stop generating and notify you.
```bash
/config budget 0.50
```
*Set to `0` to disable the limit.*

### View current usage
Usage metrics (Tokens and Estimated Cost) are always visible in the **System Status** sidebar.