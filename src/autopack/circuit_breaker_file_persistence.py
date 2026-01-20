"""File-based Circuit Breaker Persistence.

Provides persistence layer for circuit breaker state using local files,
enabling state recovery across process restarts to prevent retry storms.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileBasedCircuitBreakerPersistence:
    """File-based persistence for circuit breaker state.

    Saves and restores circuit breaker state to a local JSON file, allowing
    circuit breakers to maintain their state across process restarts.
    This prevents retry storms to failing external services after
    application restarts.

    Example:
        persistence = FileBasedCircuitBreakerPersistence(".autopack/circuit_breaker_state.json")

        # Save state
        persistence.save_state("api_service", {"state": "open", "failure_count": 5})

        # Load state
        state = persistence.load_state("api_service")

        # Clear state
        persistence.clear_state("api_service")
    """

    def __init__(self, file_path: str = ".autopack/circuit_breaker_state.json"):
        """Initialize persistence with file path.

        Args:
            file_path: Path to JSON file for storing state
        """
        self.file_path = Path(file_path)
        self._ensure_persistence_dir()
        self._state_data: dict = {}
        self._load_all_states()
        logger.info(f"Circuit breaker persistence initialized with file: {file_path}")

    def _ensure_persistence_dir(self):
        """Ensure the directory for persistence file exists."""
        if self.file_path.parent != Path("."):
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created persistence directory: {self.file_path.parent}")

    def _load_all_states(self):
        """Load all states from file on initialization."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._state_data = json.load(f)
                logger.debug(f"Loaded {len(self._state_data)} circuit breaker states from file")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load circuit breaker states from {self.file_path}: {e}")
                self._state_data = {}
        else:
            self._state_data = {}
            logger.debug(f"No existing persistence file at {self.file_path}, starting fresh")

    def _save_to_disk(self):
        """Save all states to disk."""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._state_data, f, indent=2, default=str)
            logger.debug(f"Saved {len(self._state_data)} circuit breaker states to file")
            return True
        except IOError as e:
            logger.error(f"Failed to save circuit breaker states to {self.file_path}: {e}")
            return False

    def save_state(self, service_name: str, state: dict) -> bool:
        """Save circuit breaker state to file.

        Args:
            service_name: Name of circuit breaker/service
            state: State dictionary to persist

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            self._state_data[service_name] = state
            return self._save_to_disk()
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize state for '{service_name}': {e}")
            return False

    def load_state(self, service_name: str) -> Optional[dict]:
        """Load circuit breaker state from file.

        Args:
            service_name: Name of circuit breaker/service

        Returns:
            State dictionary if found, None otherwise
        """
        return self._state_data.get(service_name)

    def clear_state(self, service_name: str) -> bool:
        """Clear circuit breaker state from file.

        Args:
            service_name: Name of circuit breaker/service

        Returns:
            True if clear succeeded, False otherwise
        """
        if service_name in self._state_data:
            del self._state_data[service_name]
            return self._save_to_disk()
        return True

    def close(self):
        """Close persistence (no-op for file-based)."""
        # No-op for file-based persistence
        logger.debug("File-based persistence closed (no-op)")
