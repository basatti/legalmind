"""The agentic RAG graph (LEG-16).

A LangGraph state machine — route -> retrieve -> reason -> answer -> cite —
replacing the single-shot path through `RagService`. Knows nothing about HTTP,
sessions or users: it receives an already-resolved authorisation scope on its
state and answers one question inside it.
"""

from graph.builder import RagGraph, build_graph
from graph.nodes import Node, StateUpdate
from graph.state import GraphState, Route

__all__ = [
    "GraphState",
    "Node",
    "RagGraph",
    "Route",
    "StateUpdate",
    "build_graph",
]
