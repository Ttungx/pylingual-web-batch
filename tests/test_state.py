import json
from pathlib import Path

import pytest

from pylingual_web_batch.errors import StateError
from pylingual_web_batch.models import TaskRecord, TaskStatus
from pylingual_web_batch.state import StateStore


def test_state_round_trip_uses_versioned_atomic_shape(tmp_path: Path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.set("pkg/mod.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="id-1"))

    loaded = StateStore(path).get("pkg/mod.pyc")

    assert loaded is not None
    assert loaded.status is TaskStatus.TIMEOUT
    assert loaded.identifier == "id-1"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["tasks"]["pkg/mod.pyc"]["updated_at"].endswith("+00:00")
    assert list(tmp_path.glob("*.tmp")) == []


def test_corrupt_or_unsupported_state_is_not_overwritten(tmp_path: Path):
    for contents in ("not-json", '{"version":2,"tasks":{}}'):
        path = tmp_path / "state.json"
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(StateError):
            StateStore(path)
        assert path.read_text(encoding="utf-8") == contents


def test_invalid_record_field_type_raises_state_error_without_overwrite(tmp_path: Path):
    path = tmp_path / "state.json"
    contents = '{"version":1,"tasks":{"x.pyc":{"status":"timeout","attempts":"one"}}}'
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(StateError, match="attempts"):
        StateStore(path)

    assert path.read_text(encoding="utf-8") == contents


def test_timeout_identifier_survives_new_store(tmp_path: Path):
    path = tmp_path / "state.json"
    StateStore(path).set(
        "x.pyc",
        TaskRecord(TaskStatus.TIMEOUT, identifier="server-42", last_position=7),
    )

    record = StateStore(path).get("x.pyc")

    assert record is not None
    assert record.identifier == "server-42"
    assert record.last_position == 7


def test_items_are_copies_and_mark_done_preserves_identifier(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.set("x.pyc", TaskRecord(TaskStatus.UPLOADED, identifier="secret"))
    snapshot = store.items()
    snapshot["x.pyc"].identifier = "changed"
    store.mark_done("x.pyc")

    record = store.get("x.pyc")
    assert record is not None
    assert record.status is TaskStatus.DONE
    assert record.identifier == "secret"
