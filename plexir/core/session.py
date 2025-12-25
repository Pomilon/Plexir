import json
import os
import datetime
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

SESSION_DIR = os.path.expanduser("~/.plexir/sessions")

class SessionManager:
    def __init__(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        self.current_session_file: Optional[str] = None

    def _get_session_path(self, session_name: str) -> str:
        return os.path.join(SESSION_DIR, f"{session_name}.json")

    def save_session(self, history: List[Dict[str, Any]], session_name: Optional[str] = None) -> str:
        if session_name is None:
            session_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        file_path = self._get_session_path(session_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            self.current_session_file = file_path
            logger.info(f"Session '{session_name}' saved to {file_path}")
            return f"Session saved as '{session_name}'."
        except (IOError, OSError) as e:
            logger.error(f"IOError saving session '{session_name}' to {file_path}: {e}")
            return f"Error: Could not save session '{session_name}'. Check file permissions or disk space. Details: {e}"
        except Exception as e:
            logger.error(f"Unexpected error saving session '{session_name}': {e}")
            return f"Error: An unexpected error occurred while saving session '{session_name}'. Details: {e}"

    def load_session(self, session_name: str) -> List[Dict[str, Any]]:
        file_path = self._get_session_path(session_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Session '{session_name}' not found.")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            self.current_session_file = file_path
            logger.info(f"Session '{session_name}' loaded from {file_path}")
            return history
        except FileNotFoundError: # Should be caught by os.path.exists, but good to have
            logger.error(f"FileNotFoundError loading session '{session_name}': {file_path}")
            raise FileNotFoundError(f"Session '{session_name}' not found at {file_path}.")
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError loading session '{session_name}' from {file_path}: {e}")
            raise ValueError(f"Error: Session file '{session_name}' is corrupted or invalid. Details: {e}")
        except (IOError, OSError) as e:
            logger.error(f"IOError loading session '{session_name}' from {file_path}: {e}")
            raise IOError(f"Error: Could not read session file '{session_name}'. Details: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading session '{session_name}': {e}")
            raise Exception(f"Error: An unexpected error occurred while loading session '{session_name}'. Details: {e}")

    def list_sessions(self) -> List[str]:
        try:
            sessions = [f.replace(".json", "") for f in os.listdir(SESSION_DIR) if f.endswith(".json")]
            sessions.sort()
            return sessions
        except (IOError, OSError) as e:
            logger.error(f"IOError listing sessions in {SESSION_DIR}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing sessions: {e}")
            return []

    def delete_session(self, session_name: str) -> str:
        file_path = self._get_session_path(session_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Session '{session_name}' not found.")
        try:
            os.remove(file_path)
            if self.current_session_file == file_path:
                self.current_session_file = None
            logger.info(f"Session '{session_name}' deleted.")
            return f"Session '{session_name}' deleted."
        except (IOError, OSError) as e:
            logger.error(f"IOError deleting session '{session_name}' from {file_path}: {e}")
            return f"Error: Could not delete session '{session_name}'. Check file permissions. Details: {e}"
        except Exception as e:
            logger.error(f"Unexpected error deleting session '{session_name}': {e}")
            return f"Error: An unexpected error occurred while deleting session '{session_name}'. Details: {e}"
