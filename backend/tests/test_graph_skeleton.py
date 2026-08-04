"""Tests for the RAG graph skeleton (LEG-74).

Every node is still a stub, so there is no behaviour to test yet. What there is
is a shape — the nodes LEG-76 to LEG-79 will fill in, and two guarantees that
have to hold at every stage of building it, not just once it is finished:

  * an unfinished graph answers nothing rather than answering badly;
  * the authorisation scope arrives at the end exactly as it went in.

Both are cheap to hold now and expensive to retrofit, which is why they are
asserted before there is anything else to assert. Nothing here touches a
database or a model — compiling the graph is pure.
"""

from foundation.authorization import AllCases, TheseCases
from graph import GraphState, build_graph

EXPECTED_NODES = {"route", "retrieve", "reason", "answer", "cite"}


def test_the_graph_has_exactly_the_five_nodes_the_epic_names() -> None:
    """LEG-16 specifies route -> retrieve -> reason -> answer -> cite.

    Asserted by name so that renaming a node — which silently breaks the edges
    referring to it — fails here rather than at runtime.
    """
    graph = build_graph()

    nodes = {name for name in graph.get_graph().nodes if not name.startswith("__")}

    assert nodes == EXPECTED_NODES


def test_a_run_of_the_stub_graph_answers_nothing() -> None:
    """A half-built graph must fail closed.

    Every node currently returns an empty update, so `answer` stays None — and
    None is what RagService already treats as "no answer". This is the property
    that lets LEG-76 to LEG-79 land one at a time: a partly-wired graph declines
    to answer instead of assembling one out of whatever nodes happen to be done.
    """
    graph = build_graph()

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
    graph = build_graph()

    unrestricted = graph.invoke(GraphState(question="q", authorized=AllCases()))
    assert unrestricted["authorized"] == AllCases()

    nothing = TheseCases(case_ids=frozenset())
    assigned_to_nothing = graph.invoke(GraphState(question="q", authorized=nothing))
    assert assigned_to_nothing["authorized"] == nothing

    one_case = TheseCases(case_ids=frozenset({7}))
    assigned_to_one = graph.invoke(GraphState(question="q", authorized=one_case))
    assert assigned_to_one["authorized"] == one_case
