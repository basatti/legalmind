"""The graph's five nodes, as stubs (LEG-74).

Each one is a placeholder with its real signature already fixed, so LEG-76 to
LEG-79 can be picked up in parallel: filling in a node means editing one
function here, not agreeing a new interface first.

Every node returns a *partial* update — only the fields it changed — which
LangGraph merges into the state. Returning `{}` means "changed nothing", which
is what a stub does.

A run of the graph as it stands therefore ends with `answer` still None. That
is deliberate: `RagService` already treats a None answer as "no answer", so a
half-built graph refuses to answer rather than inventing one. Nothing here can
fail open.
"""

from typing import Any

from graph.state import GraphState

StateUpdate = dict[str, Any]
"""A node's partial write-back. Untyped values because LangGraph merges by key
name; the keys must match `GraphState`'s field names."""


def route(state: GraphState) -> StateUpdate:
    """Decide whether this question needs one retrieval pass or several.

    LEG-76 fills this in and sets `route`. Until then every question falls
    through the linear path in `builder.py`, which is the single-shot
    behaviour the system already has.
    """
    return {}


def retrieve(state: GraphState) -> StateUpdate:
    """Fetch passages for the question, inside `state.authorized` only.

    LEG-77 fills this in by calling `RetrievalService.retrieve(within=...)`.
    It must pass `state.authorized` straight through: the scope arrives
    already resolved, and filtering happens inside the query, before ranking.
    """
    return {}


def reason(state: GraphState) -> StateUpdate:
    """Decompose a multi-step question and decide whether to retrieve again.

    LEG-78 fills this in, together with the loop guard that caps
    `state.iterations`. Hitting the cap must degrade to a clean "no answer",
    never an error — an exception here would tell a caller that a question was
    expensive to answer, which is a fact about the case they may not be
    entitled to.
    """
    return {}


def answer(state: GraphState) -> StateUpdate:
    """Turn the retrieved passages into a grounded answer.

    LEG-79 fills this in via `AnswerService`, which already discards a reply
    that cites a passage it wasn't given, cites nothing, or reports NOT_FOUND.
    That validation stays where it is — the node supplies passages and records
    the result, it does not re-judge the model's output.
    """
    return {}


def cite(state: GraphState) -> StateUpdate:
    """Produce the citations the answer is checked against.

    LEG-79 also decides whether this node has any work of its own to do:
    `AnswerService` already returns validated citations from the same call
    that produced the answer, so this is either a pass-through or the place
    that enriches citations with document filenames.
    """
    return {}
