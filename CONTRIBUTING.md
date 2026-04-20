# Contributing to context-bench

## Development setup

```bash
git clone https://github.com/nessos666/context-bench.git
cd context-bench
python3 -m pytest tests/ -v
```

## Running tests

```bash
python3 -m pytest tests/ -v
```

All tests must pass before submitting a pull request.

## Code style

- Python 3.10+
- Type annotations on all public functions
- `from __future__ import annotations` at top of every module

## Pull requests

1. Fork the repo
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit PR against `main`
