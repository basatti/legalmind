"""Manual smoke-test: seed a throwaway user + case + embedded chunk and
verify the RAG ask flow returns a real, grounded answer from the company API.

Unlike the pytest suite (which fakes the embedding/LLM providers), this hits
the real company-hosted API end to end, through the actual UI — the only way
to check that a real question gets a real, correctly cited answer back.

Usage:
    uv run python scripts/smoke_test_rag.py             # seed test data
    uv run python scripts/smoke_test_rag.py --cleanup   # remove it

After seeding, start both dev servers if they aren't already running:
    uv run uvicorn main:app --reload --app-dir src   # from backend/
    npm run dev                                       # from frontend/

Then log in at http://localhost:3000/login with the printed credentials,
open the printed case, and ask the printed question. A correct run returns
an answer citing the seeded document — not an error or "no answer".

Requires COMPANY_API_URL/COMPANY_API_KEY set in backend/.env (this makes a
real embedding API call) and the dev Postgres/pgvector container running.

Gotcha: pydantic's email validator rejects reserved TLDs (.local, .test,
.invalid, .example) at login, even though the DB will happily store them —
that's why this uses an @example.com address instead of @legalmind.local.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlmodel import Session, create_engine, select  # noqa: E402

from embeddings.company_api import CompanyEmbeddingProvider  # noqa: E402
from foundation.hashing import hash_password  # noqa: E402
from foundation.models import (  # noqa: E402
    Assignment,
    Case,
    CaseStatus,
    Document,
    DocumentChunk,
    Role,
    User,
)
from foundation.models import Session as SessionModel  # noqa: E402

DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/legalmind"
EMAIL = "smoketest@example.com"
PASSWORD = "SmokeTest123!"
CASE_TITLE = "RAG smoke test"
SAMPLE_QUESTION = "ما هي أقصى مدة لفترة التجربة في نظام العمل؟"

# Two real articles from نظام العمل (Saudi Labor Law), covering probation
# periods — chosen for a clean, checkable factual answer ("180 يوماً").
# Source: backend/data/corpus/chunks_hrsd_labor_law.jsonl (chunks 56-57).
CHUNKS = [
    {
        "section": "المادة الثالثة والخمسون",
        "body": (
            "إذا كان العامل خاضعاً للتجربة، وجب النص على ذلك صراحة في عقد العمل، "
            "وتحديد مدتها بوضوح، على ألا يزيد مجموع المدة في جميع الأحوال على "
            "(مائة وثمانين) يوماً. وتبين اللائحة الأحكام المتصلة بذلك بما في ذلك "
            "ما يتعلق بالإجازات التي لا تدخل في حساب المدة. ولكل من الطرفين الحق "
            "في إنهاء العقد خلال هذه المدة."
        ),
    },
    {
        "section": "المادة الرابعة والخمسون",
        "body": (
            "لا يجوز وضع العامل تحت التجربة أكثر من مرة واحدة لدى صاحب عمل واحد. "
            "واستثناء من ذلك يجوز باتفاق طرفي العقد - كتابة - إخضاع العامل لفترة "
            "تجربة أخرى بشرط أن تكون في مهنة أخرى أو عمل آخر، أو أن يكون قد مضى "
            "على انتهاء علاقة العامل بصاحب العمل مدة لا تقل عن ستة أشهر. وإذا "
            "أنهي العقد خلال فترة التجربة فإن أيًّا من الطرفين لا يستحق تعويضاً، "
            "كما لا يستحق العامل مكافأة نهاية الخدمة عن ذلك."
        ),
    },
]


def seed() -> None:
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        if session.exec(select(User).where(User.email == EMAIL)).first():
            print(f"{EMAIL} already exists — run --cleanup first")
            return

        user = User(
            email=EMAIL,
            full_name="Smoke Test User",
            hashed_password=hash_password(PASSWORD),
            role=Role.PARALEGAL,
            must_change_password=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        case = Case(
            title=CASE_TITLE,
            description="Seeded by scripts/smoke_test_rag.py, safe to delete",
            status=CaseStatus.IN_PROGRESS,
        )
        session.add(case)
        session.commit()
        session.refresh(case)

        session.add(Assignment(case_id=case.id, user_id=user.id))

        document = Document(
            case_id=case.id,
            filename="hrsd_labor_law_excerpt.pdf",
            file_path="smoketest-not-a-real-file.pdf",
            uploaded_by=user.id,
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        provider = CompanyEmbeddingProvider()
        texts = [f"[{c['section']}]\n{c['body']}" for c in CHUNKS]
        vectors = provider.embed(texts)

        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True)):
            session.add(
                DocumentChunk(
                    case_id=case.id,
                    document_id=document.id,
                    page_number=1,
                    sequence=i,
                    text=text,
                    embedding=vector,
                )
            )
        session.commit()

        print(f"Seeded case {case.id} with {len(CHUNKS)} embedded chunks.\n")
        print(f"1. Log in at http://localhost:3000/login as {EMAIL} / {PASSWORD}")
        print(f"2. Open http://localhost:3000/cases/{case.id}")
        print(f"3. Ask: {SAMPLE_QUESTION}")
        print('\nExpect a cited answer mentioning "180" / "مائة وثمانين" — not an error.')


def cleanup() -> None:
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == EMAIL)).first()
        if not user:
            print("nothing to clean up")
            return

        case = session.exec(select(Case).where(Case.title == CASE_TITLE)).first()
        if case is not None:
            for row in session.exec(
                select(DocumentChunk).where(DocumentChunk.case_id == case.id)
            ).all():
                session.delete(row)
            for row in session.exec(select(Document).where(Document.case_id == case.id)).all():
                session.delete(row)
            for row in session.exec(select(Assignment).where(Assignment.case_id == case.id)).all():
                session.delete(row)

        for row in session.exec(select(SessionModel).where(SessionModel.user_id == user.id)).all():
            session.delete(row)

        if case is not None:
            session.delete(case)
        session.delete(user)
        session.commit()
        print("cleaned up")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="remove the seeded test data instead of creating it"
    )
    args = parser.parse_args()

    cleanup() if args.cleanup else seed()


if __name__ == "__main__":
    main()
