from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from .errors import ConfigurationError


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_dir", Path(self.input_dir))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "state_path", Path(self.state_path))
        object.__setattr__(self, "lock_path", Path(self.lock_path))

        parsed_url = urlparse(self.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigurationError("base_url must be an absolute HTTP(S) URL")
        if self.concurrency < 1:
            raise ConfigurationError("concurrency must be at least 1")
        if self.queue_limit < 1:
            raise ConfigurationError("queue_limit must be at least 1")
        if self.poll_timeout <= 0:
            raise ConfigurationError("poll_timeout must be greater than 0")
        if self.poll_interval <= 0:
            raise ConfigurationError("poll_interval must be greater than 0")
        if self.request_timeout <= 0:
            raise ConfigurationError("request_timeout must be greater than 0")


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
    input_path: str | None = None
    output_path: str | None = None
