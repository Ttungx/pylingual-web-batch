from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import StateError
from .models import TaskRecord, TaskStatus

_STATE_VERSION = 1
_RECORD_FIELDS = set(TaskRecord.__dataclass_fields__)


class StateStore:
    """Thread-safe versioned task state with atomic persistence."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._tasks = self._load()

    def _load(self) -> dict[str, TaskRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != _STATE_VERSION:
                raise ValueError("unsupported state version")
            raw_tasks = payload.get("tasks")
            if not isinstance(raw_tasks, dict):
                raise ValueError("tasks must be an object")
            return {str(key): self._decode_record(value) for key, value in raw_tasks.items()}
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StateError(f"cannot load state {self.path}: {exc}") from exc

    @staticmethod
    def _decode_record(value: Any) -> TaskRecord:
        if not isinstance(value, dict):
            raise ValueError("task record must be an object")
        unknown = set(value) - _RECORD_FIELDS
        if unknown:
            raise ValueError(f"unknown task record fields: {sorted(unknown)}")
        data = {field: value.get(field) for field in _RECORD_FIELDS}
        data["status"] = TaskStatus(value.get("status"))
        data["attempts"] = value.get("attempts", 0)
        if (
            not isinstance(data["attempts"], int)
            or isinstance(data["attempts"], bool)
            or data["attempts"] < 0
        ):
            raise ValueError("attempts must be a non-negative integer")
        for field in (
            "identifier",
            "last_stage",
            "error",
            "updated_at",
            "input_path",
            "output_path",
        ):
            if data[field] is not None and not isinstance(data[field], str):
                raise ValueError(f"{field} must be a string or null")
        position = data["last_position"]
        if position is not None and (
            not isinstance(position, int) or isinstance(position, bool) or position < 0
        ):
            raise ValueError("last_position must be a non-negative integer or null")
        return TaskRecord(**data)

    def get(self, key: str) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(key)
            return deepcopy(record) if record is not None else None

    def set(self, key: str, record: TaskRecord) -> None:
        with self._lock:
            self._tasks[key] = replace(record, updated_at=_utc_now())
            self.save()

    def mark_done(self, key: str) -> None:
        with self._lock:
            record = self._tasks.get(key)
            if record is None:
                record = TaskRecord(TaskStatus.DONE)
            else:
                record = replace(record, status=TaskStatus.DONE, error=None)
            self.set(key, record)

    def items(self) -> dict[str, TaskRecord]:
        with self._lock:
            return deepcopy(self._tasks)

    def save(self) -> None:
        with self._lock:
            payload = {
                "version": _STATE_VERSION,
                "tasks": {key: _encode_record(record) for key, record in self._tasks.items()},
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temporary = handle.name
                    json.dump(payload, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            except OSError as exc:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
                raise StateError(f"cannot save state {self.path}: {exc}") from exc


def _encode_record(record: TaskRecord) -> dict[str, Any]:
    value = asdict(record)
    value["status"] = record.status.value
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
