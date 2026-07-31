from __future__ import annotations

import threading
from collections.abc import Callable


class QueueGate:
    """Permanently stop new uploads once an observed queue position reaches a limit."""

    def __init__(self, limit: int, logger: Callable[[str], None] = print):
        self.limit = limit
        self.logger = logger
        self._allowed = True
        self._logged = False
        self._lock = threading.Lock()

    @property
    def allowed(self) -> bool:
        with self._lock:
            return self._allowed

    def before_upload(self) -> bool:
        with self._lock:
            if not self._allowed and not self._logged:
                self.logger(f"queue limit {self.limit} reached; deferring new uploads")
                self._logged = True
            return self._allowed

    def observe_upload(self, position: int | None) -> None:
        if position is None:
            return
        with self._lock:
            if position >= self.limit:
                self._allowed = False
