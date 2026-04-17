# Persistent Sandbox Environment

The **Persistent Sandbox** is one of Plexir's most powerful features. It allows the AI to operate in a completely isolated Linux environment, effectively giving the AI its "own computer."

## How it Works

When you launch Plexir with the `--sandbox` flag:
1. Plexir starts (or restarts) a Docker container named `plexir-persistent-sandbox`.
2. The AI is informed that it is running in an isolated Docker environment.
3. **Automatic Redirection**: Every tool call (like `run_shell` or `write_file`) is automatically intercepted and executed *inside* the container instead of on your host machine.

## Benefits

- **Safety**: The AI can execute any bash command or Python script without risk to your local files or operating system.
- **State Siphon**: Plexir monitors the sandbox for file changes and active processes, sending optimized deltas to the LLM to keep the context window lean.
- **Persistence**: Unlike one-off sandboxes, the persistent sandbox keeps its state between Plexir sessions. Any files the AI creates or packages it installs (via `apt` or `pip`) will be there the next time you launch with `--sandbox`.
- **Hardened Security**: The container runs with limited capabilities (`cap_drop=["ALL"]`), preventing unauthorized system-level changes while allowing necessary file operations.

## Technical Details

- **Image**: `python:3.10-slim`
- **Memory Limit**: 1024MB (v1.10+)
- **Network**: Bridge (allows internet access for web tools/package installs).
- **Security Options**: `no-new-privileges` enabled.
- **Graceful Shutdown**: When you exit Plexir, the container is stopped to save resources but is **not** removed, preserving the AI's workspace.

## Troubleshooting

If you encounter issues with the sandbox:
1. Ensure Docker is running on your host machine.
2. Ensure your user has permissions to run Docker commands (or run Plexir with appropriate privileges).
3. You can manually remove the container if it becomes corrupted:
   ```bash
   docker stop plexir-persistent-sandbox
   docker rm plexir-persistent-sandbox
   ```