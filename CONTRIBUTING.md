# Contributing to Plexir

First off, thank you for considering contributing to Plexir! It's people like you that make Plexir such a great tool.

## Code of Conduct

By participating in this project, you are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs

- **Check if it has already been reported** by searching through GitHub issues.
- **Provide a clear and concise description** of the bug.
- **Include steps to reproduce** the behavior.
- **Mention your environment** (OS, Python version, Docker version).

### Suggesting Enhancements

- **Open a Feature Request** issue.
- **Explain why this enhancement would be useful** to most Plexir users.

### Pull Requests

1. **Fork the repository** and create your branch from `main`.
2. **If you've added code that should be tested, add tests.**
3. **Ensure the test suite passes.**
4. **Make sure your code lints.**
5. **Issue that PR!**

## Style Guide

- We use [Black](https://github.com/psf/black) for code formatting.
- Follow PEP 8 conventions.
- Use descriptive variable and function names.
- Keep functions small and focused on a single task.

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/plexir.git
   cd plexir
   ```
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies and the package in editable mode:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```
4. Run tests (if applicable):
   ```bash
   pytest
   ```

## Contact

If you have questions, feel free to open an issue or reach out to the maintainers.
