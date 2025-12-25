# Getting Started with Plexir

Welcome to Plexir! This guide will help you get up and running with your new AI-powered terminal workspace.

## Prerequisites

Before installing Plexir, ensure you have the following:
- **Python 3.10+**: The core application logic.
- **Docker**: Optional but highly recommended for the **Sandbox Mode**.
- **API Keys**: At least one API key from [Google AI Studio](https://aistudio.google.com/) (Gemini) or [Groq](https://console.groq.com/).

## Installation

1. **Clone the project**:
   ```bash
   git clone https://github.com/pomilon/plexir.git
   cd plexir
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate  # Windows
   ```

3. **Install Plexir**:
   This will install Plexir as a command-line tool named `plexir` that you can run from anywhere.
   ```bash
   pip install -e .
   ```

## Initial Configuration

On the first run, Plexir will create a default configuration directory at `~/.plexir/`.

1. **Launch Plexir**:
   ```bash
   plexir
   ```

2. **Set your primary API key**:
   Inside the TUI, type the following command (replacing `YOUR_KEY` with your actual key):
   ```bash
   /config set "Gemini Primary" api_key YOUR_KEY
   ```

3. **Reload**:
   Type `/reload` or press `Ctrl+R` to apply the changes.

## Your First Interaction

Try asking Plexir to explore your current directory:
> "List the files in this project and tell me what the project is about."

Plexir will use the `list_directory` and `read_file` tools to fulfill your request.

## Safety First

By default, Plexir runs on your local host. For any "critical" action (like `write_file`), Plexir will prompt you for confirmation. 

For complete safety, always use the **Sandbox Mode**:
```bash
plexir --sandbox
```
