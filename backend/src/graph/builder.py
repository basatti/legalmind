"""Wires the nodes into a runnable graph (LEG-74, LEG-76, LEG-78, LEG-80).

Graph shape:

    START     -> route
    route     -> retrieve                  (both routes, always)
    retrieve  -> reason     (multi-step)
    retrieve  -> answer     (single-shot)
    reason    -> retrieve   (another pass wanted)
    reason    -> answer     (done, or the iteration cap was hit)
    answer    -> cite       -> END

Every run retrieves once on the original question before anything else looks
at it. Two reasons. `reason`'s prompt asks whether *what has been retrieved so
far* is enough, which has no meaning on an empty set — so reasoning first
would be judging blind, and a stray DONE on that first pass would answer from
no passages at all. And routing is a guess: when it wrongly calls a simple
question multi-step, retrieving the original wording first means the mistake
costs one extra model call rather than replacing a good query with a
generated sub-question.

The retrieve <-> reason cycle is the loop LEG-78's MAX_ITERATIONS caps, and
that cap is the only thing ending it — `_after_reason` reads the flag the
reason node sets and counts nothing itself. A single-shot run never enters the
cycle: `retrieve` branches on the route, so one value decides a run's shape
and there is no second flag to disagree with it.

The whole retrieve <-> reason half of that shape is behind
RAG_MULTI_STEP_ENABLED, off by default — see `multi_step_enabled` below for
the measurement that put it there. With the loop off the router never picks
`reason`, so every run is route -> retrieve -> answer -> cite and the routing
model call is skipped entirely.

LEG-80 wires the graph execution path from RagService.ask().
"""

import os
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import (
    cite,
    make_answer_node,
    make_reason_node,
    make_retrieve_node,
    make_route_node,
)
from graph.state import GraphState, Route
from services.answer_service import AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService

RagGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]

MULTI_STEP_ENV_VAR = "RAG_MULTI_STEP_ENABLED"
_TRUTHY = {"1", "true", "yes", "on"}


def multi_step_enabled() -> bool:
    """Whether the reason loop may run at all (LEG-80's rollback switch).

    Off unless explicitly enabled, which is the opposite of the usual "ship it
    on" default and deliberate. Measured against the corpus, a genuinely
    compound question routed multi-step produced *no* answer where the
    single-shot path answered it correctly: the reason node's sub-questions
    restated rather than decomposed, and the extra passages they retrieved
    diluted the good ones until the model reported the answer was not there.
    Retrieval quality is not additive — more context made it worse.

    So the loop stays behind a switch until LEG-78's reasoning prompt produces
    sub-questions that narrow the search instead of widening it. Turning it on
    is one env var, which is what the ticket asked for; leaving it off costs a
    class of question we already answer correctly today.

    Anything other than 1/true/yes/on is off, including an unset variable and
    any typo — a rollback switch that fails open is not a rollback switch.
    """
    return os.environ.get(MULTI_STEP_ENV_VAR, "").strip().lower() in _TRUTHY


def _after_reason(state: GraphState) -> str:
    """Another retrieval pass, or enough found to attempt an answer.

    Reads `should_continue`, which the reason node rewrites on every pass from
    its own iteration count — so the cap in `MAX_ITERATIONS` is what actually
    ends this loop. Nothing here counts; a guard in two places is a guard that
    can disagree with itself.
    """
    return "retrieve" if state.should_continue else "answer"


def _after_retrieve(state: GraphState) -> str:
    """Back to reason on a multi-step run, straight to answer otherwise.

    Branches on the route rather than on `should_continue`: a single-shot run
    must never enter `reason`, and after a single-shot retrieval
    `should_continue` is still its default False — indistinguishable from a
    multi-step run that has decided to stop. The route is the one value that
    already separates the two.
    """
    return "reason" if state.route == Route.MULTI_STEP else "answer"


def build_graph(
    llm: LLMProvider,
    retrieval_service: RetrievalService | None = None,
    answer_service: AnswerService | None = None,
    multi_step: bool | None = None,
) -> RagGraph:
    """Compile the RAG graph.

    Dependencies are injected so tests can provide fake services.

    retrieval_service and answer_service are optional for backwards
    compatibility with graph skeleton tests that only validate routing and
    graph shape. The real application path (RagService.ask) always injects
    both services.

    multi_step defaults to reading the environment, so the switch is a
    deployment concern rather than a call-site one; tests pass it explicitly
    to pin a shape without touching os.environ. The reason node stays in the
    graph either way — with the loop disabled the router simply never sends
    anything to it, which keeps one graph shape to reason about instead of
    two.
    """
    if multi_step is None:
        multi_step = multi_step_enabled()

    builder = StateGraph(GraphState)

    builder.add_node("route", make_route_node(llm, multi_step))

    if retrieval_service is not None:
        builder.add_node(
            "retrieve",
            make_retrieve_node(retrieval_service),
        )
    else:
        builder.add_node(
            "retrieve",
            lambda state: {},
        )

    builder.add_node(
        "reason",
        make_reason_node(llm),
    )

    if answer_service is not None:
        builder.add_node(
            "answer",
            make_answer_node(answer_service),
        )
    else:
        builder.add_node(
            "answer",
            lambda state: {},
        )

    builder.add_node("cite", cite)

    builder.add_edge(START, "route")

    # Not a branch: both routes retrieve first. The route is read later, by
    # _after_retrieve, to decide whether this run reasons at all.
    builder.add_edge("route", "retrieve")

    builder.add_conditional_edges(
        "reason",
        _after_reason,
        {"retrieve": "retrieve", "answer": "answer"},
    )

    builder.add_conditional_edges(
        "retrieve",
        _after_retrieve,
        {"reason": "reason", "answer": "answer"},
    )

    builder.add_edge("answer", "cite")
    builder.add_edge("cite", END)

    return builder.compile()
