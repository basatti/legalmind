"""Tests for the query router (LEG-76).

Three things are being tested, and they are different in kind:

  * that the instruction sheet says what we claim it says;
  * that a reply is turned into the right decision, including when the reply is
    not one of the two words we asked for;
  * that the decision actually changes the path a run takes — a router that
    classifies correctly and then sends every question the same way is not
    doing anything.

What cannot be tested here is whether a real model classifies well. No test can
establish that; LEG-85's gold set is where that question gets measured.
"""

from foundation.authorization import AllCases, AuthorizedCases
from graph import GraphState, Route, build_graph
from graph.nodes import make_route_node
from graph.routing_prompt import MULTI_STEP, SINGLE_SHOT, build_routing_prompt
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService

ARABIC_QUESTION = "ما هي أقصى مدة لفترة التجربة في نظام العمل؟"


class FakeLLM(LLMProvider):
    """Replies with whatever the test decided, and remembers what it was asked."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


class FakeRetrievalService(RetrievalService):
    """Returns no matches: these tests are about which nodes a run visits, not
    what retrieval finds. Deliberately does not call `super().__init__` — no
    `ChunkSearcher` or `EmbeddingProvider` is involved.
    """

    def __init__(self) -> None:
        pass

    def retrieve(self, question: str, within: AuthorizedCases, top_k: int = 5) -> list:
        return []


def classify(reply: str, question: str = "when does notice start?") -> Route | None:
    """Run just the route node against a model that replies with `reply`."""
    node = make_route_node(FakeLLM(reply))
    update = node(GraphState(question=question, authorized=AllCases()))
    result = update["route"]
    assert isinstance(result, Route)
    return result


def visited_nodes(reply: str) -> list[str]:
    """The nodes a full run passes through, in order, for this classification."""
    graph = build_graph(FakeLLM(reply), FakeRetrievalService())
    state = GraphState(question="q", authorized=AllCases())
    return [name for step in graph.stream(state) for name in step]


# --- the instruction sheet -------------------------------------------------


def test_the_prompt_offers_both_tokens_and_the_question() -> None:
    prompt = build_routing_prompt("when does notice start?")

    assert SINGLE_SHOT in prompt
    assert MULTI_STEP in prompt
    assert "when does notice start?" in prompt


def test_the_prompt_carries_no_passages() -> None:
    """Routing runs before retrieval, so there is nothing to show the model.

    Asserted rather than assumed because it is what keeps this call cheap: one
    short prompt per question, no documents attached.
    """
    prompt = build_routing_prompt(ARABIC_QUESTION)

    assert "[1]" not in prompt
    assert "Passages" not in prompt


# --- turning a reply into a decision ---------------------------------------


def test_the_agreed_tokens_are_understood() -> None:
    assert classify(MULTI_STEP) is Route.MULTI_STEP
    assert classify(SINGLE_SHOT) is Route.SINGLE_SHOT


def test_surrounding_whitespace_and_case_do_not_matter() -> None:
    """A model that answers "multi_step\\n" has still answered correctly.

    Only these two normalisations are applied — anything further would start
    guessing at intent, and the fallback below is a safer place to land than a
    creative reading of an unexpected reply.
    """
    assert classify("  multi_step\n") is Route.MULTI_STEP
    assert classify("Single_Shot ") is Route.SINGLE_SHOT


def test_an_unrecognised_reply_falls_back_to_single_shot() -> None:
    """The fallback is the behaviour the system already has today.

    A model that returns prose, an empty string, or a refusal must cost the
    improvement and nothing else. Sending the run down a path that does not
    exist, or raising, would turn a question that works in production into a
    failure the day routing ships.
    """
    assert classify("This looks like a multi-step question to me.") is Route.SINGLE_SHOT
    assert classify("") is Route.SINGLE_SHOT
    assert classify("NOT_FOUND") is Route.SINGLE_SHOT


def test_an_arabic_question_is_classified_like_any_other() -> None:
    """The corpus is Saudi labour law, so Arabic is the normal case, not an edge.

    The question reaches the model unaltered — nothing here inspects or
    transliterates it — and the decision comes back in the same fixed tokens.
    """
    node = make_route_node(fake := FakeLLM(MULTI_STEP))
    update = node(GraphState(question=ARABIC_QUESTION, authorized=AllCases()))

    assert update["route"] is Route.MULTI_STEP
    assert ARABIC_QUESTION in fake.prompts[0]


# --- the decision changes the path -----------------------------------------


def test_a_single_shot_question_skips_the_reason_node() -> None:
    """This is the point of the ticket: one lookup should not pay for reasoning."""
    visited = visited_nodes(SINGLE_SHOT)

    assert "reason" not in visited
    assert visited == ["route", "retrieve", "answer", "cite"]


def test_a_multi_step_question_reasons_before_retrieving() -> None:
    """Decomposition happens first, so retrieval is given the sub-questions.

    Order matters, not just presence: reasoning after the search would be
    reasoning about passages fetched for the compound question nobody intends
    to answer as a whole.
    """
    visited = visited_nodes(MULTI_STEP)

    assert visited.index("reason") < visited.index("retrieve")
    assert visited == ["route", "reason", "retrieve", "answer", "cite"]
