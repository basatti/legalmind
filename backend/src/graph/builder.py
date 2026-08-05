"""Wires the nodes into a runnable graph (LEG-74, LEG-76, LEG-80).

Graph shape:
route -> retrieve -> reason -> answer -> cite

LEG-80 wires the graph execution path from RagService.ask().
"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import (
    cite,
    make_answer_node,
    make_reason_node,
    make_route_node,
    make_retrieve_node,
)
from graph.state import GraphState, Route
from services.answer_service import AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService


RagGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]


def _after_route(state: GraphState) -> Route:
    """Decide where the graph goes after routing."""
    return state.route or Route.SINGLE_SHOT


def build_graph(
    llm: LLMProvider,
    retrieval_service: RetrievalService | None = None,
    answer_service: AnswerService | None = None,
) -> RagGraph:
    """Compile the RAG graph.

    Dependencies are injected so tests can provide fake services.

    retrieval_service and answer_service are optional for backwards
    compatibility with graph skeleton tests that only validate routing and
    graph shape. The real application path (RagService.ask) always injects
    both services.
    """

    builder = StateGraph(GraphState)

    builder.add_node("route", make_route_node(llm))

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

    builder.add_conditional_edges(
        "route",
        _after_route,
        {
            Route.SINGLE_SHOT: "retrieve",
            Route.MULTI_STEP: "reason",
        },
    )

    builder.add_edge("reason", "retrieve")
    builder.add_edge("retrieve", "answer")
    builder.add_edge("answer", "cite")
    builder.add_edge("cite", END)

    return builder.compile()
