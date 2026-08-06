"""RAG query service (LEG-14).

The front door for a question. This is the only place in the system where a
user's authorisation is resolved into a scope; everything below it receives
that scope as an argument and never works it out again.

Sequence: resolve what the user may see, run the graph, turn retrieved
passages into a grounded answer, and hand back the answer with its citations.

Also where a run's trace begins (LEG-84). The span opened here is the parent of
every model call the graph goes on to make, so one question reads as one trace
rather than a handful of unrelated ones.
"""

from foundation.authorization import AuthorizedCases, CaseReader, TheseCases
from foundation.models import User
from foundation.schemas import CitationResponse, QueryAskResponse
from graph.builder import build_graph
from graph.state import GraphState
from observability.tracer import Kind, NullTracer, Tracer
from repositories.document_repository import DocumentRepository
from services.answer_service import AnswerService
from services.llm import LLMProvider
from services.retrieval_service import RetrievalService


class RagService:
    def __init__(
        self,
        case_reader: CaseReader,
        retrieval: RetrievalService,
        answers: AnswerService,
        documents: DocumentRepository,
        llm: LLMProvider | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.case_reader = case_reader
        self.retrieval = retrieval
        self.answers = answers
        self.documents = documents
        self._tracer = tracer or NullTracer()

        # Falling back to the answer service's own provider keeps the router
        # and the reason node on the same model that writes the answer, which
        # is what a caller passing no `llm` is asking for.
        self.graph = build_graph(
            llm if llm is not None else answers.provider,
            retrieval,
            answers,
        )

    def ask(self, question: str, user: User) -> QueryAskResponse:
        with self._tracer.observe(
            "rag-run",
            kind=Kind.SPAN,
            input={"question": question},
        ) as record:
            authorized = self.case_reader.authorized_cases(user)
            record.metadata["scope"] = self._scope(authorized)

            if isinstance(authorized, TheseCases) and not authorized.case_ids:
                # Genuinely nothing this user is authorized to search — a clean
                # "no answer", not an error (LEG-65).
                record.output = {"answered": False, "why": "no authorized cases"}
                return QueryAskResponse(answer=None)

            state = GraphState(
                question=question,
                authorized=authorized,
            )

            result = self.graph.invoke(state)

            answer = result.get("answer")
            citations = result.get("citations", [])

            # Only knowable up here. A node sees its own step; nothing inside
            # the graph can report which shape the run took overall.
            record.metadata["route"] = str(result.get("route") or "unrouted")
            record.metadata["retrieval_passes"] = result.get("iterations", 0)
            record.metadata["passages"] = len(result.get("matches") or [])

            if not answer or not answer.answered:
                record.output = {"answered": False, "why": "no grounded answer"}
                return QueryAskResponse(answer=None)

            record.output = {
                "answered": True,
                "citations": len(citations),
                "answer": answer.text,
            }

            return QueryAskResponse(
                answer=answer.text,
                citations=[
                    CitationResponse(
                        document_id=citation.document_id,
                        document_name=self._filename(citation.document_id),
                        page_number=citation.page_number,
                    )
                    for citation in citations
                ],
            )

    @staticmethod
    def _scope(authorized: AuthorizedCases) -> str:
        """How wide this run was allowed to search, in a form a reader can use.

        Not the case ids themselves: the useful question when an answer looks
        wrong is "was this user searching one case or forty", and a list of
        integers answers that worse than a count does.
        """
        if isinstance(authorized, TheseCases):
            return f"{len(authorized.case_ids)} case(s)"
        return "all cases"

    def _filename(self, document_id: int) -> str:
        """Look up the document's stored filename for a citation.

        A plain lookup, not an LLM call — the model already told us which
        document and page (LEG-79); this just resolves that id to something
        a lawyer recognises instead of "Document #2" (LEG-69).
        """
        document = self.documents.get_by_id(document_id)
        return document.filename if document else "Unknown document"
