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


def test_discovery_is_sorted_and_custom_include_recurses(tmp_path: Path):
    root = tmp_path / "input"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "z" / "last.bin").write_bytes(b"z")
    (root / "a" / "first.bin").write_bytes(b"a")

    tasks = discover_tasks(BatchConfig(root, tmp_path / "out", include=("*.bin",)))

    assert [task.key for task in tasks] == ["a/first.bin", "z/last.bin"]


def test_glob_pattern_is_anchored_to_whole_relative_key(tmp_path: Path):
    root = tmp_path / "input"
    (root / "pkg").mkdir(parents=True)
    (root / "deep" / "pkg").mkdir(parents=True)
    (root / "pkg" / "direct.pyc").write_bytes(b"x")
    (root / "deep" / "pkg" / "nested.pyc").write_bytes(b"x")

    tasks = discover_tasks(BatchConfig(root, tmp_path / "out", include=("pkg/*.pyc",)))

    assert [task.key for task in tasks] == ["pkg/direct.pyc"]


def test_map_output_preserves_relative_structure_and_suffix(tmp_path: Path):
    source = tmp_path / "in" / "nested" / "module.pyc"

    expected = tmp_path / "out" / "nested" / "module.py"
    assert map_output(source, tmp_path / "in", tmp_path / "out") == expected


def test_map_output_rejects_resolved_outside_root_path(tmp_path: Path):
    root = tmp_path / "in"
    root.mkdir()

    for source in (root / ".." / "escape.pyc", tmp_path / "other" / "escape.pyc"):
        try:
            map_output(source, root, tmp_path / "out")
        except ValueError:
            pass
        else:
            raise AssertionError("outside-root input must be rejected")
