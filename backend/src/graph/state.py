"""What every node in the RAG graph reads from and writes to (LEG-74).

Defined before any node exists, so LEG-76 through LEG-79 can each fill in one
node without renegotiating the shape between them — the same reason LEG-64
settled `CaseReader` before LEG-61/62/63 were built against it.

The field that matters most is `authorized`. It is resolved once, by
`RagService.ask()`, and travels with the state; no node works it out again. A
node that resolved scope for itself would be a second place where authorisation
is decided, which is exactly what LEG-66's invariant rules out.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from foundation.authorization import AuthorizedCases
from services.answer_service import Answer, Citation
from services.retrieval_service import RetrievedMatch


class Route(StrEnum):
    """What the router decided this question needs.

    An enum rather than a bool: "single-shot or not" reads as a yes/no today,
    but the epic's router is expected to grow more destinations, and a bool
    would have to be replaced rather than extended. `StrEnum` — matching Role,
    Permission and CaseStatus in foundation.models — so a log line or a Langfuse
    span (LEG-83) shows "multi_step" instead of an opaque integer.
    """

    SINGLE_SHOT = "single_shot"
    MULTI_STEP = "multi_step"


@dataclass
class GraphState:
    """Everything the graph knows about one question at one point in the run.

    Mutable by design: LangGraph merges each node's returned update into this
    object as the run proceeds. Contrast `AllCases`/`TheseCases`, which are
    frozen — those are a decision already made, this is a decision in progress.
    """

    question: str

    authorized: AuthorizedCases
    """Which cases this run may draw on. Set once at the front door; read-only
    to every node. Never recompute it — see the module docstring."""

    route: Route | None = None
    """None until the route node has run. LEG-76."""

    matches: list[RetrievedMatch] = field(default_factory=list)
    """Passages retrieved so far, already scoped by `authorized`. A multi-step
    question can add to this across several passes, so it accumulates rather
    than being replaced. LEG-77."""

    reasoning: list[str] = field(default_factory=list)
    """The reason node's intermediate working — sub-questions asked, what each
    pass concluded. Kept because it is what makes a trace readable when someone
    debugs a wrong answer (LEG-88), not because the answer depends on it."""

    iterations: int = 0
    """How many times the reason node has looped. LEG-78 caps this: an
    unbounded reason -> retrieve -> reason cycle would keep calling the company
    gateway until the request times out."""

    answer: Answer | None = None
    """None means no answer — the same outcome whether nothing was retrieved,
    the model reported the answer was not in the passages, or its reply failed
    validation. `AnswerService` already collapses those three cases on purpose;
    the graph does not reopen the distinction."""

    citations: tuple[Citation, ...] = ()
    """Where the cite node writes. Separate from `answer.citations` only
    because LEG-79 has yet to decide whether "cite" is a real node — if it
    stays folded into the answer node, this simply mirrors `answer.citations`;
    if it becomes real (enriching citations with document filenames, closing
    the "Document #2" gap from LEG-69), it holds the enriched set."""

    should_continue: bool = False
    """Set by the reason node: True sends the run back to retrieve for
    another pass, False lets it fall through to answer. LEG-78. Read once by
    the graph's conditional edge after reason, never by reason itself on a
    later call - the node decides fresh each time from state.iterations and
    what it just read, not from what it decided last time."""

    should_continue: bool = False
    """Set by the reason node: True sends the run back to retrieve for
    another pass, False lets it fall through to answer. LEG-78. Read once by
    the graph's conditional edge after reason, never by reason itself on a
    later call - the node decides fresh each time from state.iterations and
    what it just read, not from what it decided last time."""
