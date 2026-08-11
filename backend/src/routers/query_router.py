from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from embeddings.base import EmbeddingProvider
from embeddings.company_api import CompanyEmbeddingProvider, EmbeddingError
from embeddings.lazy import LazyEmbeddingProvider
from foundation.database import get_session
from foundation.models import User
from foundation.permissions import Permission
from foundation.schemas import QueryAskRequest, QueryAskResponse
from observability import Tracer, build_tracer
from repositories.assignment_case_reader import AssignmentCaseReader
from repositories.assignment_repository import AssignmentRepository
from repositories.document_chunk_repository import DocumentChunkRepository
from repositories.document_repository import DocumentRepository
from routers.auth_router import require_permission
from services.answer_service import AnswerService
from services.company_llm import CompanyLLMProvider
from services.lazy_llm import LazyLLMProvider
from services.llm import LLMError, LLMProvider
from services.rag_service import RagService
from services.retrieval_service import RetrievalService

router = APIRouter(prefix="/query", tags=["query"])


@lru_cache(maxsize=1)
def get_tracer() -> Tracer:
    """One tracer for the whole process (LEG-83).

    Cached because a real Langfuse client owns a background exporter thread and
    an HTTP connection pool — one per request would leak both. Returns a
    NullTracer whenever Langfuse is unconfigured, which is the normal case in
    CI and on a fresh clone.
    """
    return build_tracer()


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Built once per process, and CompanyEmbeddingProvider itself only built on
    first actual use — see LazyEmbeddingProvider.

    FastAPI resolves every dependency of a route before running its handler,
    so without the lazy wrapper, *every* request to /query/ask would need
    COMPANY_API_URL/COMPANY_API_KEY set — including requests that are
    rejected before ever reaching retrieval (unauthenticated, invalid input,
    or authorised for nothing).

    Must be the same model the ingestion worker used to embed the stored
    chunks. Vectors from two different models cannot be compared at all — the
    search would still return its top five, ranked by nothing.
    """
    return LazyEmbeddingProvider(lambda: CompanyEmbeddingProvider(tracer=get_tracer()))


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """The company's hosted model, in place of the local Ollama fallback.

    Lazily built for the same reason as get_embedding_provider above.
    """
    return LazyLLMProvider(lambda: CompanyLLMProvider(tracer=get_tracer()))


def get_rag_service(
    session: Session = Depends(get_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    llm: LLMProvider = Depends(get_llm_provider),
    tracer: Tracer = Depends(get_tracer),
) -> RagService:
    return RagService(
        case_reader=AssignmentCaseReader(AssignmentRepository(session)),
        retrieval=RetrievalService(
            chunks=DocumentChunkRepository(session),
            embedding_provider=embedding_provider,
        ),
        answers=AnswerService(llm),
        documents=DocumentRepository(session),
        llm=llm,
        tracer=tracer,
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
    except (LLMError, EmbeddingError) as exc:
        # The model is unreachable — an outage, not "your documents don't
        # contain the answer". Saying the latter would be a lie a lawyer might
        # act on. The detail is deliberately generic: the provider's own error
        # text can name hosts, models and quotas, none of which belong in a
        # client response.
        #
        # EmbeddingError belongs here for the same reason and was the more
        # urgent of the two: retrieval embeds the question before the model is
        # ever called, so an unreachable gateway raised it first, and its
        # message is "Could not reach {api_url}" — the exact leak this handler
        # exists to prevent, escaping as an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The answering service is temporarily unavailable",
        ) from exc
