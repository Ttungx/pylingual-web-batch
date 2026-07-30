# pylingual-web-batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a standalone Python package that batch-decompiles `.pyc` files through the pylingual Web API with resumable state, queue gating, safe retries, a CLI, tests, and GitHub Actions.

**Architecture:** Keep pure concerns separate: `discovery` plans files, `api` talks to pylingual, `state` persists task identifiers, `queue` gates only new uploads, `locking` prevents overlapping runs, and `batch` coordinates the lifecycle. Expose the coordinator through a small Python API and an `argparse` CLI; use `httpx` only for HTTP and standard-library modules for the rest.

**Tech Stack:** Python >=3.10; `httpx`; `pytest`; `pytest-cov`; `ruff`; `build`; GitHub Actions; setuptools with a `src/` layout.

## Global Constraints

- Work only in `D:\mytmp\pylingual-web-batch`; do not modify `D:\mytmp\docker\backend-app`.
- Package import name is `pylingual_web_batch`; CLI command is `pylingual-web-batch`.
- Default API base URL is `https://api.pylingual.io`.
- Default local concurrency is `1`; default queue limit is `10`; default poll timeout is `7200` seconds; default poll interval is `10` seconds.
- A timeout must persist the server `identifier`; reruns resume polling and never automatically re-upload unless `--reupload` is explicit.
- Queue gating applies only to new uploads; resume tasks bypass the gate.
- `success=false` without a valid completed stage is a permanent `decompiler_error`, not a timeout.
- Existing outputs are skipped by default and are never overwritten without `--reupload`.
- State writes are atomic; output writes are atomic; identifiers are redacted in normal logs.
- Tests use a mock HTTP transport/server and must not call the real pylingual service.
- The repository must not contain `.pyc` inputs, decompiled outputs, state files, logs, credentials, or API tokens.

---

## File Map

Create the following files:

```text
pyproject.toml
README.md
LICENSE
CHANGELOG.md
.gitignore
.github/workflows/test.yml
.github/workflows/release.yml
src/pylingual_web_batch/__init__.py
src/pylingual_web_batch/__main__.py
src/pylingual_web_batch/api.py
src/pylingual_web_batch/batch.py
src/pylingual_web_batch/cli.py
src/pylingual_web_batch/discovery.py
src/pylingual_web_batch/errors.py
src/pylingual_web_batch/locking.py
src/pylingual_web_batch/models.py
src/pylingual_web_batch/queue.py
src/pylingual_web_batch/state.py
tests/conftest.py
tests/test_api.py
tests/test_batch.py
tests/test_discovery.py
tests/test_locking.py
tests/test_queue.py
tests/test_state.py
tests/test_cli.py
```

Responsibilities:

- `models.py`: immutable task plans, configuration, task records, summaries.
- `errors.py`: public exception hierarchy and exit-code mapping.
- `discovery.py`: deterministic `.pyc` discovery and output mapping.
- `state.py`: versioned JSON state, atomic writes, task transitions.
- `locking.py`: cross-platform exclusive run lock.
- `api.py`: pylingual HTTP protocol and retry policy.
- `queue.py`: position-based new-upload gate.
- `batch.py`: single-task and batch lifecycle.
- `cli.py`: argument parsing, output, and process exit codes.
- `__init__.py`/`__main__.py`: public exports and module execution.

---

### Task 1: Scaffold the package and build metadata

**Files:**
- Create: `D:\mytmp\pylingual-web-batch\pyproject.toml`
- Create: `D:\mytmp\pylingual-web-batch\src\pylingual_web_batch\__init__.py`
- Create: `D:\mytmp\pylingual-web-batch\src\pylingual_web_batch\__main__.py`
- Create: `D:\mytmp\pylingual-web-batch\.gitignore`
- Create: `D:\mytmp\pylingual-web-batch\LICENSE`
- Create: `D:\mytmp\pylingual-web-batch\CHANGELOG.md`
- Test: `D:\mytmp\pylingual-web-batch\tests\test_package.py`

**Interfaces:**
- Produces importable package `pylingual_web_batch`.
- Produces console script `pylingual-web-batch`.
- `__main__.py` calls `pylingual_web_batch.cli.main()` and exits with its integer result.

- [ ] **Step 1: Write the failing package smoke test**

```python
from importlib.metadata import version


def test_package_metadata_and_import():
    import pylingual_web_batch

    assert pylingual_web_batch.__version__ == version("pylingual-web-batch")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /d D:/mytmp/pylingual-web-batch
python -m pytest tests/test_package.py -q
```

Expected: FAIL because package metadata and package files do not exist.

- [ ] **Step 3: Add build metadata and package exports**

Use this exact public metadata shape:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pylingual-web-batch"
version = "0.1.0"
description = "Resumable batch decompilation through the pylingual Web API"
readme = "README.md"
requires-python = ">=3.10"
license = {file = "LICENSE"}
authors = [{name = "ttungx"}]
dependencies = ["httpx>=0.27,<1"]

[project.optional-dependencies]
dev = [
  "build>=1.2,<2",
  "pytest>=8,<9",
  "pytest-cov>=5,<7",
  "ruff>=0.6,<1",
]

[project.scripts]
pylingual-web-batch = "pylingual_web_batch.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Create `__init__.py` with only the version during Task 1:

```python
__version__ = "0.1.0"

__all__ = ["__version__"]
```

Task 2 adds the model exports after `models.py` exists.

Create `__main__.py` with:

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Add repository hygiene files**

`.gitignore` must exclude:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.venv/
.env
*.log
*.lock
.pylingual-state.json
```

Use the MIT license with copyright holder `ttungx`. Add `CHANGELOG.md` with an `Unreleased` section and `0.1.0 - 2026-07-30` initial release section.

- [ ] **Step 5: Run the test and build**

Run:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_package.py -q
python -m build
```

Expected: the smoke test passes and `dist/` contains one `.whl` and one `.tar.gz`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/test_package.py .gitignore LICENSE CHANGELOG.md
git commit -m "chore: scaffold pylingual batch package"
```

---

### Task 2: Define models and public errors

**Files:**
- Create: `src/pylingual_web_batch/models.py`
- Create: `src/pylingual_web_batch/errors.py`
- Modify: `src/pylingual_web_batch/__init__.py`
- Test: `tests/test_models.py`

**Interfaces:**

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    TIMEOUT = "timeout"
    DONE = "done"
    SKIPPED = "skipped"
    DECOMPILER_ERROR = "decompiler_error"
    UPLOAD_FAIL = "upload_fail"
    EMPTY = "empty"
    FAILED = "failed"

@dataclass(frozen=True)
class TaskPlan:
    key: str
    input_path: Path
    output_path: Path

@dataclass(frozen=True)
class BatchConfig:
    input_dir: Path
    output_dir: Path
    state_path: Path = Path(".pylingual-state.json")
    lock_path: Path = Path(".pylingual-batch.lock")
    base_url: str = "https://api.pylingual.io"
    concurrency: int = 1
    queue_limit: int = 10
    poll_timeout: float = 7200.0
    poll_interval: float = 10.0
    request_timeout: float = 90.0
    reupload: bool = False
    include: tuple[str, ...] = ("*.pyc",)
    exclude: tuple[str, ...] = ()

@dataclass(frozen=True)
class BatchSummary:
    total: int
    succeeded: int
    skipped: int
    failed: int
    deferred: int

@dataclass
class TaskRecord:
    status: TaskStatus
    identifier: str | None = None
    attempts: int = 0
    last_stage: str | None = None
    last_position: int | None = None
    error: str | None = None
    updated_at: str | None = None
```

Exceptions:

```python
class PylingualError(Exception): ...
class ApiError(PylingualError): ...
class ApiResponseError(ApiError): ...
class PermanentDecompilerError(ApiError): ...
class StateError(PylingualError): ...
class LockError(PylingualError): ...
class ConfigurationError(PylingualError): ...
```

- [ ] **Step 1: Write failing validation tests**

```python
import pytest
from pathlib import Path
from pylingual_web_batch.models import BatchConfig, TaskStatus
from pylingual_web_batch.errors import ConfigurationError


def test_batch_config_rejects_invalid_limits(tmp_path: Path):
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, concurrency=0)
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, queue_limit=0)
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, poll_interval=0)


def test_task_status_is_serializable():
    assert TaskStatus.TIMEOUT.value == "timeout"
```

- [ ] **Step 2: Run the tests and verify failure**

```bash
python -m pytest tests/test_models.py -q
```

Expected: FAIL because models do not exist.

- [ ] **Step 3: Implement dataclasses and validation**

Use `__post_init__` on `BatchConfig` to raise `ConfigurationError` for `concurrency < 1`, `queue_limit < 1`, `poll_timeout <= 0`, `poll_interval <= 0`, or `request_timeout <= 0`. Convert `input_dir`, `output_dir`, `state_path`, and `lock_path` to `Path`.

- [ ] **Step 4: Export the public types**

Add `BatchConfig`, `BatchSummary`, and `TaskStatus` to `__all__`; do not export internal HTTP response classes from the package root.

- [ ] **Step 5: Run tests and lint**

```bash
python -m pytest tests/test_models.py -q
ruff check src tests
```

Expected: PASS with no lint findings.

- [ ] **Step 6: Commit**

```bash
git add src/pylingual_web_batch/models.py src/pylingual_web_batch/errors.py src/pylingual_web_batch/__init__.py tests/test_models.py
git commit -m "feat: add package models and errors"
```

---

### Task 3: Implement deterministic input discovery

**Files:**
- Create: `src/pylingual_web_batch/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**

```python
def discover_tasks(config: BatchConfig) -> list[TaskPlan]: ...
def map_output(input_path: Path, input_root: Path, output_root: Path) -> Path: ...
```

Rules: recurse under `input_dir`, include `.pyc` by default, sort by POSIX relative key, exclude `__pycache__`, reject paths outside the input root, and preserve relative paths below `output_dir` with a `.py` suffix. `pkg/mod.pyc` maps to `output/pkg/mod.py`.

- [ ] **Step 1: Write failing discovery tests**

```python
from pathlib import Path
from pylingual_web_batch.discovery import discover_tasks, map_output
from pylingual_web_batch.models import BatchConfig


def test_discovery_is_sorted_and_preserves_relative_paths(tmp_path: Path):
    root = tmp_path / "input"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "z" / "last.pyc").write_bytes(b"x")
    (root / "a" / "first.pyc").write_bytes(b"x")
    (root / "a" / "ignore.py").write_text("x")
    (root / "a" / "__pycache__").mkdir()
    (root / "a" / "__pycache__" / "cached.pyc").write_bytes(b"x")

    tasks = discover_tasks(BatchConfig(root, tmp_path / "out"))

    assert [task.key for task in tasks] == ["a/first.pyc", "z/last.pyc"]
    assert tasks[0].output_path == tmp_path / "out" / "a" / "first.py"


def test_map_output_changes_only_suffix(tmp_path: Path):
    source = tmp_path / "in" / "nested" / "module.pyc"
    assert map_output(source, tmp_path / "in", tmp_path / "out") == (
        tmp_path / "out" / "nested" / "module.py"
    )
```

- [ ] **Step 2: Run the tests and verify failure**

```bash
python -m pytest tests/test_discovery.py -q
```

Expected: FAIL because discovery functions do not exist.

- [ ] **Step 3: Implement discovery**

Use `Path.rglob("*.pyc")`, filter any relative component equal to `__pycache__`, apply configured glob includes/excludes to the POSIX key, and return `TaskPlan` objects sorted by `key`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_discovery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pylingual_web_batch/discovery.py tests/test_discovery.py
git commit -m "feat: add deterministic pyc discovery"
```

---

### Task 4: Implement versioned atomic state persistence

**Files:**
- Create: `src/pylingual_web_batch/state.py`
- Test: `tests/test_state.py`

**Interfaces:**

```python
class StateStore:
    def __init__(self, path: Path): ...
    def get(self, key: str) -> TaskRecord | None: ...
    def set(self, key: str, record: TaskRecord) -> None: ...
    def mark_done(self, key: str) -> None: ...
    def items(self) -> dict[str, TaskRecord]: ...
    def save(self) -> None: ...
```

The on-disk shape is `{ "version": 1, "tasks": {key: record_dict} }`. Every mutation updates an ISO UTC timestamp and writes a sibling temporary file followed by `os.replace`. A malformed or unsupported state file raises `StateError` and leaves the original untouched.

- [ ] **Step 1: Write failing state tests**

```python
import json
from pathlib import Path
import pytest
from pylingual_web_batch.errors import StateError
from pylingual_web_batch.models import TaskRecord, TaskStatus
from pylingual_web_batch.state import StateStore


def test_state_round_trip_and_atomic_shape(tmp_path: Path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.set("pkg/mod.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="id-1"))

    loaded = StateStore(path).get("pkg/mod.pyc")

    assert loaded is not None
    assert loaded.status is TaskStatus.TIMEOUT
    assert loaded.identifier == "id-1"
    payload = json.loads(path.read_text())
    assert payload["version"] == 1


def test_corrupt_state_is_not_overwritten(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("not-json")
    with pytest.raises(StateError):
        StateStore(path)
    assert path.read_text() == "not-json"
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_state.py -q
```

Expected: FAIL because `StateStore` does not exist.

- [ ] **Step 3: Implement state store**

Load an absent file as an empty version-1 document. Validate the top-level version and each record status against `TaskStatus`. Serialize enum values, omit no fields required by the schema, write with UTF-8, flush and `os.fsync` the temporary file, then replace it.

- [ ] **Step 4: Test timeout preservation explicitly**

Add this test:

```python
def test_timeout_identifier_survives_new_store(tmp_path: Path):
    path = tmp_path / "state.json"
    first = StateStore(path)
    first.set("x.pyc", TaskRecord(TaskStatus.TIMEOUT, identifier="server-42", last_position=7))
    second = StateStore(path)
    record = second.get("x.pyc")
    assert record.identifier == "server-42"
    assert record.last_position == 7
```

- [ ] **Step 5: Run tests and lint**

```bash
python -m pytest tests/test_state.py -q
ruff check src/pylingual_web_batch/state.py tests/test_state.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pylingual_web_batch/state.py tests/test_state.py
git commit -m "feat: add resumable atomic state store"
```

---

### Task 5: Implement cross-platform locking and queue gating

**Files:**
- Create: `src/pylingual_web_batch/locking.py`
- Create: `src/pylingual_web_batch/queue.py`
- Test: `tests/test_locking.py`
- Test: `tests/test_queue.py`

**Interfaces:**

```python
class RunLock:
    def __init__(self, path: Path): ...
    def acquire(self) -> None: ...
    def release(self) -> None: ...
    def __enter__(self) -> "RunLock": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

class QueueGate:
    def __init__(self, limit: int, logger: Callable[[str], None] = print): ...
    @property
    def allowed(self) -> bool: ...
    def before_upload(self) -> bool: ...
    def observe_upload(self, position: int | None) -> None: ...
```

`QueueGate` starts allowed. `position is not None and position >= limit` permanently closes new uploads for the current batch. It never closes because a resumed task was observed.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from pylingual_web_batch.errors import LockError
from pylingual_web_batch.locking import RunLock
from pylingual_web_batch.queue import QueueGate


def test_queue_gate_stops_only_after_real_position_reaches_limit():
    gate = QueueGate(10, logger=lambda _: None)
    assert gate.before_upload() is True
    gate.observe_upload(9)
    assert gate.before_upload() is True
    gate.observe_upload(10)
    assert gate.before_upload() is False


def test_queue_gate_ignores_unknown_position():
    gate = QueueGate(10, logger=lambda _: None)
    gate.observe_upload(None)
    assert gate.before_upload() is True


def test_run_lock_rejects_second_holder(tmp_path):
    first = RunLock(tmp_path / "run.lock")
    second = RunLock(tmp_path / "run.lock")
    first.acquire()
    try:
        with pytest.raises(LockError):
            second.acquire()
    finally:
        first.release()
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_locking.py tests/test_queue.py -q
```

Expected: FAIL because both modules do not exist.

- [ ] **Step 3: Implement QueueGate**

Protect the boolean with `threading.Lock`. `before_upload` returns the current flag and logs once when closed. `observe_upload` accepts the parsed server position only for a newly uploaded task and closes at `>= limit`.

- [ ] **Step 4: Implement RunLock**

Use an exclusive create/open strategy that works on Windows and Unix. Keep the file descriptor while held. On Unix use `fcntl.flock`; on Windows use `msvcrt.locking` or an exclusive lock implementation. Translate contention to `LockError`; release and close in `finally`/`__exit__`.

- [ ] **Step 5: Run tests and lint**

```bash
python -m pytest tests/test_locking.py tests/test_queue.py -q
ruff check src/pylingual_web_batch/locking.py src/pylingual_web_batch/queue.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pylingual_web_batch/locking.py src/pylingual_web_batch/queue.py tests/test_locking.py tests/test_queue.py
git commit -m "feat: add run lock and queue gate"
```

---

### Task 6: Implement the pylingual HTTP client

**Files:**
- Create: `src/pylingual_web_batch/api.py`
- Modify: `src/pylingual_web_batch/errors.py`
- Test: `tests/conftest.py`
- Test: `tests/test_api.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class UploadResponse:
    identifier: str
    success: bool
    message: str | None = None

@dataclass(frozen=True)
class ProgressResponse:
    identifier: str | None
    stage: str | None
    position: int | None
    success: bool | None
    message: str | None = None

@dataclass(frozen=True)
class SourceResponse:
    source: str
    decompilation_successful: bool

class PylingualClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 90.0,
        user_agent: str = "pylingual-web-batch/0.1",
        transport: httpx.BaseTransport | None = None,
    ): ...
    def upload(self, path: Path) -> UploadResponse: ...
    def poll(self, identifier: str) -> ProgressResponse: ...
    def fetch_source(self, identifier: str) -> SourceResponse: ...
    def close(self) -> None: ...
```

Use `httpx.Client`. Set `Accept: */*`, `Origin: https://www.pylingual.io`, `Referer: https://www.pylingual.io/`, and the configured User-Agent. Retry only network timeouts, connection errors, HTTP 429, and HTTP 5xx, with four total attempts and delays `0.3`, `0.6`, `1.2` seconds. Never retry a clear HTTP 4xx or an invalid successful response.

- [ ] **Step 1: Write failing mock transport tests**

```python
import json
from pathlib import Path
import httpx
import pytest
from pylingual_web_batch.api import PylingualClient
from pylingual_web_batch.errors import PermanentDecompilerError


def response(request: httpx.Request, payload: dict, status: int = 200):
    return httpx.Response(status, request=request, json=payload)


def test_upload_sends_multipart_and_returns_identifier(tmp_path: Path):
    seen = {}
    def handler(request: httpx.Request):
        seen["content_type"] = request.headers["content-type"]
        seen["origin"] = request.headers["origin"]
        seen["body"] = request.read()
        return response(request, {"success": True, "identifier": "abc"})

    path = tmp_path / "module.pyc"
    path.write_bytes(b"pyc")
    client = PylingualClient("https://example.test", transport=httpx.MockTransport(handler))
    result = client.upload(path)

    assert result.identifier == "abc"
    assert "multipart/form-data" in seen["content_type"]
    assert seen["origin"] == "https://www.pylingual.io"
    assert b"module.pyc" in seen["body"]


def test_poll_marks_success_false_without_stage_as_permanent_error():
    def handler(request: httpx.Request):
        return response(request, {"success": False, "message": "IndexError"})

    client = PylingualClient("https://example.test", transport=httpx.MockTransport(handler))
    with pytest.raises(PermanentDecompilerError, match="IndexError"):
        client.poll("abc")
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_api.py -q
```

Expected: FAIL because `PylingualClient` does not exist.

- [ ] **Step 3: Implement the injectable HTTP client and multipart upload**

Construct `httpx.Client(transport=transport, timeout=timeout, headers=...)` so tests can pass `httpx.MockTransport`; production callers omit `transport`. Use `files={"file": (path.name, path.open("rb"), "application/octet-stream")}` and `data={"fileName": path.name}`. Close the file after the request. Require `success is True` and a non-empty identifier; otherwise raise `ApiResponseError`.

- [ ] **Step 4: Implement progress parsing**

Parse `stage`, `position`, `identifier`, `success`, and `message`. Extract positions from `waiting_for_decompiler(pos=N)` when the JSON has no numeric `position`. If `success is False` and `stage` is absent, raise `PermanentDecompilerError` immediately.

- [ ] **Step 5: Implement source parsing**

Read `editor_content.file_raw_python.editor_content`; require a string. Preserve the returned source exactly. Read `decompilation_successful` when present and default it to `True` only if the source exists and the response omitted the field.

- [ ] **Step 6: Add retry and request error tests**

Add tests proving a first 503 followed by 200 succeeds, and a 400 raises without a second request. Use a mutable call counter in the mock handler and set retry delays to zero through an injectable `sleep` function or a patched `time.sleep`.

- [ ] **Step 7: Run tests and lint**

```bash
python -m pytest tests/test_api.py -q
ruff check src/pylingual_web_batch/api.py tests/test_api.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/pylingual_web_batch/api.py src/pylingual_web_batch/errors.py tests/conftest.py tests/test_api.py
git commit -m "feat: add resilient pylingual API client"
```

---

### Task 7: Implement batch lifecycle and resumable execution

**Files:**
- Create: `src/pylingual_web_batch/batch.py`
- Test: `tests/test_batch.py`

**Interfaces:**

```python
class BatchDecompiler:
    def __init__(
        self,
        config: BatchConfig,
        client: PylingualClient | None = None,
        logger: Callable[[str], None] = print,
    ): ...
    def run(self) -> BatchSummary: ...
    def resume(self) -> BatchSummary: ...
    def status(self) -> BatchSummary: ...
```

`BatchDecompiler` must use `StateStore`, `RunLock`, `QueueGate`, and `discover_tasks`. It may use a `ThreadPoolExecutor` for `concurrency > 1`, but the default is one worker. It must not submit a new task after `QueueGate.before_upload()` returns false; existing identifiers continue.

- [ ] **Step 1: Write failing lifecycle tests with a fake client**

```python
from pathlib import Path
from pylingual_web_batch.batch import BatchDecompiler
from pylingual_web_batch.models import BatchConfig


class FakeClient:
    def __init__(self):
        self.uploads = []
        self.polls = []
        self.sources = {"new-1": "print('new')\n", "old-1": "print('old')\n"}

    def upload(self, path):
        self.uploads.append(path)
        return type("Upload", (), {"identifier": "new-1", "success": True})()

    def poll(self, identifier):
        self.polls.append(identifier)
        return type("Progress", (), {
            "identifier": identifier, "stage": "done", "position": 0,
            "success": True, "message": None,
        })()

    def fetch_source(self, identifier):
        return type("Source", (), {
            "source": self.sources[identifier],
            "decompilation_successful": True,
        })()

    def close(self):
        pass


def test_existing_output_is_skipped(tmp_path: Path):
    source = tmp_path / "in" / "a.pyc"
    source.parent.mkdir()
    source.write_bytes(b"pyc")
    output = tmp_path / "out" / "a.py"
    output.parent.mkdir()
    output.write_text("already\n")
    client = FakeClient()

    summary = BatchDecompiler(BatchConfig(source.parent, tmp_path / "out"), client=client).run()

    assert summary.skipped == 1
    assert client.uploads == []


def test_timeout_state_is_resumed_without_upload(tmp_path: Path):
    source = tmp_path / "in" / "a.pyc"
    source.parent.mkdir()
    source.write_bytes(b"pyc")
    state = tmp_path / "state.json"
    state.write_text(
        '{"version":1,"tasks":{"a.pyc":{'
        '"status":"timeout","identifier":"old-1","attempts":1}}}'
    )
    client = FakeClient()
    config = BatchConfig(source.parent, tmp_path / "out", state_path=state)

    summary = BatchDecompiler(config, client=client).run()

    assert summary.succeeded == 1
    assert client.uploads == []
    assert client.polls == ["old-1"]
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_batch.py -q
```

Expected: FAIL because `BatchDecompiler` does not exist.

- [ ] **Step 3: Implement one-task lifecycle**

For each `TaskPlan`: load record; skip existing output unless `reupload`; classify resumable statuses (`pending`, `uploaded`, `timeout`, `empty`) with an identifier; otherwise call `QueueGate.before_upload`; upload; immediately persist `UPLOADED` and identifier; call `QueueGate.observe_upload` using the first progress position; poll until deadline; fetch and atomically write source; mark `DONE`.

- [ ] **Step 4: Implement timeout and permanent failure transitions**

Before every poll sleep, compare `time.monotonic() - started >= poll_timeout`; on timeout persist `TIMEOUT`, identifier, and last position. Catch `PermanentDecompilerError`, persist `DECOMPILER_ERROR`, and do not retry or upload again. Catch upload/API failures into `UPLOAD_FAIL` or `FAILED` while retaining any identifier already stored.

- [ ] **Step 5: Implement atomic source output**

Create the output parent, write UTF-8 source to a same-directory temporary file, flush and `fsync`, then `os.replace` it. Never truncate an existing output before the replacement succeeds.

- [ ] **Step 6: Implement batch summary and concurrency**

Use a single `RunLock` around `run`. For `concurrency == 1`, process deterministically in discovery order. For larger values, use a bounded executor but keep state mutations protected by the state store lock. Count succeeded, skipped, failed, and deferred results in `BatchSummary`.

- [ ] **Step 7: Add queue and permanent-failure tests**

Add tests proving: positions 0 through 9 allow new uploads; position 10 prevents subsequent uploads; resume bypasses the gate; `success=false` becomes `DECOMPILER_ERROR`; and a second run does not upload that permanent failure.

- [ ] **Step 8: Run tests and lint**

```bash
python -m pytest tests/test_batch.py -q
ruff check src/pylingual_web_batch/batch.py tests/test_batch.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/pylingual_web_batch/batch.py tests/test_batch.py
git commit -m "feat: add resumable batch coordinator"
```

---

### Task 8: Implement CLI commands and exit behavior

**Files:**
- Create: `src/pylingual_web_batch/cli.py`
- Modify: `src/pylingual_web_batch/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**

```python
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Commands: `run INPUT -o OUTPUT`, `resume --state PATH`, and `status --state PATH`. `run` accepts the configuration options from the spec. Exit `0` when all work succeeds/skips, `1` when any task fails, `2` for invalid arguments/configuration or lock contention.

- [ ] **Step 1: Write failing parser tests**

```python
from pylingual_web_batch.cli import build_parser


def test_run_parser_defaults():
    args = build_parser().parse_args(["run", "input", "-o", "output"])
    assert args.jobs == 1
    assert args.queue_limit == 10
    assert args.poll_timeout == 7200.0
    assert args.poll_interval == 10.0


def test_reupload_is_explicit():
    args = build_parser().parse_args(["run", "input", "-o", "output", "--reupload"])
    assert args.reupload is True
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_cli.py -q
```

Expected: FAIL because CLI functions do not exist.

- [ ] **Step 3: Implement argparse CLI**

Build subparsers with exact commands and defaults. Convert path strings to `Path`, comma-separated include/exclude values to tuples, and pass all values into `BatchConfig`.

- [ ] **Step 4: Implement output and exit codes**

Print one summary line containing total, succeeded, skipped, failed, and deferred. Catch `ConfigurationError`, `StateError`, and `LockError` as exit code 2; return 1 for a summary with failures; return 0 otherwise. Do not print full identifiers.

- [ ] **Step 5: Add command dispatch tests**

Monkeypatch `BatchDecompiler` with a fake class and assert `run`, `resume`, and `status` each call the expected method and return the expected integer. Test invalid `--jobs 0` returns 2.

- [ ] **Step 6: Run tests and package entrypoint**

```bash
python -m pytest tests/test_cli.py -q
python -m pylingual_web_batch --help
pylingual-web-batch --help
```

Expected: tests pass and both help commands show `run`, `resume`, and `status`.

- [ ] **Step 7: Commit**

```bash
git add src/pylingual_web_batch/cli.py src/pylingual_web_batch/__main__.py tests/test_cli.py
git commit -m "feat: add batch decompiler CLI"
```

---

### Task 9: Add user documentation and examples

**Files:**
- Create: `README.md`
- Create: `examples/basic.py`
- Create: `examples/configuration.toml`
- Modify: `CHANGELOG.md`

**Interfaces:**
- README documents installation, CLI, Python API, state recovery, queue behavior, failure states, security, and development commands.
- Examples must use local paths and must not contain credentials or real `.pyc` files.

- [ ] **Step 1: Write the installation and quick-start sections**

The README must contain these runnable commands:

```bash
python -m pip install pylingual-web-batch
pylingual-web-batch run ./input -o ./output
```

Document that the first run may upload new tasks, a timeout preserves the server identifier, and a later run resumes polling instead of uploading again.

- [ ] **Step 2: Document queue and failure semantics**

Include an explicit table:

| Status | Meaning | Next run |
|---|---|---|
| `timeout` | Local polling deadline reached | Resume same identifier |
| `decompiler_error` | Server returned permanent failure | Skip unless `--reupload` |
| `upload_fail` | Upload did not complete | Retry on next run |
| `done` | Source fetched and written | Skip if output exists |

Explain `position < 10` permits new uploads, `position >= 10` stops only new uploads, and resumed tasks bypass the gate.

- [ ] **Step 3: Add Python API example**

`examples/basic.py` must contain:

```python
from pathlib import Path
from pylingual_web_batch import BatchConfig, BatchDecompiler

config = BatchConfig(
    input_dir=Path("./input"),
    output_dir=Path("./output"),
    concurrency=1,
    queue_limit=10,
)
print(BatchDecompiler(config).run())
```

- [ ] **Step 4: Add development and security instructions**

Document `pip install -e ".[dev]"`, `pytest`, `ruff check .`, and `python -m build`. State that `.pyc` files may contain sensitive code, that API identifiers are task credentials, that users must comply with authorization and service terms, and that state/output/log files should not be committed.

- [ ] **Step 5: Validate documentation commands**

```bash
python -m pip install -e .
python -m pylingual_web_batch --help
```

Expected: both commands succeed.

- [ ] **Step 6: Commit**

```bash
git add README.md examples CHANGELOG.md
git commit -m "docs: add package usage and recovery guide"
```

---

### Task 10: Add GitHub Actions, final verification, and release metadata

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/release.yml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- `test.yml` runs on push and pull request.
- `release.yml` runs only for tags matching `v*` and builds the package before creating a GitHub Release.
- No workflow uploads to PyPI until a separate explicit release decision supplies a trusted PyPI environment/token.

- [ ] **Step 1: Add the test workflow**

Use this workflow shape:

```yaml
name: test
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest --cov=pylingual_web_batch --cov-report=term-missing
      - run: python -m build
```

- [ ] **Step 2: Add the tagged release workflow**

Use a tag trigger `push: tags: ["v*"]`, checkout, Python setup, install `build`, run tests, run `python -m build`, and upload `dist/*` to `actions/upload-artifact@v4`. Create a GitHub Release with `softprops/action-gh-release@v2` and attach `dist/*`. Do not add a PyPI publish step.

- [ ] **Step 3: Run the complete local gate**

```bash
python -m pytest -q
ruff check .
python -m build
python -m pip install --force-reinstall dist/pylingual_web_batch-*.whl
pylingual-web-batch --help
```

Expected: all tests pass, lint exits 0, build creates wheel/sdist, wheel installation succeeds, and help shows all three commands.

- [ ] **Step 4: Inspect repository contents**

```bash
git status --short
git ls-files | grep -E '\.(pyc|log)$|\.pylingual|\.env$' || true
git diff --check
```

Expected: no forbidden files, no whitespace errors, and only intended source/docs/workflow files are tracked.

- [ ] **Step 5: Update release metadata**

Set `CHANGELOG.md` `0.1.0` notes to the tested feature set. Ensure README installation points at `ttungx/pylingual-web-batch` and does not claim PyPI availability until a package has actually been published.

- [ ] **Step 6: Commit final release preparation**

```bash
git add .github README.md CHANGELOG.md
 git commit -m "ci: add package checks and release workflow"
```

- [ ] **Step 7: Push the public repository**

Only after local verification passes and GitHub authentication is available:

```bash
git remote add origin https://github.com/ttungx/pylingual-web-batch.git
git branch -M main
git push -u origin main
```

Expected: the public repository is visible at `https://github.com/ttungx/pylingual-web-batch`, and the test workflow starts automatically.

- [ ] **Step 8: Create the first GitHub Release**

After the workflow passes:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Expected: the release workflow builds and attaches the wheel and source archive to the `v0.1.0` GitHub Release.

---

## Plan Self-Review

- **Spec coverage:** Tasks 1–2 cover packaging, exports, dependencies, versioning, and public errors. Task 3 covers discovery. Task 4 covers versioned atomic state. Task 5 covers cross-platform locks and queue gating. Task 6 covers API endpoints, headers, response validation, retries, and permanent failures. Task 7 covers lifecycle, timeout resume, output atomicity, concurrency, and summaries. Task 8 covers CLI commands, options, and exit codes. Task 9 covers usage, security, and recovery documentation. Task 10 covers multi-version Actions, builds, artifacts, release tags, and repository hygiene.
- **Placeholder scan:** No `TODO`, `TBD`, or unspecified implementation step remains. All named interfaces and paths are defined in this plan.
- **Type consistency:** `BatchConfig`, `TaskPlan`, `TaskRecord`, `TaskStatus`, `BatchSummary`, `PylingualClient`, `QueueGate`, `StateStore`, `RunLock`, and `BatchDecompiler` signatures are consistent across tasks. The CLI constructs `BatchConfig`; the coordinator consumes it; the state and API types match the lifecycle tests.
- **Scope:** This is one cohesive package project. It excludes a Web UI and PyPI publishing credentials, as specified.
