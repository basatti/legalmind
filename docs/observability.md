# Tracing with Langfuse

Every call to the company LLM and embedding API is recorded: the prompt, the
reply, the token counts and the latency. This is what turns "the answer was
wrong" into "the answer was wrong *here*" (LEG-83).

Tracing is **off unless you configure it**. None of this is needed to run the
app, and CI runs with it off — see [Tracing is optional](#tracing-is-optional).

---

## The vocabulary

Three words, used throughout the UI:

- **Observation** — one recorded unit of work. Has an input, an output, a start
  and end time.
- **Trace** — the top-level container. One question produces one trace, with
  every model call it made nested inside it (LEG-84).
- **Span / generation / embedding** — the *kind* of observation. Langfuse
  renders them differently: a generation and an embedding get a model name and
  token counts, a plain span does not, because a span is not a model call.

We name them in `observability/tracer.py` as `Kind.SPAN`, `Kind.GENERATION` and
`Kind.EMBEDDING`, so nothing outside that package imports Langfuse's own
literals.

---

## Quick start

**1. Start Langfuse** (Docker Desktop must be running — this part is six
containers):

```bash
docker compose -f docker-compose.langfuse.yml up -d
```

First run pulls six images and takes a few minutes.

**2. Get keys.** Ask on Slack for the shared ones. They are not in the repo and
never will be. To make your own instead: open <http://localhost:3001>, sign up,
create an organisation and a project, then **Settings → API Keys**. The secret
key is shown once — copy it before closing the dialog.

**3. Add three lines to `backend/.env`:**

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3001
```

**4. Restart the backend.** The tracer is built once per process (`lru_cache` on
`get_tracer`), so a server that was already running will not pick up new keys.
This is the mistake everyone makes first: nothing errors, you just get no traces.

**5. Check it:**

```bash
cd backend
uv run python scripts/smoke_test_tracing.py
```

Then open <http://localhost:3001> → **Tracing**.

Stop Langfuse when you are done — it is not light:

```bash
docker compose -f docker-compose.langfuse.yml down
```

Add `-v` only if you also want the recorded traces deleted.

---

## What the six containers are

| container | what it does |
|---|---|
| `langfuse-web` | the UI and the ingestion API |
| `langfuse-worker` | processes queued events into ClickHouse |
| `postgres` | its own metadata — users, projects, API keys |
| `clickhouse` | the trace data itself; a column store, because traces are written far more than read |
| `redis` | the queue between web and worker |
| `minio` | S3-compatible blob storage for large payloads |

This is why it lives in a **separate compose file** rather than being added to
`docker-compose.yml`. Six extra containers on every `docker compose up` would be
a heavy tax on people who are not debugging a trace today.

Expect a few GB of disk once traces accumulate. `down -v` reclaims it.

---

## Where things live

| what | address |
|---|---|
| Langfuse UI | <http://localhost:3001> |
| its own Postgres | `localhost:5433` |
| MinIO console | <http://localhost:9091> |

**Both of those ports are deliberately not the defaults.** Langfuse ships on
3000, which the frontend owns, and its Postgres on 5432, which the project
database owns. Left alone, one of them silently fails to start.

`docker-compose.langfuse.yml` is the upstream file with exactly three lines
changed — **22** (`NEXTAUTH_URL`), **79** (web port), **168** (Postgres port).
If you re-download it to pick up a new Langfuse version, those three edits have
to be reapplied.

---

## How it is wired

```
backend/src/observability/
├── tracer.py            Tracer interface, Kind, Observation, NullTracer
├── langfuse_tracer.py   the ONLY file that imports Langfuse
├── factory.py           build_tracer() — reads .env, picks one
└── __init__.py          public exports (LangfuseTracer is deliberately absent)
```

Two provider classes trace themselves:

- `services/company_llm.py` → `Kind.GENERATION`
- `embeddings/company_api.py` → `Kind.EMBEDDING`

and `services/rag_service.py` opens the `rag-run` span those calls nest inside
(LEG-84). `routers/query_router.py` hands all three the tracer when it builds
them.

### How the nesting works

`start_as_current_observation` does what its name says: the span it opens
becomes *the currently active span* for this thread, and anything opened after
it attaches as a child. Nothing is threaded through `RagService` → graph →
nodes → providers. The root is opened once in `ask()` and the provider spans
find their own parent.

The proof is visible in the UI: `rag-run` reports token counts even though
`ask()` never sets `record.usage`. Those totals can only be its children's,
rolled up.

### Three design decisions worth knowing

**The providers trace themselves rather than being wrapped.** A wrapper around
`generate()` would see a prompt and a reply and nothing else — the token counts
live in the `usage` block of the HTTP response, which the provider reads and
discards. Instrumentation goes where the data is.

**`NullTracer` instead of `if tracing_enabled:`.** Callers always receive a real
`Observation` to write to; when tracing is off, those writes go nowhere. There
is not a single tracing conditional anywhere in the codebase.

**Our own `Tracer` interface rather than Langfuse everywhere.** The SDK is a
moving target. When its overloads turned out to be fussier than expected during
LEG-83, the fix touched one function and nothing else in the project noticed.

---

## Tracing something new

Say you want to trace the retrieval step. Two changes:

**1. Accept a tracer, defaulting to one that records nothing:**

```python
from observability.tracer import Kind, NullTracer, Tracer

class RetrievalService:
    def __init__(self, ..., tracer: Tracer | None = None) -> None:
        self._tracer = tracer or NullTracer()
```

The default matters — every existing caller and test keeps working untouched.

**2. Wrap the work:**

```python
with self._tracer.observe("retrieval", kind=Kind.SPAN, input={"question": question}) as record:
    matches = ...
    record.output = {"matches": len(matches)}
    return matches
```

Then pass a real tracer where the object is constructed, in `query_router.py`.

### Two rules when you do this

**Record what is readable, not what is returned.** The embedding provider logs
`{"vectors": 1, "dimensions": 1024}` rather than the vectors. Nobody has ever
debugged anything by reading a thousand floats. Ask what question you would open
the trace to answer, and record that.

**Pass a dict as `input`, not a bare list.** Langfuse reads a list on a model
call as an array of chat messages and renders a column of `undefined` when it
cannot find `role` and `content`. `{"texts": texts}` renders cleanly.

---

## Debugging a wrong answer

This is what the whole thing is for. A lawyer reports a bad answer; open the
trace and work down this list.

**1. Open the `rag-run` trace and read its metadata.**
`scope` is how wide the search was allowed to be, `route` which shape the run
took, `passages` how many reached the model, `retrieval_passes` how many times
it went looking. If `scope` reads `0 case(s)`, stop here — this is a
permissions problem, and no model was ever called.

**2. If `answered` is false, read `why`.**
`no authorized cases` and `no grounded answer` are indistinguishable to the
lawyer — both return an empty answer, deliberately — but they are completely
different bugs. This field is the only place the two are told apart.

**3. Open the nested `company-llm` and read the Input.**
This is the full assembled prompt, including the numbered passages retrieved for
this question. It is the single most useful field in the system.

**4. Do the passages actually contain the answer?**

- **No** → this is a *retrieval* problem, not a model problem. The right
  document was never handed over. Check chunking, embeddings, or whether the
  document was ingested at all. Changing the prompt will not help.
- **Yes** → this is a *generation* problem. The model had what it needed and
  still got it wrong. Now the prompt, the model, or the language is in question.

**5. Is the Output exactly `NOT_FOUND`?**
The model is reporting that the answer is not in the passages — see
`services/prompt.py`. If step 4 says it *is* in there, that is a real model
failure worth recording; Arabic quality is model-dependent, and this is exactly
the kind of case LEG-85's gold set exists to catch.

**6. Check the token counts.**
An unusually large input may have been truncated by the model's context window,
in which case the passages you can see in the trace are not all the passages the
model actually read.

**7. Check the latency.**
A slow generation with a normal-sized prompt points at the gateway, not at us.

If `RAG_MULTI_STEP_ENABLED` is on, expect several retrieval passes per question,
and read them in order — the later ones search on sub-questions, not the
original.

---

## A worked example: the answer that cites correctly and is still wrong (LEG-88)

The checklist above is the procedure. This is it applied to a real failure, with
the real numbers, so you know what each step looks like before you need it.

The case is deliberately not a dramatic one. Nothing crashed, nothing was
hallucinated, no citation was invented, and the answer is a true statement about
Saudi labour law. Read only the answer and you would approve it. That is exactly
why it is the case worth learning on — the obvious failures announce themselves,
and this one does not.

### The complaint

Gold-set item `end-of-service-award-first-five-years`, from run
`20260808-114513-graph`. The question, in Arabic:

> استقلت بعد ثلاث سنوات، كيف تُحسب مكافأة نهاية الخدمة عن هذه السنوات؟
>
> *"I resigned after three years — how is the end-of-service award calculated
> for those years?"*

The eval marked it `answer_hit: 0`. A lawyer reporting this would say only that
the answer "doesn't answer the question".

### Step 1 — open the trace and read the metadata

Trace `b5e6f0a0290d809a50ace6ddd8c33487`. Three spans:

| span | nested under | tokens | ms |
|---|---|---|---|
| `eval-item[graph]` | — (root) | — | 12,489 |
| `company-embeddings` | root | 23 in | 3,902 |
| `company-llm` | root | 729 in / 713 out | 8,529 |

**An eval trace is not shaped like a production trace, and this trips people
up.** The checklist above describes a `rag-run` root span carrying `scope`,
`route`, `passages` and `retrieval_passes`. There is no `rag-run` span here:
`ragas_eval.py` calls `build_graph()` directly rather than going through
`RagService.ask()`, so the root is `eval-item[graph]` and it carries different
fields — `input.question`, metadata `{gold_item, lang, mode, round}`, and an
output of `{context_hit, answer_hit, answered}`.

So on an eval trace, step 1 gives you the scores instead of the routing. Here
they read `answered: 1`, `context_hit: 1`, `answer_hit: 0`. If you need `route`
or `retrieval_passes` for a gold-set item, they are in the run's JSON report
under `evals/results/`, not in Langfuse — this one was `single_shot` with
`iterations: 0`.

To see the production shape instead, ask through `/query/ask` and open the
`rag-run` trace, or run `scripts/smoke_test_tracing.py`, which produces one.

### Step 2 — `answered` is true, so there is no `why` to read

The model produced an answer rather than declining. Skip to the passages.

### Steps 3 and 4 — read the Input, and ask whether the answer is in there

Open the nested `company-llm` and read the Input. Five passages were retrieved:

| | article | what it says |
|---|---|---|
| `[1]` | المادة الخامسة والثمانون (85) | resignation *reduces* the award — one third for 2–5 years' service |
| `[2]` | المادة الرابعة والثمانون (84) | the accrual *rate* — half a month's wage for each of the first five years, a full month's wage thereafter |
| `[3]` | المادة السابعة والثمانون (87) | — |
| `[4]` | المادة السابعة والسبعون (77) | — |
| `[5]` | المادة السادسة والثمانون (86) | — |

**This is the fork in step 4, and it goes the way people do not expect.** The
answer *is* in the passages. Article 84 at `[2]` is the rate the question asks
for, and `context_hit: 1` records that retrieval did its job. So this is not a
retrieval problem. Chunking, embeddings and ingestion are all fine, and changing
any of them would fix nothing.

### Step 5 — the Output is not `NOT_FOUND`

The model answered:

> إذا كان انتهاء علاقة العمل بسبب استقالة العامل، فإنه يستحق ثلث المكافأة إذا
> كانت مدة خدمته لا تقل عن سنتين متتاليتين ولا تزيد على خمس سنوات **[1]**.
>
> *"If the employment relationship ends because of the worker's resignation, they
> are entitled to one third of the award if their service is no less than two
> consecutive years and no more than five years [1]."*

Every part of that is true, and `[1]` genuinely says it. The citation is honest:
the model cited a passage it was given, and the claim matches the passage. The
citation discipline the prompt enforces held perfectly.

What the answer never states is the **rate** — half a month's wage per year —
which is the thing "how is it calculated" asks for. The model answered from `[1]`
and stopped, never combining it with `[2]`.

### Steps 6 and 7 — tokens and latency are unremarkable

729 input tokens is nowhere near a context limit, so nothing was truncated: the
model saw all five passages. 8.5 s for the generation is normal for this
gateway. Neither step explains anything here, which is itself informative — it
rules out the two infrastructure explanations and leaves only the real one.

### The diagnosis

This question needs **two articles composed**: the rate from Article 84,
*reduced* by the resignation fraction from Article 85. Three years falls inside
Article 84's first five years, so the rate is half a month's wage per year; and
three years falls in Article 85's two-to-five band, so resignation earns one
third of it. Neither article answers the question alone.

The model produced one half of that and presented it as complete. The failure is
not retrieval, not hallucination, and not citation — it is **composition**, and
it is invisible to anyone who does not check the answer against the question.

The gold set anticipated exactly this split. From the item's own `notes`:

> this article gives the rate only — the separate reduction for resignation lives
> in المادة الخامسة والثمانون

### What to do about it

Look at `INSTRUCTIONS` in `services/prompt.py` and notice what is absent. The
rules say to use only the passages, to cite what is used, and to keep the answer
under four sentences. **Nothing asks the model to combine passages when a
question spans more than one.** The model followed every rule it was given.

That makes this a design finding rather than a bug report. Two candidate
directions, both testable against the gold set:

- **The reason node (LEG-78)**, whose stated job is to decompose multi-step
  questions and *synthesize across retrieved sets* — exactly the capability
  missing here. This item is a ready-made regression case for it: it needs two
  sub-questions ("what is the rate?" and "what does resignation change?") whose
  answers must then be combined. It is gated behind `RAG_MULTI_STEP_ENABLED`,
  which is off by default, and the run above was `single_shot`.
- **The instruction sheet**, which never asks for synthesis at all. A rule about
  answering from every passage the question needs is a much smaller change than
  a graph node, and worth measuring before reaching for the larger one.

Whichever is tried, re-run `ragas_eval.py` before and after. `INSTRUCTIONS` is
shared by every question in the system, and a fix aimed at this one can easily
cost accuracy on the fourteen that currently pass — which is the entire reason
LEG-87 tracks results over time.

### What this case teaches

- **`context_hit: 1` with `answer_hit: 0` is the signature of a generation
  problem.** Both scores are on the trace. Read them together — either alone
  tells you the wrong thing.
- **A correct citation is not a correct answer.** `[1]` was cited accurately and
  the answer was still wrong. Citation checking cannot catch this class of
  failure; only comparing the answer to the question can.
- **The most dangerous wrong answers are the plausible ones.** This is what the
  gold set is for, and why `answer_hit` is a substring check against a required
  phrase rather than a judgement of whether the answer "looks right".

---

## What is not traced

- **The ingestion worker.** `worker_main.py` builds its own provider and gets
  the default `NullTracer`. Ingestion embeds hundreds of chunks per document,
  which would flood the trace list for little debugging value. One line to
  change if that stops being true.
- **Retrieval, routing, and the individual graph nodes.** Only the two external
  API calls have spans of their own. `rag-run` reports the graph's *outcome* —
  route, passes, passage count — but the nodes themselves are not observed.
  Adding them follows the recipe above.

---

## Tracing is optional

With the two keys blank, `build_tracer()` returns a `NullTracer`. The app calls
it everywhere exactly as before and the writes go nowhere. No credentials are
needed to run the app, the tests, or CI.

A `NullTracer` in the smoke-test output is **correct behaviour, not a fault.**
It means there is nothing to look at, not that something broke.

---

## Never send this to Langfuse Cloud

Traces carry verbatim text from real case documents — the same content the
company-hosted gateway exists to keep off third-party services.

Left unset, the Langfuse SDK defaults to `cloud.langfuse.com`. So that a
half-configured install cannot quietly become an export of client material, the
app **refuses to trace** when the two keys are set and `LANGFUSE_BASE_URL` is
not, and logs an error explaining why. Point it at an instance we control,
always.

Running Langfuse anywhere shared — a real host, a DNS entry, a firewall rule —
is an infrastructure request, not a code change. Raise it with Bassel rather
than provisioning something yourself.

---

## A note on "cost"

LEG-17's acceptance criteria mention tracing cost. On a self-hosted gateway
there is no vendor price to read, so Langfuse's cost column stays at $0.00 and
that is correct, not broken.

What is real is **tokens and latency**. LEG-87 settled this: cost *is* those two
numbers here, and both are recorded per gold-set item by `scripts/ragas_eval.py`
and carried into `docs/eval-results.md`. Nobody should go looking for a money
figure that does not exist. If one is ever genuinely wanted, a rate has to be
configured deliberately in Langfuse — it cannot be derived from anything the
gateway reports.

---

## Scoring a run (LEG-87)

`Tracer.score(name, value)` attaches a judgement to observed work. It is
deliberately not a field on `Observation`: everything on that record is
something the work itself produced, and a score is somebody else's opinion of
it, formed afterwards.

It has two timings, because judgements arrive at two different moments:

```python
with tracer.observe("eval-item[graph]", kind=Kind.SPAN) as record:
    ...
    tracer.score("answer_hit", 1.0)          # on the span, decided on the spot

tracer.score("faithfulness", 0.83, trace_id=record.trace_id)   # long after
```

The second form exists for RAGAS, which grades a whole batch at once — by the
time it has an opinion, every span it is judging has closed. `record.trace_id`
is the one field the *tracer* writes and the caller reads, and it is only
readable while the span is open.

Under `NullTracer` both forms are no-ops and `trace_id` is None, so an untraced
eval run cannot silently look like a scored one.

---

## When something is wrong

**`localhost:3001` refuses to connect.** Still starting; `langfuse-web` runs
database migrations on first boot.

```bash
docker compose -f docker-compose.langfuse.yml logs langfuse-web --tail 20
```

**The smoke test prints `NullTracer`.** One of the three variables is missing
from `backend/.env`. If both keys are set, the missing one is
`LANGFUSE_BASE_URL` and the app is refusing on purpose — the backend log says so
explicitly.

**The app runs but no traces appear.** The backend was started before the keys
were added. Restart it.

**A script exits without its traces arriving.** The SDK sends from a background
thread and a short-lived process can exit first. Call `tracer.flush()` before
returning, as `scripts/smoke_test_tracing.py` does. Long-running processes such
as the API never need it.

**`Input` renders as a column of `undefined`.** Langfuse tried to read a list as
chat messages. Pass a dict.

**Port 3001 or 5433 already taken.** Change the host side in
`docker-compose.langfuse.yml` and update `LANGFUSE_BASE_URL` to match.

**Traces are eating disk.** ClickHouse and MinIO volumes grow.
`docker compose -f docker-compose.langfuse.yml down -v` clears them.

---

## Related

- **LEG-83** — spans on the LLM and embedding calls
- **LEG-84** — the `rag-run` span they nest inside
- **LEG-85** — the Arabic-first gold set, in `backend/evals/`
- **LEG-86** — the eval harness, `backend/scripts/ragas_eval.py`
- **LEG-87** — quality over time: `docs/eval-results.md`, generated from
  `backend/evals/history.jsonl` by `backend/scripts/eval_report.py`
- **LEG-88** — a written walkthrough of debugging one real bad answer
