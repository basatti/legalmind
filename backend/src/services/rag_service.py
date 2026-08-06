"""RAG query service (LEG-14).

The front door for a question. This is the only place in the system where a
user's authorisation is resolved into a scope; everything below it receives
that scope as an argument and never works it out again.

Sequence: resolve what the user may see, run the graph, turn retrieved
passages into a grounded answer, and hand back the answer with its citations.
"""

from foundation.authorization import CaseReader, TheseCases
from foundation.models import User
from foundation.schemas import CitationResponse, QueryAskResponse
from graph.builder import build_graph
from graph.state import GraphState
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
    ) -> None:
        self.case_reader = case_reader
        self.retrieval = retrieval
        self.answers = answers
        self.documents = documents

        # Falling back to the answer service's own provider keeps the router
        # and the reason node on the same model that writes the answer, which
        # is what a caller passing no `llm` is asking for.
        self.graph = build_graph(
            llm if llm is not None else answers.provider,
            retrieval,
            answers,
        )

    def ask(self, question: str, user: User) -> QueryAskResponse:
        authorized = self.case_reader.authorized_cases(user)

        if isinstance(authorized, TheseCases) and not authorized.case_ids:
            # Genuinely nothing this user is authorized to search — a clean
            # "no answer", not an error (LEG-65).
            return QueryAskResponse(answer=None)

        state = GraphState(
            question=question,
            authorized=authorized,
        )

        result = self.graph.invoke(state)

        answer = result.get("answer")
        citations = result.get("citations", [])

        if not answer or not answer.answered:
            return QueryAskResponse(answer=None)

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

    def _filename(self, document_id: int) -> str:
        """Look up the document's stored filename for a citation.

        A plain lookup, not an LLM call — the model already told us which
        document and page (LEG-79); this just resolves that id to something
        a lawyer recognises instead of "Document #2" (LEG-69).
        """
        document = self.documents.get_by_id(document_id)
        return document.filename if document else "Unknown document"
