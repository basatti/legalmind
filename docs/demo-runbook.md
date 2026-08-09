# Demo runbook (LEG-99)

Everything needed to give the 15-minute demo and survive it going wrong. Timings
below are measured on the compose stack, not estimated.

## Pre-flight, 30 minutes before

Do these in order. Every one of them has failed silently at least once.

1. **Tailscale up.** The embedding and LLM calls go to the company gateway over
   the VPN. Without it every question returns "no answer" — which looks exactly
   like a broken product, not a missing connection.

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" --max-time 8 https://ai-worker2.tail6156a3.ts.net:8443/v1/models
   ```

   `401` is correct — it means reachable. A timeout means no VPN.

2. **`backend/.env` has the real values.** `COMPANY_API_URL` and
   `COMPANY_API_KEY` are placeholders in `.env.example` (`https://example.invalid`,
   `sk-changeme`). A clean clone cannot ingest or answer without them.

3. **Bring the stack up.**

   ```bash
   docker compose up -d
   ```

   About 30 seconds when the images already exist, ~10 minutes if they have to
   build. Build the night before, not on the day. Startup is ordered: `db`
   healthy → `migrate` runs the Alembic chain and exits 0 → `app` and `worker`
   → `frontend` waits for `app` to be healthy.

4. **Rebuild the dataset.**

   ```bash
   cd backend && uv run python scripts/seed_demo.py --reset
   ```

   22 seconds. Prints the case ids, the three logins and the demo questions.

5. **Hide the clutter.** A partner sees *every* case. Any leftover scratch case
   — `gta6`, `RAG smoke test` — is on screen during the demo, and worse, the
   labor-law question cites documents from both the seeded case and the old
   smoke-test case, so the audience sees two sources for the same law. Delete or
   rename them beforehand.

6. **Ask one question and watch it answer.** Not optional. It is the only check
   that covers the VPN, the gateway, the corpus and the graph at once.

## Timings

| | measured |
|---|---|
| `docker compose up -d`, images present | ~30s |
| image build from cold | ~10 min |
| `seed_demo.py --reset` | 22s |
| login | 0.5–1.6s |
| open a case, list documents | instant |
| a question, answered | **10–12s** |
| a question, refused on authorization | 12s |
| upload a document | 1.4s |
| worker ingests it | **8s** |

**The whole demo path is 43.5 seconds of machine time**, measured end to end on
the compose stack: sign in → open case → ask → switch user → refusal → upload →
ingest → ask again. In a fifteen-minute slot that leaves roughly fourteen minutes
of talking, so the constraint is your script, not the system.

**Every question costs ten seconds of silence.** Four questions is over a minute
of dead air in a fifteen-minute slot. Plan what you say while it thinks — that is
the natural place to explain what is happening underneath.

A refusal takes just as long as an answer, because the attorney *is* assigned to
a case: retrieval runs, finds nothing relevant inside their scope, and the model
reports NOT_FOUND. Nothing is short-circuited.

## The 15 minutes

| min | what | notes |
|---|---|---|
| 0–1 | What it is: a lawyer uploads case documents and asks questions in natural language, answers cite the source | one sentence, no architecture yet |
| 1–3 | Sign in as the partner, open the labor-law case, show the documents | |
| 3–6 | Ask the labor question. Talk through retrieval while it runs. Show the citation | the 10s gap is your explanation window |
| 6–9 | **The authorization moment** — sign in as the attorney, ask the contract question, get the clean refusal | the strongest thing you have; do not rush it |
| 9–12 | Upload a document live, let the worker ingest it, ask about it | 8s from upload to searchable — short enough to watch, long enough to narrate |
| 12–15 | The three decisions, then questions | |

## The three design decisions

Each has evidence in the repo. Do not claim more than these support.

### 1. Authorization is resolved once, at the front door, and travels as a value

`RagService.ask()` calls `CaseReader.authorized_cases(user)` and gets back an
`AuthorizedCases` — either `AllCases` or `TheseCases(frozenset)`. That value goes
into the graph state and is read by the retrieve node on every pass. No node
recomputes it or looks at the user.

Two things make it hold rather than being a convention:

- **The two cases are different types.** "May see everything" and "assigned to
  nothing" were both an empty list before, so a missed branch turned a permission
  failure into unrestricted access. `AllCases` and `TheseCases(frozenset())`
  cannot be confused.
- **The filter is inside the SQL**, before ranking: `WHERE case_id IN (...)` then
  `ORDER BY ... LIMIT k`. There is no code path that can produce a chunk outside
  the authorized set, so there is nothing to forget to call.

*Evidence:* `docs/retrieval-authorization.md`, `foundation/authorization.py`, and
the live refusal in the demo.

*Expect to be asked:* "Why not just filter the results afterwards?" — because
post-filtering has two failure modes: it silently under-fetches when all top-k
belong to unauthorized cases, and a refactor that drops the filter step leaks a
document instead of merely being slow.

### 2. The multi-step retrieval loop is built, tested, and turned off

`RAG_MULTI_STEP_ENABLED` defaults to off. The reason/retrieve loop is wired and
capped at `MAX_ITERATIONS = 3`, and it is disabled because when it was measured
it made answers *worse*: a compound question produced near-identical
sub-questions, pulled in unrelated passages, and the model returned NOT_FOUND
where a single pass had answered correctly.

The code stays wired but unreachable so there is one graph shape to reason about
rather than two. Turning it on is one environment variable once the sub-question
prompt earns it.

*Evidence:* `docs/graph-design.md`, `graph/builder.py::multi_step_enabled`.

*Expect to be asked:* "So you built something you don't use?" — the honest answer
is that measuring it is what produced the decision, and shipping it on by default
would have been the mistake.

### 3. Temperature is pinned at 0 so evaluation means something

Both LLM providers send `temperature: 0`. The system is scored against a 15-item
gold set; a model that answers differently on identical input makes a score
unattributable — you cannot separate a retrieval regression from sampling noise.
It costs phrasing variety and buys evaluations you can act on.

*Evidence:* `docs/eval-results.md` — runs marked *deterministic* returned
byte-identical text across rounds.

*Expect to be asked:* "Doesn't that make answers robotic?" — for a legal
assistant, reproducibility is worth more than fluency. The same question must
give the same answer to two lawyers.

## If it breaks

**A question returns "no answer" for everything.** VPN or gateway. Run the curl
in step 1. This is the most likely failure and the fastest to diagnose.

**An upload never becomes searchable.** Check the worker: `docker compose logs
worker --tail 20`. Both `app` and `worker` share the `document_storage` volume,
so a file-not-found here means the volume is missing, not the code.

**The data looks wrong, or you deleted something mid-demo.**

```bash
cd backend && uv run python scripts/seed_demo.py --reset
```

22 seconds and you are back to a known state. This works even if someone uploaded
a document during the demo.

**The whole stack is confused.**

```bash
docker compose down && docker compose up -d
```

Never add `--remove-orphans`. Until the running Langfuse containers are recreated
under their new project name, they still carry the `legalmind` project label and
that flag would delete them.

## Known rough edges

Say these before someone finds them.

- A citation shows the filename and page, but is not clickable — there is no
  document-view route yet. It was a link to a 404 until recently; a dead link is
  worse than an honest label.
- The demo runs on seeded data with real embeddings, but nobody has run this
  against a *clean clone* end to end, and a clean clone needs two credentials
  pasted in before it can ingest anything.
- CI does not build the Docker images yet, so a broken Dockerfile would surface
  here first.
