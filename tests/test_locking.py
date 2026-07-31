from pathlib import Path

import pytest

from pylingual_web_batch.errors import LockError
from pylingual_web_batch.locking import RunLock


def test_run_lock_rejects_second_holder_and_can_be_reacquired(tmp_path: Path):
    path = tmp_path / "run.lock"
    first = RunLock(path)
    second = RunLock(path)
    first.acquire()
    try:
        with pytest.raises(LockError):
            second.acquire()
    finally:
        first.release()

    with second:
        assert path.exists()
