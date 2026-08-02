from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from embeddings.base import EmbeddingProvider
from embeddings.company_api import CompanyEmbeddingProvider
from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import QueryAskRequest, QueryAskResponse
from repositories.assignment_case_reader import AssignmentCaseReader
from repositories.assignment_repository import AssignmentRepository
from repositories.document_chunk_repository import DocumentChunkRepository
from routers.auth_router import require_permission
from services.answer_service import AnswerService
from services.company_llm import CompanyLLMProvider
from services.llm import LLMError, LLMProvider
from services.rag_service import RagService
from services.retrieval_service import RetrievalService

router = APIRouter(prefix="/query", tags=["query"])


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Built once per process. A network call, not a 2GB local load, so unlike
    the earlier self-hosted BgeM3EmbeddingProvider this needs no lazy wrapper.

    Must be the same model the ingestion worker used to embed the stored
    chunks. Vectors from two different models cannot be compared at all — the
    search would still return its top five, ranked by nothing.
    """
    return CompanyEmbeddingProvider()


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """The company's hosted model, in place of the local Ollama fallback."""
    return CompanyLLMProvider()


def get_rag_service(
    session: Session = Depends(get_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm: LLMProvider = Depends(get_llm_provider),
) -> RagService:
    return RagService(
        case_reader=AssignmentCaseReader(AssignmentRepository(session)),
        retrieval=RetrievalService(
            chunks=DocumentChunkRepository(session),
            embedding_provider=embedding_provider,
        ),
        answers=AnswerService(llm),
    )


@router.post("/ask")
def ask(
    data: QueryAskRequest,
    service: RagService = Depends(get_rag_service),
    user: User = Depends(
        require_permission(Permission.CASE_READ_ANY, Permission.CASE_READ_ASSIGNED)
    ),
) -> QueryAskResponse:
    try:
        return service.ask(data.question, user)
    except LLMError as exc:
        # The model is unreachable — an outage, not "your documents don't
        # contain the answer". Saying the latter would be a lie a lawyer might
        # act on. The detail is deliberately generic: the provider's own error
        # text can name hosts, models and quotas, none of which belong in a
        # client response.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The answering service is temporarily unavailable",
        ) from exc
