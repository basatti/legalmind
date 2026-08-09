# Running LegalMind locally

Everything needed to get the app up and log in. For dependency setup and the
lint/type/test commands, see the root `README.md`.

## Before you start

- **Postgres must be running.** It runs natively on this machine — Docker
  Desktop is not required just to start the app.
- Dependencies installed once: `cd backend && uv sync --extra dev`, and
  `cd frontend && npm install`.
- `backend/.env` must exist. Copy `backend/.env.example` and fill it in if it
  does not.

## Three terminals

**1. Backend — FastAPI on port 8000**

```bash
cd backend
uv run uvicorn main:app --app-dir src --reload
```

`--reload` restarts on every save. `--app-dir src` is what puts `src` on the
Python path.

**2. Frontend — Next.js on port 3000**

```bash
cd frontend
npm run dev
```

Next.js, not plain React, so it is `npm run dev` and not `npm start`.

**3. Worker — only needed if uploads should become searchable**

```bash
cd backend/src
uv run python -m worker_main
```

Run from `src`, because `python -m worker_main` has no equivalent of uvicorn's
`--app-dir` flag.

Without this terminal, uploads still succeed — the document is stored and
visible — but its ingestion job sits at `PENDING` for ever and nothing about
its contents is searchable.

## All at once, with Docker

The three terminals above are the day-to-day way to work. For a demo, or to
check the stack runs as a unit, compose brings up everything — Postgres,
migrations, API, worker and frontend — from one command.

**`backend/.env` has to exist first, and two of its values have to be real.**
`COMPANY_API_URL` and `COMPANY_API_KEY` ship as placeholders in
`.env.example`; ask the team for the working ones. Without them the app still
starts and login works, but upload, ingestion and ask all fail — the worker
cannot reach the embedding gateway.

```bash
cp backend/.env.example backend/.env   # then fill in the two company values
docker compose up --build
```

The first run takes several minutes while the images build; after that it is
seconds. Addresses are the same as the table below.

What differs from the three-terminal setup:

- **Migrations run themselves.** A one-shot `migrate` service runs
  `alembic upgrade head` and exits, and `app` and `worker` do not start until
  it has exited cleanly. It is a separate service on purpose: `app` and
  `worker` are the same image started at the same moment, so migrating from
  shared startup code would have both of them racing through the same chain.
- **The worker is always running**, so uploads become searchable without a
  third terminal.
- **Uploads live in a Docker volume**, `document_storage`, mounted into both
  `app` and `worker`. They are separate containers with separate filesystems,
  so without that shared volume ingestion fails with a file-not-found even
  though the upload succeeded.

Stopping:

```bash
docker compose down      # keeps the database and uploaded documents
docker compose down -v   # deletes both, permanently
```

### Langfuse is not part of this

Tracing lives in its own file and is entirely optional — six extra containers
that the app does not need:

```bash
docker compose -f docker-compose.langfuse.yml up -d
```

It declares its own project name, `legalmind-langfuse`, so the two stacks
cannot share a network or delete each other's containers. They used to: both
defaulted to the project name `legalmind`, which made `--remove-orphans` on
either one destructive to the other.

One catch: `LANGFUSE_BASE_URL=http://localhost:3001` only works when the
backend runs natively. Inside a container `localhost` means that container, so
a containerised app cannot reach Langfuse that way — it would need
`http://host.docker.internal:3001`.

A fresh Langfuse database shows a signup screen and issues new API keys. To
keep the keys already in `backend/.env`, set the `LANGFUSE_INIT_*` variables in
a root `.env` before the first start — see the list near the top of
`docker-compose.langfuse.yml`.

## Where things live

| what | address |
|---|---|
| the app | <http://localhost:3000> |
| the API | <http://localhost:8000> |
| Swagger UI (interactive, "Try it out") | <http://localhost:8000/docs> |
| ReDoc (read-only, easier to skim) | <http://localhost:8000/redoc> |
| the raw OpenAPI spec | <http://localhost:8000/openapi.json> |

Swagger UI and ReDoc are two viewers of the same spec, which FastAPI generates
from the route signatures and Pydantic schemas. Neither is written by hand.

## Logging in

The first admin is created by migration `dd761b9ccc7b`, not by hand:

- **`admin@legalmind.com`** / **`ChangeMe123!`**

It is flagged `must_change_password`, and while that flag is set the backend
refuses *every other endpoint* with `403 Password change required` — including
creating users. Change the password first, at
<http://localhost:3000/change-password>.

New passwords need at least 8 characters, at least one letter and at least one
digit.

## Demo data

An empty database has the admin account and nothing else. To get a queryable
corpus — three users, two cases, assignments and 256 embedded chunks — in about
twenty seconds:

```bash
cd backend
uv run python scripts/seed_demo.py
```

`--reset` rebuilds it from scratch, `--cleanup` removes it, `--limit N` seeds a
small subset for a quick check. It only ever touches what it created, so it is
safe to run against a database that already has real work in it.

The three accounts all share the password printed by the script. Their
assignments are arranged so the authorization behaviour can be shown rather than
described: ask the attorney's account a question that only the contract case can
answer and it refuses, while the partner answers it and cites the source.

Embeddings are real calls to the company gateway, so this needs the VPN. The
corpus itself ships with the repo at `backend/seed/labor_law_corpus.jsonl` — no
network fetch, so it works on demo day regardless of whether hrsd.gov.sa is up.

## The three env files

| file | committed | purpose |
|---|---|---|
| `backend/.env` | no | real local config: dev `DATABASE_URL`, company gateway URL, key, model names |
| `backend/.env.example` | yes | template with the same keys and placeholder values |
| `backend/.env.test` | yes | `DATABASE_URL` for `legalmind_test`; force-loaded by `conftest.py` so tests can never hit the dev database |

The frontend needs no env file — `lib/api-client.ts` defaults to
`http://localhost:8000`. Set `NEXT_PUBLIC_API_URL` only to point somewhere else.

## When something is wrong

**Any documents page returns 500, or a query mentions a column that does not
exist.** The dev database is behind the migrations:

```bash
cd backend
uv run alembic upgrade head
```

**Login returns 422 rather than 401.** The email failed validation before the
password was ever checked. Reserved TLDs such as `.local` are rejected by
`EmailStr`.

**Every API call returns 403 "Password change required".** The logged-in user
still has `must_change_password` set. Change the password; nothing else works
until then.

**The frontend renders something stale, or throws an odd module error.** Delete
`frontend/.next` and restart `npm run dev`. Not worth debugging.

**An upload never becomes searchable.** The worker is not running — see
terminal 3.

If the worker *is* running and the job shows `failed` with a file-not-found,
the API and the worker are writing to and reading from different storage roots.
Both default to `backend/storage/documents` as an absolute path, so this should
not happen locally; if they run in separate containers, `STORAGE_DIR` has to
point both at the same mounted volume.

## Never do this

Do not run `pytest` from the repo root. It must run from `backend/`. The test
fixtures call `drop_all()`, and in July a relative path in `conftest.py` meant
`DATABASE_URL` fell through to the real dev database, which was destroyed while
176 tests reported success. Both a path fix and a guard requiring `_test` in the
database name are in place now, but the habit is still worth keeping.
