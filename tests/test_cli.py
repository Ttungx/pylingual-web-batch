from pathlib import Path

from pylingual_web_batch.cli import build_parser, main
from pylingual_web_batch.models import BatchSummary


def test_run_parser_defaults_and_reupload():
    args = build_parser().parse_args(["run", "input", "-o", "output", "--reupload"])
    assert args.jobs == 1
    assert args.queue_limit == 10
    assert args.poll_timeout == 7200.0
    assert args.poll_interval == 10.0
    assert args.reupload is True


def test_dispatches_all_commands(monkeypatch, tmp_path: Path):
    calls = []

    class FakeBatch:
        def __init__(self, config):
            calls.append(("init", config))

        def run(self):
            calls.append(("run", None))
            return BatchSummary(1, 1, 0, 0, 0)

        def resume(self):
            calls.append(("resume", None))
            return BatchSummary(1, 0, 0, 1, 0)

        def status(self):
            calls.append(("status", None))
            return BatchSummary(1, 0, 0, 0, 1)

    monkeypatch.setattr("pylingual_web_batch.cli.BatchDecompiler", FakeBatch)
    assert main(["run", str(tmp_path), "-o", str(tmp_path / "out")]) == 0
    assert main(["resume", "--state", str(tmp_path / "state.json")]) == 1
    assert main(["status", "--state", str(tmp_path / "state.json")]) == 0
    assert [call[0] for call in calls if call[0] != "init"] == ["run", "resume", "status"]


def test_invalid_jobs_returns_two(tmp_path: Path):
    assert main(["run", str(tmp_path), "-o", str(tmp_path / "out"), "--jobs", "0"]) == 2
