from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from .api import ProgressResponse, PylingualClient
from .discovery import discover_tasks
from .errors import ApiError, PermanentDecompilerError
from .locking import RunLock
from .models import BatchConfig, BatchSummary, TaskPlan, TaskRecord, TaskStatus
from .queue import QueueGate
from .state import StateStore

_RESUMABLE = {
    TaskStatus.PENDING,
    TaskStatus.UPLOADED,
    TaskStatus.TIMEOUT,
    TaskStatus.EMPTY,
}
_FINAL_FAILURE = {TaskStatus.DECOMPILER_ERROR, TaskStatus.FAILED}
_DONE_STAGES = {"done", "completed", "complete", "finished"}


class BatchDecompiler:
    """Coordinate discovery, upload, polling, state, and atomic output writes."""

    def __init__(
        self,
        config: BatchConfig,
        client: PylingualClient | None = None,
        logger: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.client = client
        self._owns_client = client is None
        self.logger = logger
        self.sleep = sleep
        self.state = StateStore(config.state_path)
        self.gate = QueueGate(config.queue_limit, logger)

    def _client(self) -> PylingualClient:
        if self.client is None:
            raise RuntimeError("HTTP client is unavailable outside run or resume")
        return self.client

    def run(self) -> BatchSummary:
        return self._execute(resume_only=False)

    def resume(self) -> BatchSummary:
        return self._execute(resume_only=True)

    def status(self) -> BatchSummary:
        plans = {plan.key: plan for plan in discover_tasks(self.config)}
        records = self.state.items()
        keys = sorted(set(plans) | set(records))
        statuses = []
        for key in keys:
            record = records.get(key)
            if record is not None:
                statuses.append(record.status)
            elif plans[key].output_path.exists():
                statuses.append(TaskStatus.SKIPPED)
            else:
                statuses.append(TaskStatus.PENDING)
        return _summary(statuses)

    def _execute(self, resume_only: bool) -> BatchSummary:
        statuses: list[TaskStatus] = []
        if self.client is None:
            self.client = PylingualClient(self.config.base_url, self.config.request_timeout)
        try:
            with RunLock(self.config.lock_path):
                work: list[tuple[TaskPlan, TaskRecord | None]] = []
                for plan in discover_tasks(self.config):
                    record = self.state.get(plan.key)
                    if resume_only and not _has_identifier(record):
                        statuses.append(record.status if record else TaskStatus.PENDING)
                    else:
                        work.append((plan, record))
                if self.config.concurrency == 1:
                    statuses.extend(self._process(plan, record) for plan, record in work)
                else:
                    with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
                        statuses.extend(executor.map(lambda args: self._process(*args), work))
        finally:
            if self._owns_client and self.client is not None:
                self.client.close()
                self.client = None
        return _summary(statuses)

    def _process(self, plan: TaskPlan, record: TaskRecord | None) -> TaskStatus:
        if plan.output_path.exists() and not self.config.reupload:
            self.state.set(plan.key, TaskRecord(TaskStatus.SKIPPED))
            return TaskStatus.SKIPPED

        if record and record.status in _FINAL_FAILURE and not self.config.reupload:
            return record.status

        identifier = None
        is_new_upload = False
        if not self.config.reupload and record and record.status in _RESUMABLE:
            identifier = record.identifier

        if identifier is None:
            if not self.gate.before_upload():
                return TaskStatus.PENDING
            attempts = (record.attempts if record else 0) + 1
            try:
                upload = self._client().upload(plan.input_path)
                identifier = upload.identifier
                is_new_upload = True
                record = TaskRecord(
                    TaskStatus.UPLOADED,
                    identifier=identifier,
                    attempts=attempts,
                )
                self.state.set(plan.key, record)
            except ApiError as exc:
                self.state.set(
                    plan.key,
                    TaskRecord(TaskStatus.UPLOAD_FAIL, attempts=attempts, error=str(exc)),
                )
                return TaskStatus.UPLOAD_FAIL

        return self._poll_and_write(
            plan,
            identifier,
            record or TaskRecord(TaskStatus.UPLOADED),
            observe_queue=is_new_upload,
        )

    def _poll_and_write(
        self,
        plan: TaskPlan,
        identifier: str,
        record: TaskRecord,
        *,
        observe_queue: bool,
    ) -> TaskStatus:
        started = time.monotonic()
        observed_upload = observe_queue
        while True:
            if time.monotonic() - started >= self.config.poll_timeout:
                self.state.set(
                    plan.key,
                    replace(record, status=TaskStatus.TIMEOUT, identifier=identifier),
                )
                return TaskStatus.TIMEOUT
            try:
                progress = self._client().poll(identifier)
                record = replace(
                    record,
                    status=TaskStatus.UPLOADED,
                    identifier=identifier,
                    last_stage=progress.stage,
                    last_position=progress.position,
                    error=progress.message,
                )
                self.state.set(plan.key, record)
                if observed_upload:
                    self.gate.observe_upload(progress.position)
                    observed_upload = False
                if _is_complete(progress):
                    source = self._client().fetch_source(identifier)
                    if not source.decompilation_successful:
                        raise PermanentDecompilerError("decompilation was unsuccessful")
                    if not source.source:
                        self.state.set(plan.key, replace(record, status=TaskStatus.EMPTY))
                        return TaskStatus.EMPTY
                    _atomic_write(plan.output_path, source.source)
                    self.state.mark_done(plan.key)
                    return TaskStatus.DONE
            except PermanentDecompilerError as exc:
                self.state.set(
                    plan.key,
                    replace(
                        record,
                        status=TaskStatus.DECOMPILER_ERROR,
                        identifier=identifier,
                        error=str(exc),
                    ),
                )
                return TaskStatus.DECOMPILER_ERROR
            except ApiError as exc:
                self.state.set(
                    plan.key,
                    replace(
                        record,
                        status=TaskStatus.FAILED,
                        identifier=identifier,
                        error=str(exc),
                    ),
                )
                return TaskStatus.FAILED
            self.sleep(self.config.poll_interval)


def _has_identifier(record: TaskRecord | None) -> bool:
    return bool(record and record.identifier and record.status in _RESUMABLE)


def _is_complete(progress: ProgressResponse) -> bool:
    stage = (progress.stage or "").lower()
    return stage in _DONE_STAGES


def _atomic_write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _summary(statuses: list[TaskStatus]) -> BatchSummary:
    succeeded = statuses.count(TaskStatus.DONE)
    skipped = statuses.count(TaskStatus.SKIPPED)
    failed = sum(
        status in _FINAL_FAILURE or status is TaskStatus.UPLOAD_FAIL for status in statuses
    )
    deferred = len(statuses) - succeeded - skipped - failed
    return BatchSummary(len(statuses), succeeded, skipped, failed, deferred)
