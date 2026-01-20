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

### 1. Launch Plexir
```bash
plexir
```

### 2. Authentication
Plexir supports both API Keys and Google OAuth.

**Option A: API Key (Standard)**
Inside the TUI, type:
```bash
/config set "Gemini Primary" api_key YOUR_KEY
/reload
```

**Option B: Google OAuth (High Quota)**
If you want to use your Gemini CLI / Code Assist quota:
1.  Run `/auth login` inside Plexir.
2.  Follow the instructions (a new window will open).
3.  Once logged in, run `/reload`.

### 3. Verify
Try asking Plexir to explore your current directory:
> "List the files in this project."

## Modes of Operation

### Standard Mode
```bash
plexir
```
Safe default. File edits require confirmation.

### Autonomous "YOLO" Mode
```bash
plexir --sandbox --yolo
```
Fully autonomous. No confirmation prompts. Runs inside a secure Docker container.

## Safety First

By default, Plexir runs on your local host. For any "critical" action (like `write_file`), Plexir will prompt you for confirmation. 

For complete safety, always use the **Sandbox Mode**:
```bash
plexir --sandbox
```
This isolates the agent in a Docker container. In **Clone Mode** (default), your files are protected; changes are only saved if you explicitly export them on exit.
