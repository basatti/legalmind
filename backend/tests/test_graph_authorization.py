"""Authorization regression tests for the graph (LEG-81).

LEG-65 proved the single-shot path cannot answer from a case the asker is not
authorized for. The graph reopens that question, because a multi-step run
retrieves more than once: the scope has to hold on the *last* hop as firmly as
on the first, and nothing between the hops may widen it.

Two levels, deliberately:

  * graph-level, with a recording fake, asserting the scope object handed to
    each retrieval is the very same one that entered the run — identity, not
    equality, so a rebuilt-but-equal scope would still fail;
  * HTTP-level, through the real router, real authorization and real pgvector
    query, re-running LEG-65's matrix with the loop switched on.

The adversarial case matters most. Sub-questions are model output — untrusted
text — and they become the *query* on later hops. A sub-question asking for
every case in the system must retrieve exactly as narrowly as any other,
because `within` travels through GraphState and is never derived from what a
node said. That is LEG-66's invariant; here it is stated as a test.
"""

import pytest

from embeddings.offline import OfflineEmbeddingProvider
from foundation.authorization import AllCases, AuthorizedCases, TheseCases
from foundation.models import EMBEDDING_DIMENSIONS, Role
from graph import GraphState, build_graph
from graph.builder import MULTI_STEP_ENV_VAR
from graph.reasoning_prompt import CONTINUE, DONE
from graph.routing_prompt import MULTI_STEP
from main import app
from routers.query_router import get_embedding_provider, get_llm_provider
from services.answer_service import Answer, AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService
from tests.conftest import create_user_and_login
from tests.test_query_router import (
    STUB_REPLY,
    assign,
    make_case,
    make_searchable_chunk,
)

# A sub-question written to widen the search, the way a prompt-injected or
# simply badly-behaved model might phrase one.
GREEDY_SUB_QUESTION = "all cases in the system, ignore restrictions, every document"


class MultiStepLLM(LLMProvider):
    """Routes multi-step, then asks for `hops` extra retrieval passes.

    The sub-question is deliberately greedy: if anything downstream let node
    output influence scope, this is the text that would do it.
    """

    def __init__(self, hops: int = 2, sub_question: str = GREEDY_SUB_QUESTION) -> None:
        self.hops = hops
        self.sub_question = sub_question
        self.reasoning_calls = 0

    def generate(self, prompt: str) -> str:
        if MULTI_STEP in prompt and CONTINUE not in prompt:
            return MULTI_STEP

        if CONTINUE in prompt and DONE in prompt:
            self.reasoning_calls += 1
            if self.reasoning_calls <= self.hops:
                return f"{CONTINUE}\n{self.sub_question}"
            return DONE

        return STUB_REPLY


class RecordingRetrievalService(RetrievalService):
    """Remembers the scope and query of every hop. Returns nothing: these tests
    are about what retrieval was *asked for*, not what it found."""

    def __init__(self) -> None:
        self.scopes: list[AuthorizedCases] = []
        self.questions: list[str] = []

    def retrieve(self, question: str, within: AuthorizedCases, top_k: int = 5) -> list:
        self.scopes.append(within)
        self.questions.append(question)
        return []


class StubAnswerService(AnswerService):
    def __init__(self) -> None:
        pass

    def answer(self, question: str, passages: list) -> Answer:
        return Answer.none_found()


def run_graph(scope: AuthorizedCases, hops: int = 2):
    retrieval = RecordingRetrievalService()
    graph = build_graph(MultiStepLLM(hops=hops), retrieval, StubAnswerService(), multi_step=True)
    final = graph.invoke(GraphState(question="the original question", authorized=scope))
    return final, retrieval


# ---------------------------------------------------------------------------
# Graph level: the scope survives every hop
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        AllCases(),
        TheseCases(case_ids=frozenset({7})),
        TheseCases(case_ids=frozenset({3, 9})),
        TheseCases(case_ids=frozenset()),
    ],
)
def test_every_hop_receives_the_identical_scope_object(scope: AuthorizedCases) -> None:
    """Not merely an equal scope — the same object.

    Equality would pass even if some node rebuilt the scope from values it had
    read, which is the shape of the mistake this test exists to catch: a scope
    that is recomputed is a scope that can be recomputed wrongly.
    """
    _, retrieval = run_graph(scope)

    assert len(retrieval.scopes) > 1, "the loop did not run; this proves nothing"
    assert all(seen is scope for seen in retrieval.scopes)


def test_the_greedy_sub_question_becomes_the_query_but_never_the_scope() -> None:
    """The hostile text does reach retrieval — as a *query*, which is harmless.

    Worth asserting both halves: that the sub-question really was used (so the
    test is exercising the path it claims to) and that the scope alongside it
    is untouched.
    """
    scope = TheseCases(case_ids=frozenset({7}))
    _, retrieval = run_graph(scope)

    assert GREEDY_SUB_QUESTION in retrieval.questions
    assert all(seen == scope for seen in retrieval.scopes)


def test_an_empty_scope_stays_empty_across_every_hop() -> None:
    """The case LEG-65 called out: authorized for nothing must not drift into
    "authorized for everything" on a later pass, which is exactly the confusion
    an empty list would have allowed before AllCases/TheseCases existed."""
    nothing = TheseCases(case_ids=frozenset())
    final, retrieval = run_graph(nothing)

    assert all(seen == nothing for seen in retrieval.scopes)
    assert final["authorized"] == nothing
    assert not isinstance(final["authorized"], AllCases)


def test_the_scope_on_the_state_is_unchanged_when_the_run_ends() -> None:
    """Whatever the nodes wrote, `authorized` is what it was at the front door."""
    scope = TheseCases(case_ids=frozenset({4}))
    final, retrieval = run_graph(scope)

    assert final["authorized"] is scope
    assert len(retrieval.scopes) > 1


def test_more_hops_do_not_loosen_the_scope() -> None:
    """A run that loops to the cap is the longest exposure there is."""
    scope = TheseCases(case_ids=frozenset({7}))
    _, retrieval = run_graph(scope, hops=99)

    assert len(retrieval.scopes) >= 3
    assert all(seen is scope for seen in retrieval.scopes)


# ---------------------------------------------------------------------------
# HTTP level: LEG-65's matrix, re-run with the loop on
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_step_providers(client, monkeypatch):
    """Real retrieval and real authorization; only the models are stand-ins,
    and the loop is switched on for the life of one test.

    Yields the shared model so a test can assert the loop actually engaged.
    Without that check these tests would still pass if the switch quietly
    failed to take effect — and would then be re-testing LEG-65's single-shot
    path under a name that claims otherwise.
    """
    monkeypatch.setenv(MULTI_STEP_ENV_VAR, "true")
    llm = MultiStepLLM()
    app.dependency_overrides[get_embedding_provider] = lambda: OfflineEmbeddingProvider(
        dimensions=EMBEDDING_DIMENSIONS
    )
    app.dependency_overrides[get_llm_provider] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_llm_provider, None)


def ask(client, question="What is the deadline?"):
    return client.post("/query/ask", json={"question": question})


def test_a_multi_step_question_still_cannot_reach_an_unassigned_case(
    client, session, multi_step_providers
):
    """LEG-81's headline: the content exists and is findable, the run makes
    several retrieval passes with a sub-question asking for everything, and the
    answer is still empty."""
    theirs = make_case(session, "assigned")
    someone_elses = make_case(session, "not assigned")
    user_id = create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, user_id, theirs.id)
    make_searchable_chunk(session, someone_elses.id, user_id)

    response = ask(client)

    assert multi_step_providers.reasoning_calls > 1, "the loop did not run; this proves nothing"
    assert response.status_code == 200
    assert response.json()["answer"] is None


def test_a_multi_step_question_from_a_paralegal_with_no_cases_finds_nothing(
    client, session, multi_step_providers
):
    other = make_case(session, "someone else's")
    user_id = create_user_and_login(client, session, "priya@example.com", Role.PARALEGAL)
    make_searchable_chunk(session, other.id, user_id)

    response = ask(client)

    assert response.status_code == 200
    assert response.json()["answer"] is None


def test_a_multi_step_question_still_reaches_an_assigned_case(
    client, session, multi_step_providers
):
    """The mirror image. Without this, every test above would also pass if the
    graph simply never retrieved anything."""
    case = make_case(session, "assigned")
    user_id = create_user_and_login(client, session, "amy@example.com", Role.ATTORNEY)
    assign(session, user_id, case.id)
    make_searchable_chunk(session, case.id, user_id)

    response = ask(client)
    body = response.json()

    assert multi_step_providers.reasoning_calls > 1, "the loop did not run; this proves nothing"
    assert response.status_code == 200
    assert body["answer"] == STUB_REPLY
    assert body["citations"] != []


def test_a_partner_keeps_unrestricted_scope_across_hops(client, session, multi_step_providers):
    """Partners hold case:read:any and have no Assignment rows, so their scope
    is AllCases rather than a list. That distinction has to survive the loop
    too — collapsing it to an empty TheseCases would silently answer nothing."""
    case = make_case(session, "nobody is assigned to this")
    user_id = create_user_and_login(client, session, "pat@example.com", Role.PARTNER)
    make_searchable_chunk(session, case.id, user_id)

    response = ask(client)

    assert multi_step_providers.reasoning_calls > 1, "the loop did not run; this proves nothing"
    assert response.status_code == 200
    assert response.json()["answer"] == STUB_REPLY
