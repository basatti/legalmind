# RAG Graph Design

This document mirrors LEG-66's doc for the RAG query graph (`src/graph/`):
why each node exists, how routing decides single-shot vs. multi-step, and how
authorization scope survives every hop. It reflects the graph as wired today
(LEG-74, LEG-76, LEG-77, LEG-78, LEG-79, LEG-80, LEG-81), including the
`RAG_MULTI_STEP_ENABLED` rollback switch added after LEG-80.

## Graph shape

START -> route -> retrieve -> (reason ↔ retrieve)* -> answer -> cite -> END

Every run retrieves once on the original question before anything else looks
at it, both routes hit retrieve first via a fixed edge. Only after that
first retrieval does _after_retrieve check state.route and send
multi-step runs into reason. Single-shot runs go straight to answer.

From inside reason, _after_reason reads should_continue: True ↔s
back to retrieve for another pass, False falls through to answer. The
↔ is capped by MAX_ITERATIONS = 3 in the reason node itself, the
conditional edge does no counting of its own, it just reads the flag reason
set.

## Why each node exists

route - classifies the question as SINGLE_SHOT or MULTI_STEP by
asking the LLM (routing_prompt.py). When multi_step is False (the
current default), it skips the model call entirely and always returns
SINGLE_SHOT, there's nothing to classify if only one destination is
reachable.

retrieve - fetches passages for the current query, scoped to
state.authorized. Uses the latest sub-question from state.reasoning if
reason has already run, otherwise the original question. Matches
accumulate across passes (a multi-step run can call this more than once)
rather than being replaced.

reason - only reached on multi-step runs. Decides, from what's been
retrieved so far, whether to keep going (CONTINUE, appending a
sub-question to state.reasoning) or stop (DONE). Enforces
MAX_ITERATIONS so this can never ↔ forever.

answer - terminal generation node. Dedupes passages across all
retrieval passes (unique_passages) so a chunk retrieved twice isn't sent to
the model twice under two different numbers, then answers the original
question (never the last sub-question) against those passages.

cite - copies state.answer.citations into state.citations. Kept as
a separate node/state field rather than reading answer.citations directly
downstream, so the graph's output shape doesn't depend on Answer's
internals.

## Routing: single-shot vs. multi-step

In production today, routing is effectively always single-shot. The
reason/retrieve ↔ is gated behind the RAG_MULTI_STEP_ENABLED environment
variable (graph/builder.py::multi_step_enabled), which defaults to off, and
nothing currently turns it on. Every real run is route -> retrieve -> answer
-> cite; the multi-step path below describes wiring that exists in code but
does not execute in production.

This isn't a stub, it's a deliberate rollback after measurement: once the
loop was wired end to end, a genuinely compound question generated two
near-identical sub-questions that pulled in unrelated passages, and the
model returned NOT_FOUND, where the same question answered correctly from
the passages a single retrieval pass found. More context made it worse. (Not
a gold-set score, this is not stable enough yet to quote a number from, LEG-87.)

With the flag off:
- route never calls the model and always returns SINGLE_SHOT.
- Every run is route -> retrieve -> answer -> cite.
- The reason node and the retrieve/reason ↔ stay wired in the graph
  (so there's one graph shape to reason about, not two) but are unreachable.

Turning the ↔ on is one env var (RAG_MULTI_STEP_ENABLED=true). The loop
itself and its MAX_ITERATIONS cap are correctly wired (there's a test that
hangs without the cap); what's left is reasoning_prompt.py: sub-questions
need to narrow the search rather than restate the question. That's LEG-78's
remaining work, and what turning the flag on depends on.

## How scope survives every hop

state.authorized (an AuthorizedCases) is resolved exactly once, by
RagService.ask(), before the graph is invoked. It is:

- passed into GraphState at construction,
- read by retrieve on every pass (retrieval_service.retrieve(query, within=state.authorized)),
- never recomputed, reinterpreted, or narrowed by any node.

No node, route, reason, answer, or cite, touches authorization at
all. This is intentional: LEG-66's invariant is that authorization is
decided in exactly one place. A node that resolved scope for itself would be
a second place where that decision could be made, and could disagree with
the first.

Covered by tests in backend/tests/test_graph_authorization.py (LEG-81).

## Other state worth knowing

- matches accumulates across retrieval passes rather than being replaced.
- reasoning holds reason's sub-questions, kept for traceability
  (Langfuse tracing, LEG-83) rather than because answer depends on it.
- iterations / should_continue are read once, right after reason runs,
  by _after_reason, never by reason itself on a later call. Each pass
  decides fresh from state.iterations, not from what it decided last time.
  