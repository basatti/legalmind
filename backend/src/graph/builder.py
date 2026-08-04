"""Wires the nodes into a runnable graph (LEG-74, LEG-76).

The shape the epic asks for: route -> retrieve -> reason -> answer -> cite.

LEG-76 turned the first edge into a branch, which is what makes this a graph
rather than a pipeline. A single-shot question goes straight to retrieve. A
multi-step one reasons first — decomposing the question before any search runs,
so retrieval is given the sub-questions rather than the compound original.

The remaining edges are still unconditional. LEG-78 adds the loop that lets
reason send the run back for another retrieval pass, together with the cap that
stops it running forever; a cycle without that cap would keep calling the
company gateway until the request timed out.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import answer, cite, make_route_node, reason, retrieve
from graph.state import GraphState, Route
from services.llm import LLMProvider

RagGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]
"""The compiled graph's full type: state, context, input and output schemas.

Context is `Any` because no context schema is declared — LangGraph's runtime
context (per-run config a node can read) is not needed while every node is
built with what it needs and works only from the state it is handed.
"""


def _after_route(state: GraphState) -> Route:
    """Which way the run goes once the question has been classified.

    Falls back to single-shot when `route` is unset. The route node always sets
    it, so this is unreachable in practice — but the fallback is the cheap path
    and the one the system already takes today, so an unset value costs the
    improvement rather than raising inside the graph.
    """
    return state.route or Route.SINGLE_SHOT


def build_graph(llm: LLMProvider) -> RagGraph:
    """Compile the RAG graph.

    Takes the model rather than reaching for one, so a test compiles the same
    graph against a fake. Compiling is otherwise pure — no database, no
    network, no credentials — and the model is not called until a run reaches
    the route node.
    """
    builder = StateGraph(GraphState)

    builder.add_node("route", make_route_node(llm))
    builder.add_node("retrieve", retrieve)
    builder.add_node("reason", reason)
    builder.add_node("answer", answer)
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
