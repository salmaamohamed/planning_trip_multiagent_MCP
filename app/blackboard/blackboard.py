"""Shared Blackboard workspace for one travel-planning session.

Specialist agents never pass results to each other directly: each one writes
its structured options here, and readers pull what they need. The Blackboard
is created per session and injected into the graph through the LangGraph
runtime context, so there is no module-level mutable state.
"""
import copy
import threading
import uuid
from typing import Any

from app.blackboard.schemas import BlackboardEntry


class Blackboard:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or uuid.uuid4().hex
        self._entries: dict[str, BlackboardEntry] = {}
        self._lock = threading.RLock()

    def write(self, key: str, value: Any, author: str = "unknown") -> None:
        """Create or overwrite `key`."""
        with self._lock:
            previous = self._entries.get(key)
            self._entries[key] = BlackboardEntry(
                key=key,
                value=copy.deepcopy(value),
                written_by=author,
                version=previous.version + 1 if previous else 1,
            )

    def update(self, key: str, value: Any, author: str = "unknown") -> None:
        """Modify an existing key. Dicts are merged; any other type is replaced."""
        with self._lock:
            if key not in self._entries:
                raise KeyError(f"Blackboard key '{key}' does not exist; use write() first")
            current = self._entries[key].value
            new_value = {**current, **value} if isinstance(current, dict) and isinstance(value, dict) else value
            self.write(key, new_value, author)

    def read(self, key: str, default: Any = None) -> Any:
        """Return a copy of the value so readers cannot mutate shared data."""
        with self._lock:
            entry = self._entries.get(key)
            return copy.deepcopy(entry.value) if entry else default

    def entry(self, key: str) -> BlackboardEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            return entry.model_copy(deep=True) if entry else None

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._entries

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return {key: copy.deepcopy(entry.value) for key, entry in self._entries.items()}
