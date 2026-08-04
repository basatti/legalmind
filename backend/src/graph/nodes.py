"""The graph's five nodes (LEG-74, LEG-76).

`route` is implemented. `retrieve`, `reason`, `answer` and `cite` are still
placeholders with their real signatures already fixed, so LEG-77 to LEG-79 can
be picked up in parallel: filling one in means editing one function here, not
agreeing a new interface first.

Every node returns a *partial* update — only the fields it changed — which
LangGraph merges into the state. Returning `{}` means "changed nothing", which
is what a stub does.

A run therefore still ends with `answer` as None, whichever way the router
sends it. That is deliberate: `RagService` already treats a None answer as "no
answer", so a partly-built graph refuses to answer rather than assembling one
out of whichever nodes happen to be finished. Nothing here can fail open.
"""

import logging
from typing import Any, Protocol

from graph.routing_prompt import MULTI_STEP, SINGLE_SHOT, build_routing_prompt
from graph.state import GraphState, Route
from services.llm import LLMProvider

logger = logging.getLogger(__name__)

StateUpdate = dict[str, Any]
"""A node's partial write-back. Untyped values because LangGraph merges by key
name; the keys must match `GraphState`'s field names."""


class Node(Protocol):
    """What LangGraph runs: state in, partial update out.

    A Protocol rather than `Callable[[GraphState], StateUpdate]` because
    LangGraph's own node type names the parameter — `def __call__(self, state:
    ...)`. A Callable alias makes that parameter positional-only, so a factory
    annotated with one is rejected by `add_node` even though the function it
    returns is perfectly valid.

    A node that needs collaborators — a model, a repository — is built by a
    factory that takes them and returns one of these, rather than reaching for
    them itself. Same reason RagService takes its collaborators in `__init__`:
    a test supplies fakes, and nothing in here decides which provider is real.
    """

    def __call__(self, state: GraphState) -> StateUpdate: ...


def make_route_node(llm: LLMProvider) -> Node:
    """Build the node that decides whether a question needs one pass or several."""

    def route(state: GraphState) -> StateUpdate:
        """Classify the question and record the decision on the state.

        An unrecognised reply is not an error. It falls back to single-shot,
        which is exactly what the system does today for every question — so a
        model that misbehaves costs the improvement, never the existing
        behaviour. Failing the request instead would mean a question that works
        in production today starts returning 503 the moment routing ships.

        `LLMError` is deliberately not caught: the model being unreachable is a
        real outage, and the answer node would fail on the next call anyway.
        `query_router` already turns it into a 503 with a message that names
        neither host nor model.
        """
        reply = llm.generate(build_routing_prompt(state.question)).strip().upper()

        if reply == MULTI_STEP:
            return {"route": Route.MULTI_STEP}

        if reply != SINGLE_SHOT:
            # Worth a log line rather than silence: a model that has stopped
            # answering in the agreed tokens sends every question down the
            # single-shot path, which looks like the router doing nothing.
            logger.warning("router replied %r, expected one of the two tokens", reply)

        return {"route": Route.SINGLE_SHOT}

    return route


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
