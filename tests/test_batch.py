from pathlib import Path

from pylingual_web_batch.api import ProgressResponse, SourceResponse, UploadResponse
from pylingual_web_batch.batch import BatchDecompiler
from pylingual_web_batch.errors import ApiResponseError
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


def test_status_does_not_create_http_client(monkeypatch, tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")

    def fail_client(*args, **kwargs):
        raise AssertionError("status must not create an HTTP client")

    monkeypatch.setattr("pylingual_web_batch.batch.PylingualClient", fail_client)
    summary = BatchDecompiler(config(tmp_path, root)).status()
    assert summary.total == 1


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


def test_jobs_run_tasks_in_parallel(tmp_path: Path):
    import threading

    root = make_input(tmp_path, "a.pyc", "b.pyc")
    first_poll_started = threading.Event()
    release_first = threading.Event()

    class ParallelClient(FakeClient):
        def __init__(self):
            super().__init__()
            self._poll_lock = threading.Lock()

        def poll(self, identifier):
            with self._poll_lock:
                self.polls.append(identifier)
                is_first = len(self.polls) == 1
            if is_first:
                first_poll_started.set()
                assert release_first.wait(1), "second task did not run concurrently"
            else:
                assert first_poll_started.is_set()
                release_first.set()
            return ProgressResponse(identifier, "done", 0, True)

    summary = BatchDecompiler(
        config(tmp_path, root, concurrency=2), client=ParallelClient()
    ).run()
    assert summary.succeeded == 2


def test_poll_api_error_preserves_resumable_identifier(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    cfg = config(tmp_path, root)

    class TransientClient(FakeClient):
        def poll(self, identifier):
            self.polls.append(identifier)
            raise ApiResponseError("connection lost")

    first_client = TransientClient()
    first = BatchDecompiler(cfg, client=first_client).run()
    record = StateStore(cfg.state_path).get("a.pyc")

    assert first.deferred == 1
    assert record is not None
    assert record.status is TaskStatus.UPLOADED
    assert record.identifier == "new-1"

    second_client = FakeClient()
    second = BatchDecompiler(cfg, client=second_client).run()
    assert second.succeeded == 1
    assert second_client.uploads == []
    assert second_client.polls == ["new-1"]


def test_fetch_api_error_preserves_resumable_identifier(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    cfg = config(tmp_path, root)

    class TransientClient(FakeClient):
        def fetch_source(self, identifier):
            raise ApiResponseError("connection lost")

    summary = BatchDecompiler(cfg, client=TransientClient()).run()
    record = StateStore(cfg.state_path).get("a.pyc")

    assert summary.deferred == 1
    assert record is not None
    assert record.status is TaskStatus.UPLOADED
    assert record.identifier == "new-1"


def test_instances_constructed_before_runs_reload_state_under_lock(tmp_path: Path):
    root_a = make_input(tmp_path / "first", "a.pyc")
    root_b = make_input(tmp_path / "second", "b.pyc")
    cfg_a = config(tmp_path, root_a)
    cfg_b = config(tmp_path, root_b)
    first = BatchDecompiler(cfg_a, client=FakeClient())
    second = BatchDecompiler(cfg_b, client=FakeClient())

    first.run()
    second.run()

    records = StateStore(cfg_a.state_path).items()
    assert set(records) == {"a.pyc", "b.pyc"}


def test_concurrent_queue_reservation_limits_unobserved_uploads(tmp_path: Path):
    import threading

    root = make_input(tmp_path, "a.pyc", "b.pyc")
    first_upload_started = threading.Event()

    class UploadRaceClient(FakeClient):
        def upload(self, path):
            self.uploads.append(path)
            first_upload_started.set()
            return UploadResponse(f"new-{len(self.uploads)}", True)

        def poll(self, identifier):
            self.polls.append(identifier)
            assert first_upload_started.is_set()
            return ProgressResponse(identifier, "done", 1, True)

    client = UploadRaceClient()
    summary = BatchDecompiler(
        config(tmp_path, root, concurrency=2, queue_limit=1),
        client=client,
        logger=lambda _: None,
    ).run()

    assert summary.succeeded == 1
    assert summary.deferred == 1
    assert len(client.uploads) == 1


def test_output_write_error_preserves_resumable_identifier(tmp_path: Path):
    root = make_input(tmp_path, "a.pyc")
    output_parent = tmp_path / "out"
    output_parent.write_text("not a directory", encoding="utf-8")
    cfg = config(tmp_path, root)

    summary = BatchDecompiler(cfg, client=FakeClient()).run()
    record = StateStore(cfg.state_path).get("a.pyc")

    assert summary.deferred == 1
    assert record is not None
    assert record.status is TaskStatus.UPLOADED
    assert record.identifier == "new-1"


def test_resume_uses_persisted_paths_without_current_discovery(tmp_path: Path):
    original = tmp_path / "original"
    root = make_input(original, "pkg/a.pyc")
    cfg = config(original, root)
    StateStore(cfg.state_path).set(
        "pkg/a.pyc",
        TaskRecord(
            TaskStatus.TIMEOUT,
            identifier="old-a",
            input_path=str(root / "pkg/a.pyc"),
            output_path=str(original / "out/pkg/a.py"),
        ),
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    resume_cfg = BatchConfig(
        elsewhere,
        elsewhere,
        state_path=cfg.state_path,
        lock_path=cfg.lock_path,
        poll_interval=0.001,
    )
    client = FakeClient()

    summary = BatchDecompiler(resume_cfg, client=client).resume()

    assert summary.succeeded == 1
    assert client.uploads == []
    assert client.polls == ["old-a"]
    assert (original / "out/pkg/a.py").exists()


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
