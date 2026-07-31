from pathlib import Path

import pytest

from pylingual_web_batch.errors import ConfigurationError
from pylingual_web_batch.models import BatchConfig, TaskStatus


def test_batch_config_rejects_invalid_limits(tmp_path: Path):
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, concurrency=0)
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, queue_limit=0)
    with pytest.raises(ConfigurationError):
        BatchConfig(tmp_path, tmp_path, poll_interval=0)


def test_task_status_is_serializable():
    assert TaskStatus.TIMEOUT.value == "timeout"
