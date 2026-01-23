# Memory & Context Management

Plexir uses advanced techniques to manage long-running conversations, ensuring the model remains coherent even as the history grows.

## 🧠 Persistent Memory Bank (New in v1.7)

Plexir now includes a **Long-Term Memory** system powered by `chromadb`. This allows the agent to store and recall specific facts across different sessions.

### Features
- **Semantic Storage**: Memories are stored as embeddings, meaning the agent can find them even if the exact keywords don't match (e.g., searching for "database credentials" finds "db password").
- **Session Persistence**: Memories persist even after you close Plexir. They are stored in `~/.plexir/memory`.
- **Tools**:
    - `save_memory`: The agent uses this to store explicit user facts (e.g., "The user prefers Python over C++").
    - `search_memory`: The agent uses this to recall information when needed.

### Usage
You can prompt the agent to remember things directly:
> "Remember that my API keys are stored in .env.local"

Or ask it to recall:
> "Where did I say my keys were?"

## 🔄 Rolling Summarization

When a conversation history becomes too large (exceeding 40 messages), Plexir automatically triggers **Rolling Summarization**. 

1. **How it works**: Plexir identifies older, unpinned messages and uses the primary LLM to condense them into a concise "BACKGROUND SUMMARY."
2. **Context Preservation**: This summary is injected at the start of the conversation, allowing the model to remember high-level decisions and context while clearing out detailed token-heavy noise.
3. **Automatic**: This happens in the background without user intervention.

## 📌 Message Pinning

You can manually protect critical messages from being summarized or pruned using **Context Pinning**.

### Pin a message
Use the `/session pin` command followed by the message number (visible in the history or logs).
```bash
/session pin 5
```
*Pinned messages will be highlighted and are exempt from the summarization process.*

### Unpin a message
```bash
/session unpin 5
```

## 🧠 Distillation (Failover)

During a **Provider Failover** (e.g., Gemini Primary hitting a quota), Plexir uses a "Distillation" process to transfer only the most essential recent context to the backup provider. This ensures a smooth transition with minimal latency and token waste.