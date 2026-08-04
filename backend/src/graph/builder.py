"""Wires the nodes into a runnable graph (LEG-74).

The shape the epic asks for: route -> retrieve -> reason -> answer -> cite.

The edges here are all unconditional, which is not the end state. LEG-76's
router is what makes the graph a graph rather than a pipeline: it replaces the
route -> retrieve edge with a conditional one, so a single-shot question can
skip the reason node entirely. Building that branch now, with every node still
a stub, would mean writing a routing rule with nothing to route.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes import answer, cite, reason, retrieve, route
from graph.state import GraphState

RagGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]
"""The compiled graph's full type: state, context, input and output schemas.

Context is `Any` because no context schema is declared — LangGraph's runtime
context (per-run config a node can read) is not needed while every node works
only from the state it is handed.
"""


def build_graph() -> RagGraph:
    """Compile the RAG graph.

    Compiling is pure — no database, no model, no credentials — so this is safe
    to call at import time or in a test. The nodes reach for those things when
    they run, not when the graph is built.
    """
    builder = StateGraph(GraphState)

    builder.add_node("route", route)
    builder.add_node("retrieve", retrieve)
    builder.add_node("reason", reason)
    builder.add_node("answer", answer)
    builder.add_node("cite", cite)

    builder.add_edge(START, "route")
    builder.add_edge("route", "retrieve")
    builder.add_edge("retrieve", "reason")
    builder.add_edge("reason", "answer")
    builder.add_edge("answer", "cite")
    builder.add_edge("cite", END)

    return builder.compile()
