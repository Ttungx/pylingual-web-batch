from pathlib import Path

from pylingual_web_batch.discovery import discover_tasks, map_output
from pylingual_web_batch.models import BatchConfig


def test_discovery_applies_include_and_exclude_globs_and_skips_pycache(tmp_path: Path):
    root = tmp_path / "input"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "keep.pyc").write_bytes(b"keep")
    (root / "pkg" / "skip.pyc").write_bytes(b"skip")
    (root / "other.pyc").write_bytes(b"other")
    (root / "pkg" / "keep.py").write_text("ignored")
    (root / "pkg" / "__pycache__").mkdir()
    (root / "pkg" / "__pycache__" / "cached.pyc").write_bytes(b"cached")

    config = BatchConfig(root, tmp_path / "out", include=("pkg/*.pyc",), exclude=("pkg/skip*.pyc",))
    tasks = discover_tasks(config)

    assert [task.key for task in tasks] == ["pkg/keep.pyc"]
    assert tasks[0].output_path == tmp_path / "out" / "pkg" / "keep.py"


def test_map_output_preserves_relative_structure_and_suffix(tmp_path: Path):
    source = tmp_path / "in" / "nested" / "module.pyc"

    expected = tmp_path / "out" / "nested" / "module.py"
    assert map_output(source, tmp_path / "in", tmp_path / "out") == expected
