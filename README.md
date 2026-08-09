# LegalMind

An AI paralegal: lawyers upload case documents, ask questions in natural
language, and get answers grounded in those documents with citations back to
the source. It is a co-op training project — the CS concepts are the point, and
the product is how they get exercised.

## Structure

```
.
├── Makefile              # run lint/type-check/test from the repo root
├── docker-compose.yml    # db, app, worker
├── docs/                 # setup, observability, eval results, authorization
├── backend/              # FastAPI service (uv, ruff, mypy, pytest)
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── migrations/       # Alembic schema migrations
│   ├── evals/            # gold set + recorded eval runs
│   ├── tests/
│   └── src/
│       ├── main.py           # FastAPI app entry point
│       ├── worker_main.py    # ingestion worker entry point
│       ├── routers/          # HTTP endpoints
│       ├── services/         # auth, ingestion, retrieval, answering
│       ├── repositories/     # database access
│       ├── graph/            # LangGraph RAG flow
│       ├── embeddings/       # bge-m3 embedding providers
│       ├── chunkers/         # document chunking strategies
│       ├── parsers/          # PDF and document parsing
│       ├── observability/    # Langfuse tracing
│       └── foundation/       # models, authorization, permissions, storage
└── frontend/             # Next.js app (TypeScript, ESLint)
    ├── package.json
    ├── app/              # App Router pages
    ├── components/
    └── lib/
```

The FastAPI application entry point is `backend/src/main.py`; the ingestion
worker starts from `backend/src/worker_main.py`. Python dependencies and tooling
configuration (`uv`, `ruff`, `mypy`, `pytest`) live under `backend/`.

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

## Running the app

See [`docs/running-locally.md`](docs/running-locally.md) — the three terminals,
the URLs, the login, and what to check when something does not work.

## Observability

See [`docs/observability.md`](docs/observability.md) — running Langfuse locally,
reading a trace to debug a wrong answer, and what to do when there are none.

## Answer quality

See [`docs/eval-results.md`](docs/eval-results.md) — every recorded eval run and
what it measured. Generated from `backend/evals/history.jsonl`; read the spread
before the mean, and treat a single-round run as measuring that run rather than
the system.

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