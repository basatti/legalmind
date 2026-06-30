# Backend

Python service. Managed with `uv`; linted/formatted with `ruff`, type-checked
with `mypy`, tested with `pytest`.

## Setup

```bash
cd backend
uv sync --extra dev
```

## Commands

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy                    # type-check
uv run pytest                  # tests
```

Or from the repo root, use the `make` targets (see root README).
