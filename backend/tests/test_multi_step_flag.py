"""Tests for the multi-step rollback switch (LEG-80).

LEG-80 asked for "a config flag to fall back to single-shot, so a regression is
one env var away from rollback". Three things have to hold for that to be true:

  * off by default, and off for anything that is not an explicit yes — a
    rollback switch that fails open is not a rollback switch;
  * off means the reason loop is unreachable, not merely unlikely;
  * off also means the routing model call is skipped, since a classification
    with one reachable destination is a call spent to learn nothing.

Nothing here touches a database, a real model, or os.environ except through
monkeypatch.
"""

import pytest

from foundation.authorization import AllCases, AuthorizedCases
from graph import GraphState, build_graph
from graph.builder import MULTI_STEP_ENV_VAR, multi_step_enabled
from graph.routing_prompt import MULTI_STEP
from graph.state import Route
from services.answer_service import Answer, AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService


class CountingLLM(LLMProvider):
    """Always votes multi-step, and records every prompt it is asked for."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return MULTI_STEP


class NoopRetrievalService(RetrievalService):
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, question: str, within: AuthorizedCases, top_k: int = 5) -> list:
        self.calls += 1
        return []


class StubAnswerService(AnswerService):
    def __init__(self) -> None:
        pass

    def answer(self, question: str, passages: list) -> Answer:
        return Answer.none_found()


def run(multi_step: bool):
    llm = CountingLLM()
    retrieval = NoopRetrievalService()
    graph = build_graph(llm, retrieval, StubAnswerService(), multi_step=multi_step)
    final = graph.invoke(GraphState(question="q", authorized=AllCases()))
    return final, llm, retrieval


# --- reading the environment --------------------------------------------------


def test_the_loop_is_off_when_the_variable_is_unset(monkeypatch) -> None:
    monkeypatch.delenv(MULTI_STEP_ENV_VAR, raising=False)

    assert multi_step_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " true "])
def test_explicit_yeses_turn_the_loop_on(monkeypatch, value: str) -> None:
    monkeypatch.setenv(MULTI_STEP_ENV_VAR, value)

    assert multi_step_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", "ture", "enabled"])
def test_anything_else_leaves_it_off(monkeypatch, value: str) -> None:
    """Including plausible typos. The switch fails closed on purpose: an
    unrecognised value means somebody's intent is unclear, and the safe
    reading of unclear intent is the behaviour that answers questions."""
    monkeypatch.setenv(MULTI_STEP_ENV_VAR, value)

    assert multi_step_enabled() is False


# --- what the flag actually changes -------------------------------------------


def test_with_the_loop_off_a_multi_step_vote_is_not_even_asked_for() -> None:
    """The model votes MULTI_STEP every time here and still never runs: with
    one reachable destination there is no question worth asking it."""
    final, llm, retrieval = run(multi_step=False)

    assert llm.prompts == []
    assert final["route"] is Route.SINGLE_SHOT
    assert final["iterations"] == 0
    assert retrieval.calls == 1


def test_with_the_loop_on_the_same_vote_reaches_reason() -> None:
    """The mirror of the test above — same fake, same question, loop enabled."""
    final, llm, _ = run(multi_step=True)

    assert llm.prompts != []
    assert final["route"] is Route.MULTI_STEP
    assert final["iterations"] >= 1


def test_the_default_follows_the_environment(monkeypatch) -> None:
    """Omitting the argument reads the switch, so deployment decides this and
    no call site has to remember to."""
    monkeypatch.setenv(MULTI_STEP_ENV_VAR, "false")
    llm = CountingLLM()
    graph = build_graph(llm, NoopRetrievalService(), StubAnswerService())

    final = graph.invoke(GraphState(question="q", authorized=AllCases()))

    assert final["route"] is Route.SINGLE_SHOT
    assert llm.prompts == []
