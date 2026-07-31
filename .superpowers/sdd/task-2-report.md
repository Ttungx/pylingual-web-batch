# Task 2 Report

## Summary
Implemented the package models and public error types required by Task 2, added validation for `BatchConfig`, and exported the requested public symbols from the package root.

## Files changed
- `src/pylingual_web_batch/models.py`
- `src/pylingual_web_batch/errors.py`
- `src/pylingual_web_batch/__init__.py`
- `tests/test_models.py`

## Validation
- `python -m pytest tests/test_models.py -q`
- `python -m pytest -q`
- `ruff check src tests`

## Notes
- `BatchConfig` normalizes path-like inputs to `Path` in `__post_init__`.
- Validation raises `ConfigurationError` for invalid concurrency, queue limit, timeout, and poll interval values.
- Only the requested public models were exported from `pylingual_web_batch.__init__`.
