from __future__ import annotations

from pathlib import Path, PurePosixPath

from .models import BatchConfig, TaskPlan

__all__ = ["discover_tasks", "map_output"]


def map_output(input_path: Path, input_root: Path, output_root: Path) -> Path:
    """Map an input .pyc path to its output .py path under the output root."""
    input_path = Path(input_path)
    input_root = Path(input_root)
    output_root = Path(output_root)

    relative = input_path.relative_to(input_root)
    return output_root / relative.with_suffix(".py")


def discover_tasks(config: BatchConfig) -> list[TaskPlan]:
    """Discover batch tasks under the configured input directory."""
    input_root = Path(config.input_dir)
    output_root = Path(config.output_dir)
    tasks: list[TaskPlan] = []

    for input_path in input_root.rglob("*.pyc"):
        relative = input_path.relative_to(input_root)
        if "__pycache__" in relative.parts:
            continue

        key = relative.as_posix()
        if not _matches_any(key, config.include):
            continue
        if config.exclude and _matches_any(key, config.exclude):
            continue

        tasks.append(
            TaskPlan(
                key=key,
                input_path=input_path,
                output_path=map_output(input_path, input_root, output_root),
            )
        )

    tasks.sort(key=lambda task: task.key)
    return tasks


def _matches_any(key: str, patterns: tuple[str, ...]) -> bool:
    path = PurePosixPath(key)
    return any(path.match(pattern) for pattern in patterns)
