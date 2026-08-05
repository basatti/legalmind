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
from services.retrieval_service import RetrievalService

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
    """Build retrieval node using RetrievalService (LEG-77)."""

    def retrieve(state: GraphState) -> StateUpdate:
        matches = retrieval_service.retrieve(
            state.question,
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

        summaries = [match.chunk.text for match in state.matches]

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
        passages = []

        for match in state.matches:
            passages.extend(match.context_chunks)

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
