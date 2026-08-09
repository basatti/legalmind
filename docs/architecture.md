# Architecture — the decisions worth knowing (LEG-97)

A short map of how LegalMind is put together and why the load-bearing choices
were made that way. Where a decision already has a document of its own, this
points at it rather than repeating it.

## Shape

```
Next.js (frontend/)
      │  session cookie
      ▼
FastAPI (backend/src/routers/)
      │
      ├── services/       auth, cases, documents, review
      │
      └── RagService.ask()          ← authorization resolved here, once
              │
              └── graph/            route → retrieve → answer → cite
                      │
                      ├── RetrievalService → DocumentChunkRepository (pgvector)
                      └── AnswerService    → LLMProvider

Uploads → IngestionJob queue → worker_main.py → parse → chunk → embed → store
```

Two processes run from the same image: the API (`backend/src/main.py`) and the
ingestion worker (`backend/src/worker_main.py`). Postgres with pgvector holds
both the relational data and the embeddings.

## Auth and authorization

These are two separate mechanisms and the distinction matters.

**Authentication** is server-side sessions, not JWTs. `AuthService.login()`
verifies the password and writes a `Session` row with a 24-hour TTL; the client
holds only an opaque session id. The reason is revocation: a stolen JWT stays
valid until it expires because nothing server-side tracks it, whereas a session
row can be deleted. For a system holding a law firm's case documents, being able
to end a session immediately is worth the database lookup on each request. There
is no public registration — admins create users (`create_user`), and a new user
carries `must_change_password`.

**Authorization** has two layers.

*What a role may do* is a static matrix in `foundation/permissions.py`: role →
frozenset of permissions, checked by set membership. Four roles (admin, partner,
attorney, paralegal) and eleven permissions, written out explicitly per role with
no inheritance chain to resolve — a check is a dict lookup and a set membership
test, and reading the matrix tells you the whole answer.

*Which cases a user may draw answers from* is the decision the DoD asks to see
called out, and it is the one architectural rule the rest of the system is bent
around:

> Authorization is resolved exactly once, at the front door, and travels
> downward as a value. Nothing below re-derives it.

`RagService.ask()` calls `CaseReader.authorized_cases(user)` and gets back an
`AuthorizedCases` — either `AllCases` (partners and admins, who hold
`case:read:any`) or `TheseCases(frozenset)` (everyone else, scoped to their
Assignment rows). That value is put into `GraphState` and read by the retrieve
node on every pass. No node recomputes it, narrows it, or looks at the user at
all.

Two things make this hold rather than merely being a convention:

- **The two cases are different types.** "May see everything" and "assigned to
  nothing" were both an empty list before `AuthorizedCases` existed, which meant
  a missed branch turned a permission failure into unrestricted access.
  `AllCases` and `TheseCases(frozenset())` cannot be confused, and the empty set
  is a legitimate value with exactly one meaning.
- **The filter is inside the SQL query**, before ranking — `WHERE case_id IN
  (...)` then `ORDER BY ... LIMIT k`, never rank-then-discard. There is no code
  path that can produce a chunk outside the authorized set, so there is nothing
  to forget to call. `ChunkSearcher.search()` takes the scope as an argument for
  the same reason: an implementation is given no opportunity to search first and
  filter afterwards.

Full reasoning, including why search-then-filter is a vulnerability class rather
than a style preference: [`retrieval-authorization.md`](retrieval-authorization.md).
How the scope survives each hop of the graph:
[`graph-design.md`](graph-design.md#how-scope-survives-every-hop).

## The other decisions

**Postgres with pgvector, not a dedicated vector database.** Cases, assignments,
documents and embeddings live in one database, so a retrieval query can join
authorization data and vectors in a single statement. That is what makes
filtering-before-ranking possible at all; with a separate vector store the scope
would have to be applied in application code, on the far side of the ranking.
Search is a brute-force scan today — exact, and fast enough at this corpus size.
Adding an HNSW or IVF index later is a migration, not a change to the query's
shape.

**The answer service refuses rather than guesses.** A reply is discarded whole if
it cites a passage it was not given, cites nothing, or reports NOT_FOUND. All
three return the same empty answer. A lawyer has no use for the distinction, and
collapsing them means a wrong answer never gets dressed up as a real one. The
difference is recorded in the logs, where it belongs.

**The RAG flow is a graph, and its multi-step loop is off by default.** The
retrieve/reason loop is wired, tested and capped — and disabled behind
`RAG_MULTI_STEP_ENABLED`, because when it was measured it made answers worse: a
compound question produced near-identical sub-questions, pulled in unrelated
passages, and the model returned NOT_FOUND where a single pass had answered
correctly. Keeping the code wired but unreachable means one graph shape to reason
about rather than two, and turning it back on is one environment variable once
the sub-question prompt earns it. See [`graph-design.md`](graph-design.md).

**Temperature is pinned at 0.** Both LLM providers send `temperature: 0`. The
system is measured against a gold set, and a model that answers differently on
identical input makes a score unattributable — you cannot tell a retrieval
regression from sampling noise. It costs some phrasing variety and buys
evaluations that mean something. See [`eval-results.md`](eval-results.md).

**Ingestion is a queue, not part of the upload request.** An upload writes an
`IngestionJob` row and returns; the worker claims jobs, parses, chunks, embeds
and stores, with bounded retries and a staleness timeout for jobs whose worker
died. Producer and consumer never wait on each other, so a slow PDF cannot hold
a request open, and the worker can run on another machine.

**Dependencies are narrow protocols.** `CaseReader`, `ChunkSearcher`,
`LLMProvider`, `EmbeddingProvider` each expose only what their consumer needs —
`ChunkSearcher` reads and searches, and deliberately does not offer the write
methods the same repository has. Tests inject fakes; production injects the real
thing; and an interface that does not expose a capability cannot have it misused.

**Models run on company infrastructure**, reached through a LiteLLM gateway over
Tailscale — `bge-m3` for embeddings (1024-dim, L2-normalized at embedding time)
and `gpt-oss` for generation. No document text leaves the network. The practical
consequence is that nothing works off the VPN, which is the first thing to check
when the app appears broken.

**Every question is one trace.** The span opened in `RagService.ask()` is the
parent of every model call the graph makes, so a run reads as a single trace in
Langfuse instead of a scattering of unrelated calls. See
[`observability.md`](observability.md).

## Where to read more

| Document | Covers |
|---|---|
| [`retrieval-authorization.md`](retrieval-authorization.md) | Filtering inside the query, top-k, cosine vs. dot product, pgvector index tradeoffs |
| [`graph-design.md`](graph-design.md) | Graph shape, why each node exists, routing, how scope survives every hop |
| [`observability.md`](observability.md) | Langfuse tracing, reading a trace to debug a wrong answer |
| [`eval-results.md`](eval-results.md) | Recorded eval runs and how to read them |
| [`running-locally.md`](running-locally.md) | Setup, the three terminals, what to check when it does not work |
