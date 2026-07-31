from __future__ import annotations

import threading
from collections.abc import Callable


class UploadReservation:
    """A single new-upload slot held until queue position is observed or upload fails."""

    def __init__(self, gate: QueueGate):
        self._gate = gate
        self._active = True
        self._lock = threading.Lock()

    def observe(self, position: int | None) -> None:
        with self._lock:
            if not self._active:
                return
            self._active = False
        self._gate._finish_reservation(position)

    def release(self) -> None:
        self.observe(None)


class QueueGate:
    """Serialize unobserved uploads and close after reaching a queue limit."""

    def __init__(self, limit: int, logger: Callable[[str], None] = print):
        self.limit = limit
        self.logger = logger
        self._allowed = True
        self._reservations = 0
        self._logged = False
        self._lock = threading.Lock()

    @property
    def allowed(self) -> bool:
        with self._lock:
            return self._allowed

    def reserve_upload(self) -> UploadReservation | None:
        with self._lock:
            unavailable = not self._allowed or self._reservations >= self.limit
            if unavailable and not self._logged:
                self.logger(f"queue limit {self.limit} reached; deferring new uploads")
                self._logged = True
            if unavailable:
                return None
            self._reservations += 1
            return UploadReservation(self)

    def _finish_reservation(self, position: int | None) -> None:
        with self._lock:
            if position is not None and position >= self.limit:
                self._allowed = False
            self._reservations -= 1
