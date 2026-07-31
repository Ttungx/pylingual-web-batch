from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .batch import BatchDecompiler
from .errors import ConfigurationError, LockError, StateError
from .models import BatchConfig, BatchSummary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pylingual-web-batch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="discover and decompile input files")
    run.add_argument("input", type=Path)
    run.add_argument("-o", "--output", type=Path, required=True)
    _add_common_options(run)

    for name, help_text in (
        ("resume", "resume identifiers in a state file"),
        ("status", "summarize a state file without network access"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--state", type=Path, required=True)
        command.add_argument("--input", type=Path, default=Path("."))
        command.add_argument("--output", type=Path, default=Path("."))
        command.add_argument(
            "--lock-file",
            "--lock",
            dest="lock_path",
            type=Path,
            default=Path(".pylingual-batch.lock"),
        )
        command.add_argument("--log-format", choices=("text", "jsonl"), default="text")
        command.add_argument("--base-url", default="https://api.pylingual.io")
        command.add_argument("--poll-timeout", type=float, default=7200.0)
        command.add_argument("--poll-interval", type=float, default=10.0)
        command.add_argument("--request-timeout", type=float, default=90.0)
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, default=Path(".pylingual-state.json"))
    parser.add_argument(
        "--lock-file",
        "--lock",
        dest="lock_path",
        type=Path,
        default=Path(".pylingual-batch.lock"),
    )
    parser.add_argument("--log-format", choices=("text", "jsonl"), default="text")
    parser.add_argument("--base-url", default="https://api.pylingual.io")
    parser.add_argument("-j", "--jobs", type=int, default=1)
    parser.add_argument("--queue-limit", type=int, default=10)
    parser.add_argument("--poll-timeout", type=float, default=7200.0)
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--request-timeout", type=float, default=90.0)
    parser.add_argument("--include", default="*.pyc")
    parser.add_argument("--exclude", default="")
    parser.add_argument("--reupload", action="store_true")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = _config_from_args(args)
        decompiler = BatchDecompiler(config)
        summary = getattr(decompiler, args.command)()
        _print_summary(summary, args.log_format)
        return 1 if summary.failed else 0
    except (ConfigurationError, StateError, LockError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _config_from_args(args: argparse.Namespace) -> BatchConfig:
    if args.command == "run":
        return BatchConfig(
            input_dir=args.input,
            output_dir=args.output,
            state_path=args.state,
            lock_path=args.lock_path,
            base_url=args.base_url,
            concurrency=args.jobs,
            queue_limit=args.queue_limit,
            poll_timeout=args.poll_timeout,
            poll_interval=args.poll_interval,
            request_timeout=args.request_timeout,
            reupload=args.reupload,
            include=_patterns(args.include, ("*.pyc",)),
            exclude=_patterns(args.exclude, ()),
        )
    return BatchConfig(
        input_dir=args.input,
        output_dir=args.output,
        state_path=args.state,
        lock_path=args.lock_path,
        base_url=args.base_url,
        poll_timeout=args.poll_timeout,
        poll_interval=args.poll_interval,
        request_timeout=args.request_timeout,
    )


def _patterns(raw: str, default: tuple[str, ...]) -> tuple[str, ...]:
    patterns = tuple(item.strip() for item in raw.split(",") if item.strip())
    return patterns or default


def _print_summary(summary: BatchSummary, log_format: str = "text") -> None:
    if log_format == "jsonl":
        print(
            json.dumps(
                {
                    "event": "summary",
                    "total": summary.total,
                    "succeeded": summary.succeeded,
                    "skipped": summary.skipped,
                    "failed": summary.failed,
                    "deferred": summary.deferred,
                },
                separators=(",", ":"),
            )
        )
        return
    print(
        f"total={summary.total} succeeded={summary.succeeded} skipped={summary.skipped} "
        f"failed={summary.failed} deferred={summary.deferred}"
    )
