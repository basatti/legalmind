"""Tests for the reason <-> retrieve loop and its cap (LEG-78, LEG-80).

The node-level behaviour of `reason` is tested through the graph here rather
than in isolation, because the thing that matters is not what the node returns
— it is whether the compiled graph actually stops. An unbounded
reason -> retrieve cycle would keep calling the company gateway until the
request timed out, which is the failure LEG-78 exists to prevent.

Four properties:

  * a single-shot run never enters `reason` at all;
  * a multi-step run does loop back, so sub-questions reach retrieval;
  * a model that always says CONTINUE is still stopped, by the cap;
  * DONE ends the loop before the cap.

Nothing here touches a database or a real model.
"""

from foundation.authorization import AllCases, AuthorizedCases
from graph import GraphState, build_graph
from graph.nodes import MAX_ITERATIONS
from graph.reasoning_prompt import CONTINUE, DONE
from graph.routing_prompt import MULTI_STEP, SINGLE_SHOT
from services.answer_service import Answer, AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService


class ScriptedLLM(LLMProvider):
    """Answers the router with `route`, and every reasoning pass with the next
    scripted decision (repeating the last one once the script runs out).

    The two prompts are told apart by the tokens they ask for, which is the
    same contract the nodes themselves rely on.
    """

    def __init__(self, route: str, reasoning: list[str] | None = None) -> None:
        self.route = route
        self.reasoning = reasoning or [DONE]
        self.reasoning_calls = 0

    def generate(self, prompt: str) -> str:
        if MULTI_STEP in prompt and CONTINUE not in prompt:
            return self.route

        decision = self.reasoning[min(self.reasoning_calls, len(self.reasoning) - 1)]
        self.reasoning_calls += 1
        # CONTINUE has to carry a sub-question on the second line; DONE must not.
        return f"{CONTINUE}\nsub-question {self.reasoning_calls}" if decision == CONTINUE else DONE


class CountingRetrievalService(RetrievalService):
    """Records each query it is asked for. Returns nothing, so the answer node
    has no passages and the run ends in a clean "no answer" — these tests are
    about control flow, not about answers."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve(self, question: str, within: AuthorizedCases, top_k: int = 5) -> list:
        self.queries.append(question)
        return []


class StubAnswerService(AnswerService):
    """Always declines to answer, so nothing here depends on an LLM reply."""

    def __init__(self) -> None:
        self.calls = 0

    def answer(self, question: str, passages: list) -> Answer:
        self.calls += 1
        return Answer.none_found()


def run(route: str, reasoning: list[str] | None = None):
    llm = ScriptedLLM(route, reasoning)
    retrieval = CountingRetrievalService()
    answers = StubAnswerService()
    graph = build_graph(llm, retrieval, answers)

    final = graph.invoke(GraphState(question="the original question", authorized=AllCases()))
    return final, llm, retrieval, answers


# --- single-shot never loops --------------------------------------------------


def test_a_single_shot_run_never_enters_reason() -> None:
    final, llm, retrieval, answers = run(SINGLE_SHOT)

    assert final["iterations"] == 0
    assert llm.reasoning_calls == 0
    assert retrieval.queries == ["the original question"]
    assert answers.calls == 1


# --- multi-step loops ---------------------------------------------------------


def test_a_multi_step_run_loops_back_for_each_sub_question() -> None:
    """Two CONTINUEs then DONE.

    The original question is always searched first; each CONTINUE then adds one
    more pass, searching the sub-question it produced.
    """
    final, _, retrieval, answers = run(MULTI_STEP, [CONTINUE, CONTINUE, DONE])

    assert retrieval.queries == ["the original question", "sub-question 1", "sub-question 2"]
    assert final["reasoning"] == ["sub-question 1", "sub-question 2"]
    assert answers.calls == 1


def test_done_on_the_first_pass_answers_from_the_first_retrieval() -> None:
    """`reason` may decide the first search already found enough.

    It falls through to answer with that one retrieval's passages — never with
    nothing, which is what reasoning ahead of any search used to risk.
    """
    final, _, retrieval, answers = run(MULTI_STEP, [DONE])

    assert retrieval.queries == ["the original question"]
    assert final["iterations"] == 1
    assert answers.calls == 1


# --- the cap actually stops it ------------------------------------------------


def test_a_model_that_never_says_done_is_still_stopped() -> None:
    """The property LEG-78 exists for: an always-CONTINUE model must not spin.

    Without the cap this call would not return.
    """
    final, llm, retrieval, answers = run(MULTI_STEP, [CONTINUE])

    assert final["iterations"] == MAX_ITERATIONS + 1
    # The opening search on the original question, plus one per CONTINUE.
    assert len(retrieval.queries) == MAX_ITERATIONS + 1
    assert answers.calls == 1
    assert final["answer"] is not None and not final["answer"].answered


def test_the_run_still_ends_in_a_clean_no_answer_when_capped() -> None:
    """Hitting the limit degrades to "no answer", never to an error."""
    final, _, _, _ = run(MULTI_STEP, [CONTINUE])

    assert final["citations"] == ()
