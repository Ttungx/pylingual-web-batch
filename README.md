# pylingual-web-batch

[English](README.md) | [简体中文](README.zh-CN.md)

Resumable, queue-aware batch decompilation through the pylingual Web API.

## Installation

The project has not been published to PyPI. Install it from GitHub or a local checkout:

```bash
python -m pip install "git+https://github.com/ttungx/pylingual-web-batch.git"
```

After a future PyPI release, installation will be:

```bash
python -m pip install pylingual-web-batch
```

## Quick start

Place authorized bytecode files under an input directory and run:

```bash
pylingual-web-batch run ./input -o ./output
```

Inputs are discovered recursively. The default include pattern is `*.pyc`; use comma-separated
`--include` and `--exclude` patterns to customize selection. Existing outputs are skipped unless
`--reupload` is explicit.

Useful options:

```bash
pylingual-web-batch run ./input -o ./output \
  --state ./.pylingual-state.json --jobs 1 --queue-limit 10 \
  --poll-timeout 7200 --poll-interval 10
pylingual-web-batch resume --state ./.pylingual-state.json \
  --input ./input --output ./output
pylingual-web-batch status --state ./.pylingual-state.json \
  --input ./input --output ./output
```

`run` discovers all matching files and resumes usable identifiers before creating uploads.
`resume` processes only resumable identifiers already in state. `status` reads local state and does
not make API requests.

## Recovery, queue, and failure behavior

State is versioned JSON written atomically after each transition. A local polling timeout preserves
the server identifier. A later run resumes polling that identifier instead of uploading the file
again. Source outputs are also replaced atomically.

Queue gating applies only to newly uploaded tasks. An observed `position < 10` permits another new
upload with the default limit; `position >= 10` stops subsequent new uploads for that batch.
Resumed tasks bypass the gate. The gate limit is configurable with `--queue-limit`.

| Status | Meaning | Next run |
|---|---|---|
| `timeout` | Local polling deadline reached | Resume same identifier |
| `decompiler_error` | Server returned permanent failure | Skip unless `--reupload` |
| `upload_fail` | Upload did not complete | Retry on next run |
| `done` | Source fetched and written | Skip if output exists |

Only `--reupload` allows an existing output or permanent decompiler failure to be attempted again.
Normal console messages do not include full API identifiers.

## Python API

```python
from pathlib import Path

from pylingual_web_batch import BatchConfig, BatchDecompiler

config = BatchConfig(
    input_dir=Path("./input"),
    output_dir=Path("./output"),
    concurrency=1,
    queue_limit=10,
)
print(BatchDecompiler(config).run())
```

See [`examples/basic.py`](examples/basic.py) and
[`examples/configuration.toml`](examples/configuration.toml).

## Security and authorization

`.pyc` files can contain sensitive or proprietary code. Upload only files you are authorized to
process and comply with pylingual's service terms. API identifiers act like task credentials; do
not disclose them. Do not commit input bytecode, state, output source, logs, credentials, or API
tokens. The provided `.gitignore` excludes common generated and sensitive files, but users remain
responsible for repository hygiene.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python -m build
```

Tests use `httpx.MockTransport` and never call the live pylingual API. GitHub Actions tests Python
3.10 through 3.13 and builds distributions. Tagged releases attach artifacts to GitHub Releases;
there is intentionally no PyPI publishing step.
