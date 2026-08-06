"""The graph's five nodes (LEG-74, LEG-76, LEG-77, LEG-79).

`route`, `retrieve`, `reason`, `answer` and `cite` are implemented nodes.

Every node returns a *partial* update — only the fields it changed —
which LangGraph merges into the state.
"""

import logging
from typing import Any, Protocol

from graph.reasoning_prompt import CONTINUE, DONE, build_reasoning_prompt
from graph.routing_prompt import MULTI_STEP, SINGLE_SHOT, build_routing_prompt
from graph.state import GraphState, Route
from services.answer_service import AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService, unique_passages

logger = logging.getLogger(__name__)

StateUpdate = dict[str, Any]
"""A node's partial write-back. Untyped values because LangGraph merges by key
name; the keys must match `GraphState`'s field names."""


class Node(Protocol):
    """What LangGraph runs: state in, partial update out."""

    def __call__(self, state: GraphState) -> StateUpdate: ...


def make_route_node(llm: LLMProvider) -> Node:
    """Build the node that decides whether a question needs one pass or several."""

    def route(state: GraphState) -> StateUpdate:
        """Classify the question and record the decision on the state."""

        reply = llm.generate(build_routing_prompt(state.question)).strip().upper()

        if reply == MULTI_STEP:
            return {"route": Route.MULTI_STEP}

        if reply != SINGLE_SHOT:
            logger.warning(
                "router replied %r, expected one of the two tokens",
                reply,
            )

        return {"route": Route.SINGLE_SHOT}

    return route


def make_retrieve_node(retrieval_service: RetrievalService) -> Node:
    """Build the node that fetches passages for the question.

    Takes the service rather than reaching for one, for the same reason
    `make_route_node` takes the model: a test supplies a fake, and nothing in
    here decides which retrieval backend is real.
    """

    def retrieve(state: GraphState) -> StateUpdate:
        """Fetch passages for the current query, inside `state.authorized` only.

        Passes `state.authorized` straight through to
        `RetrievalService.retrieve(within=...)`: the scope arrived already
        resolved at the front door, and filtering happens inside the query,
        before ranking. Never recomputed here — see the module docstring on
        `GraphState`.

        The query is the latest sub-question when `reason` has already run —
        `reasoning` is empty on the single-shot path and on the first pass of
        a multi-step one, so `state.question` covers both until `reason`
        starts appending to it. This is what lets retrieval work from a
        sub-question rather than the compound original once LEG-78 fills
        `reason` in, without this node needing to know how that decomposition
        happened.

        Matches accumulate rather than replace: a multi-step question can
        loop back here more than once, and each pass adds to what earlier
        passes found rather than discarding it.
        """
        query = state.reasoning[-1] if state.reasoning else state.question

        matches = retrieval_service.retrieve(
            query,
            within=state.authorized,
        )

        return {
            "matches": [
                *state.matches,
                *matches,
            ],
        }

    return retrieve


MAX_ITERATIONS = 3
"""Hard cap on reason -> retrieve cycles."""


def make_reason_node(llm: LLMProvider) -> Node:
    """Build the node that decomposes a multi-step question."""

    def reason(state: GraphState) -> StateUpdate:

        iterations = state.iterations + 1

        if iterations > MAX_ITERATIONS:
            logger.warning(
                "reason node hit max iterations (%d), falling through to answer",
                MAX_ITERATIONS,
            )

            return {
                "iterations": iterations,
                "should_continue": False,
            }

        # The matched chunk itself, not its context_chunks — neighbours are
        # there to keep the *answer* readable, and folding them in here would
        # feed the same text to the model several times over as the passes
        # accumulate.
        summaries = [retrieved.match.text for retrieved in state.matches]

        prompt = build_reasoning_prompt(
            state.question,
            state.reasoning,
            summaries,
        )

        reply = llm.generate(prompt).strip()

        lines = reply.splitlines()
        decision = lines[0].strip().upper() if lines else ""

        if decision == CONTINUE:
            sub_question = lines[1].strip() if len(lines) > 1 else state.question

            return {
                "iterations": iterations,
                "reasoning": [
                    *state.reasoning,
                    sub_question,
                ],
                "should_continue": True,
            }

        if decision != DONE:
            logger.warning(
                "reason node replied %r, expected one of the two tokens",
                reply,
            )

        return {
            "iterations": iterations,
            "should_continue": False,
        }

    return reason


def make_answer_node(answer_service: AnswerService) -> Node:
    """Build the terminal answer node using AnswerService (LEG-79)."""

    def answer(state: GraphState) -> StateUpdate:
        # Deduped, not a plain flatten: a multi-step run retrieves several
        # times, and overlapping matches would otherwise send the same chunk
        # to the model twice under two different passage numbers.
        passages = unique_passages(state.matches)

        # The original question, never the last sub-question — the sub-questions
        # were a means of finding passages, and the answer has to address what
        # was actually asked.
        result = answer_service.answer(
            state.question,
            passages,
        )

        return {
            "answer": result,
        }

    return answer


def cite(state: GraphState) -> StateUpdate:
    """Write validated citations into graph state (LEG-79)."""

    if not state.answer:
        return {
            "citations": (),
        }

    return {
        "citations": state.answer.citations,
    }
