from pathlib import Path

from pylingual_web_batch.api import ProgressResponse, SourceResponse, UploadResponse
from pylingual_web_batch.batch import BatchDecompiler
from pylingual_web_batch.models import BatchConfig, TaskRecord, TaskStatus
from pylingual_web_batch.state import StateStore


class FakeClient:
    def __init__(self, *, positions=None, permanent=False):
        self.uploads = []
        self.polls = []
        self.positions = iter(positions or [0])
        self.permanent = permanent

    def upload(self, path):
        self.uploads.append(path)
        return UploadResponse(f"new-{len(self.uploads)}", True)

    def poll(self, identifier):
        self.polls.append(identifier)
        if self.permanent:
            from pylingual_web_batch.errors import PermanentDecompilerError

            raise PermanentDecompilerError("server failed")
        return ProgressResponse(identifier, "done", next(self.positions), True)

    def fetch_source(self, identifier):
        return SourceResponse(f"# {identifier}\n", True)

    def close(self):
        pass


def make_input(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "in"
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pyc")
    return root


def config(tmp_path: Path, root: Path, **kwargs) -> BatchConfig:
    return BatchConfig(
        root,
        tmp_path / "out",
        state_path=tmp_path / "state.json",
        lock_path=tmp_path / "run.lock",
        poll_interval=0.001,
        **kwargs,
    )


def test_existing_output_is_skipped(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    output = tmp_path / "out" / "a.py"
    output.parent.mkdir()
    output.write_text("already\n", encoding="utf-8")
    client = FakeClient()

    summary = BatchDecompiler(config(tmp_path, root), client=client).run()

    assert summary.skipped == 1
    assert client.uploads == []
    assert output.read_text(encoding="utf-8") == "already\n"


def test_timeout_identifier_is_resumed_without_upload(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    cfg = config(tmp_path, root)
    StateStore(cfg.state_path).set(
        "a.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="old-1", attempts=1)
    )
    client = FakeClient()

    summary = BatchDecompiler(cfg, client=client).run()

    assert summary.succeeded == 1
    assert client.uploads == []
    assert client.polls == ["old-1"]
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == "# old-1\n"


def test_queue_limit_defers_only_new_uploads(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc", "b.pyc")
    client = FakeClient(positions=[10])

    summary = BatchDecompiler(config(tmp_path, root), client=client, logger=lambda _: None).run()

    assert summary.succeeded == 1
    assert summary.deferred == 1
    assert len(client.uploads) == 1


def test_resume_bypasses_closed_gate(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc", "b.pyc", "c.pyc")
    cfg = config(tmp_path, root)
    StateStore(cfg.state_path).set(
        "b.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="old-b")
    )
    client = FakeClient(positions=[10, 0])

    summary = BatchDecompiler(cfg, client=client, logger=lambda _: None).run()

    assert summary.succeeded == 2
    assert summary.deferred == 1
    assert client.polls == ["new-1", "old-b"]


def test_resumed_position_never_closes_gate_for_new_upload(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc", "b.pyc")
    cfg = config(tmp_path, root)
    StateStore(cfg.state_path).set(
        "a.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="old-a")
    )
    client = FakeClient(positions=[10, 0])

    summary = BatchDecompiler(cfg, client=client, logger=lambda _: None).run()

    assert summary.succeeded == 2
    assert len(client.uploads) == 1
    assert client.polls == ["old-a", "new-1"]


def test_permanent_error_is_persisted_and_not_reuploaded(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    cfg = config(tmp_path, root)
    client = FakeClient(permanent=True)

    first = BatchDecompiler(cfg, client=client).run()
    second = BatchDecompiler(cfg, client=client).run()

    assert first.failed == second.failed == 1
    assert len(client.uploads) == 1
    record = StateStore(cfg.state_path).get("a.pyc")
    assert record is not None
    assert record.status is TaskStatus.DECOMPILER_ERROR


def test_timeout_preserves_identifier(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")

    class WaitingClient(FakeClient):
        def poll(self, identifier):
            self.polls.append(identifier)
            return ProgressResponse(identifier, "working", 4, True)

    cfg = config(tmp_path, root, poll_timeout=0.001)
    summary = BatchDecompiler(cfg, client=WaitingClient(), sleep=lambda _: None).run()

    assert summary.deferred == 1
    record = StateStore(cfg.state_path).get("a.pyc")
    assert record is not None
    assert record.status is TaskStatus.TIMEOUT
    assert record.identifier == "new-1"
