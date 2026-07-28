# legalmind
A system for CS students to practice.
# LegalMind

## Structure

```
.
├── main.py          # FastAPI app entry point
├── Makefile          # run lint/type-check/test from the repo root
├── backend/            # Python tooling & dependencies (uv, ruff, mypy, pytest)
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/foundation/
│   └── tests/
└── frontend/             # Next.js app (TypeScript, ESLint)
    ├── package.json
    └── app/
```

`main.py` is the FastAPI application entry point and lives at the repo root.
Python dependencies and tooling configuration (`uv`, `ruff`, `mypy`,
`pytest`) live under `backend/`.

## Setup

**Backend:**

```bash
cd backend
uv sync --extra dev
```

**Frontend:**

```bash
cd frontend
npm install
```

## Running checks

From the repo root:

```bash
make check       # lint + format-check + typecheck + test (backend) + lint (frontend)
```

Individually:

```bash
make lint          # backend: ruff check
make format         # backend: ruff format --check
make typecheck       # backend: mypy
make test             # backend: pytest
make fe-lint           # frontend: eslint
```

See `backend/README.md` and `frontend/README.md` for stack-specific details.

## Stack

- **Backend:** Python ≥ 3.11, managed with `uv`. Linted/formatted with
  `ruff`, type-checked with `mypy`, tested with `pytest`.
- **Frontend:** Next.js (App Router) + TypeScript, linted with ESLint.