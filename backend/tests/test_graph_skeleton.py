"""Tests for the RAG graph's shape (LEG-74).

Not the nodes' behaviour — each node is tested where it is implemented — but
two guarantees that have to hold at *every* stage of building the graph, not
only once it is finished:

  * an unfinished graph answers nothing rather than answering badly;
  * the authorisation scope arrives at the end exactly as it went in.

Both are cheap to hold now and expensive to retrofit, which is why they are
asserted while there is still very little else to assert. These tests are
expected to keep passing unchanged as LEG-77 to LEG-79 fill in the remaining
nodes; the day one of them starts failing, a node has begun answering or
rescoping when it should not.

Nothing here touches a database or a real model — compiling the graph is pure.
"""

from foundation.authorization import AllCases, TheseCases
from graph import GraphState, build_graph
from graph.routing_prompt import SINGLE_SHOT
from services.llm import LLMProvider

EXPECTED_NODES = {"route", "retrieve", "reason", "answer", "cite"}


class FakeLLM(LLMProvider):
    """Classifies everything as single-shot, so these tests exercise one fixed path.

    The router's own behaviour is covered in test_route_node.py; here the model
    is only present because compiling the graph requires one.
    """

    def generate(self, prompt: str) -> str:
        return SINGLE_SHOT


def test_the_graph_has_exactly_the_five_nodes_the_epic_names() -> None:
    """LEG-16 specifies route -> retrieve -> reason -> answer -> cite.

    Asserted by name so that renaming a node — which silently breaks the edges
    referring to it — fails here rather than at runtime.
    """
    graph = build_graph(FakeLLM())

    nodes = {name for name in graph.get_graph().nodes if not name.startswith("__")}

    assert nodes == EXPECTED_NODES


def test_a_partly_built_graph_answers_nothing() -> None:
    """A half-built graph must fail closed.

    `route` is implemented; `retrieve`, `reason`, `answer` and `cite` are not,
    so nothing ever sets `answer` and it stays None — which RagService already
    treats as "no answer". This is the property that lets LEG-77 to LEG-79 land
    one at a time: a partly-wired graph declines to answer instead of
    assembling one out of whichever nodes happen to be done.
    """
    graph = build_graph(FakeLLM())

    result = graph.invoke(GraphState(question="ما هي مدة فترة التجربة؟", authorized=AllCases()))

    assert result["answer"] is None
    assert result["citations"] == ()
    assert result["iterations"] == 0


def test_the_authorized_scope_survives_a_run_unchanged() -> None:
    """Scope is resolved once, at the front door, and no node may widen it.

    Checked in both directions, per LEG-65: the unrestricted case and the
    authorized-for-nothing case. The second matters most — an empty TheseCases
    that came back as AllCases, or as anything other than itself, would be the
    exact confusion foundation.authorization exists to make impossible.
    """
    graph = build_graph(FakeLLM())

    unrestricted = graph.invoke(GraphState(question="q", authorized=AllCases()))
    assert unrestricted["authorized"] == AllCases()

    nothing = TheseCases(case_ids=frozenset())
    assigned_to_nothing = graph.invoke(GraphState(question="q", authorized=nothing))
    assert assigned_to_nothing["authorized"] == nothing

    one_case = TheseCases(case_ids=frozenset({7}))
    assigned_to_one = graph.invoke(GraphState(question="q", authorized=one_case))
    assert assigned_to_one["authorized"] == one_case
