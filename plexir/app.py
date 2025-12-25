"""
Plexir: An advanced AI Terminal Workspace.
Main entry point for the application.
"""

import argparse
import logging
import os
from plexir.ui.app import run

def setup_logging():
    """Sets up centralized logging for the Plexir application."""
    log_dir = os.path.expanduser("~/.plexir")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "plexir.log")
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        filemode="a",
        force=True
    )
    logging.info("--- Plexir Session Started ---")

def main():
    """Main entry point for the Plexir CLI."""
    setup_logging()
    parser = argparse.ArgumentParser(description="Plexir AI Terminal Workspace")
    parser.add_argument(
        "--sandbox", 
        action="store_true", 
        help="Enable persistent Docker sandbox for all tool executions."
    )
    args = parser.parse_args()

    run(sandbox_enabled=args.sandbox)

if __name__ == "__main__":

    main()
