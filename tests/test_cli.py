import json
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


def test_parser_supports_lock_file_and_jsonl():
    args = build_parser().parse_args(
        [
            "run",
            "input",
            "-o",
            "output",
            "--lock-file",
            "custom.lock",
            "--log-format",
            "jsonl",
        ]
    )

    assert args.lock_path == Path("custom.lock")
    assert args.log_format == "jsonl"


def test_jsonl_summary_is_structured(monkeypatch, capsys, tmp_path: Path):
    class FakeBatch:
        def __init__(self, config):
            pass

        def status(self):
            return BatchSummary(2, 1, 0, 0, 1)

    monkeypatch.setattr("pylingual_web_batch.cli.BatchDecompiler", FakeBatch)

    assert main(["status", "--state", str(tmp_path / "state.json"), "--log-format", "jsonl"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "event": "summary",
        "total": 2,
        "succeeded": 1,
        "skipped": 0,
        "failed": 0,
        "deferred": 1,
    }


def test_invalid_base_url_returns_two(tmp_path: Path):
    assert (
        main(
            [
                "run",
                str(tmp_path),
                "-o",
                str(tmp_path / "out"),
                "--base-url",
                "not a url",
            ]
        )
        == 2
    )


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
