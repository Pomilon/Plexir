# Configuring Providers

Plexir is designed to be provider-agnostic, supporting multiple LLM services with a robust failover mechanism.

## The Configuration File

Settings are stored in JSON format at `~/.plexir/config.json`.

## Provider Types

- **`gemini`**: Google's Gemini models (Flash, Pro). Requires an API key from Google AI Studio.
- **`groq`**: Ultra-fast inference for Llama 3 and Mistral models. Requires a Groq API key.
- **`openai`**: Supports official OpenAI models or any OpenAI-compatible API (like local Ollama instances).

## Failover & Retries

Plexir manages providers using a priority order defined in your config.

1. **Smart Retries**: If a provider returns a rate limit error (429), Plexir will retry up to 20 times with a 2-second delay.
2. **Instant Fallback**: If a provider returns a hard "Resource Exhausted" or "Fatal" error, Plexir immediately switches to the next provider in the list.
3. **Sticky Routing**: Once a fallback is successful, Plexir "sticks" to that backup provider for the rest of the conversation to ensure consistency.

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
/config set "Gemini Primary" api_key AIza...
```

### Change model
```bash
/config set "Groq Backup" model_name deepseek-v3
```

### Reorder priorities
```bash
/config reorder "Groq Backup" up
```
