# Contributing

## Before you start

```bash
git pull
```

Make sure you're up to date before branching off or making changes — avoids
conflicts and duplicate work later.

## Workflow

1. Make your changes.
2. Run the checks locally, from the repo root:

   ```bash
   make check
   ```

   This runs the exact same lint/format/typecheck/test steps CI runs (see
   `.github/workflows/ci.yml`). Catching a failure here is private; catching
   it in CI is a red ❌ on your PR that everyone sees.

   `make` isn't available by default on Windows/PowerShell. If `make check`
   isn't recognized, run the same 4 checks manually instead:

   ```bash
   cd backend
   uv run ruff check .            # lint — flags style issues (e.g. missing newline, unused imports)
   uv run ruff format --check .   # formatting — confirms code matches the project's formatting rules
   uv run mypy                    # type check — catches wrong-type arguments before the code ever runs
   uv run pytest                  # tests — actually runs the test suite and reports pass/fail
   ```

3. Stage only the files you actually changed:

   ```bash
   git add path/to/file1 path/to/file2
   ```

   Avoid `git add -A` / `git add .` — it's easy to accidentally stage
   `.env`, build artifacts, or unrelated in-progress files.

4. Commit with a message that references the ticket:

   ```bash
   git commit -m "LEG-XX: short description of what changed"
   ```

   Describe *what changed*, not "fix stuff" — e.g.
   `LEG-19: Align User model with spec, add Session table and repositories`.

5. Push:

   ```bash
   git push
   ```

## If your change touches `backend/src/foundation/models.py`

A model change needs a matching Alembic migration — the two should always be
committed together.

1. Generate it:

   ```bash
   cd backend
   uv run alembic revision --autogenerate -m "describe the schema change"
   ```

2. **Open the generated file in `backend/migrations/versions/` before
   applying it.** Autogenerate has a known gap: if a field uses SQLModel's
   string type, the generated file references `sqlmodel.sql.sqltypes.AutoString`
   but doesn't always add `import sqlmodel` — the migration crashes with
   `NameError` if you don't add it by hand.
3. Apply and confirm it actually runs:

   ```bash
   uv run alembic upgrade head
   ```
4. Commit the migration file alongside your model change.

## Why this matters

CI only catches problems *after* your code is already pushed and visible to
everyone. Running `make check` (and, for schema changes, actually applying
the migration) locally first means broken code never leaves your machine.
