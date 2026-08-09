"""Build the demo dataset from an empty database, in one command (LEG-98).

The corpus that existed before this script was ingested ad hoc: nobody could
recreate it, so a wiped database meant re-uploading files by hand and hoping.
This makes the dataset a thing you can rebuild — during a demo, not just before
one.

    uv run python scripts/seed_demo.py            # build it
    uv run python scripts/seed_demo.py --reset    # rebuild from scratch
    uv run python scripts/seed_demo.py --cleanup  # remove it, leave the rest
    uv run python scripts/seed_demo.py --limit 20 # a fast subset, for a smoke check

Safe to re-run: without --reset it refuses rather than seeding a second copy.
--reset removes only what this script created, matched on the seed marker in
each case's description, and never touches the admin account, other users, or
cases anyone made by hand.

What it builds, and why this shape:

  Two cases, three users, and assignments arranged so the authorization story
  can be demonstrated rather than asserted. The attorney is assigned to the
  labor-law case only, the paralegal to the contract case only, and the partner
  to neither — a partner holds case:read:any, so an empty assignment list is
  exactly the interesting case: they can still answer from both.

  Ask the attorney's account a question about the contract case and the answer
  is a clean refusal, not an error and not a leak. That contrast is the whole
  point of the retrieval-authorization design (docs/retrieval-authorization.md),
  and it needs two cases with different content to show at all.

Chunks are embedded and written directly rather than uploaded through the
ingestion queue. The queue path needs a running worker and takes minutes on a
254-chunk corpus; this takes one command and finishes while someone is still
apologising for the failed demo. Uploading a document live is a better way to
show ingestion anyway — it is a thing an audience can watch happen.

Requires: DATABASE_URL reachable, migrations applied (`alembic upgrade head`),
and COMPANY_API_URL / COMPANY_API_KEY set — the embeddings are real calls to
the company gateway, so this needs the VPN.
"""

import argparse
import json
import os
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
    IngestionJob,
    Role,
    User,
)
from foundation.models import Session as SessionModel  # noqa: E402

# Every row this script creates is reachable from a case carrying this marker,
# which is what makes --cleanup precise instead of "delete things that look
# seeded".
SEED_MARKER = "[seed_demo] Rebuild with: uv run python scripts/seed_demo.py --reset"

CORPUS = Path(__file__).resolve().parent.parent / "seed" / "labor_law_corpus.jsonl"

# The gateway is happy with a few hundred short texts, but one request per
# chunk would be 254 round trips and one request for all of them risks a
# timeout on a slow link. Batching is the boring middle.
EMBED_BATCH = 32

PASSWORD = "DemoPass123!"

DEMO_USERS = [
    ("partner@legalmind.com", "Partner (demo)", Role.PARTNER),
    ("attorney@legalmind.com", "Attorney (demo)", Role.ATTORNEY),
    ("paralegal@legalmind.com", "Paralegal (demo)", Role.PARALEGAL),
]

LABOR_CASE_TITLE = "استشارة نظام العمل"
CONTRACT_CASE_TITLE = "مراجعة عقد توظيف"

# The contract case exists to be the case the attorney cannot see. It is small
# on purpose: it only has to hold one fact that is unmistakably not in the
# labor law, so "did the scope hold" has an unambiguous answer.
CONTRACT_CHUNKS = [
    {
        "section": "البند الرابع - الراتب",
        "text": (
            "[البند الرابع - الراتب]\n"
            "يتقاضى الطرف الثاني راتباً شهرياً قدره ثمانية عشر ألف ريال سعودي "
            "(18,000 ريال)، يُدفع في اليوم الأخير من كل شهر ميلادي، بالإضافة إلى "
            "بدل سكن سنوي يعادل راتب ثلاثة أشهر."
        ),
    },
    {
        "section": "البند السابع - عدم المنافسة",
        "text": (
            "[البند السابع - عدم المنافسة]\n"
            "يلتزم الطرف الثاني بعدم العمل لدى أي منشأة منافسة داخل المملكة "
            "لمدة سنة واحدة من تاريخ انتهاء العلاقة التعاقدية، وذلك في مدينة "
            "الرياض على وجه التحديد."
        ),
    },
]

# Two questions with checkable answers: one the demo asks as itself, one that
# only the contract case can answer and so doubles as the authorization probe.
DEMO_QUESTIONS = [
    ("labor", "كم يوماً رصيد الإجازة السنوية للعامل في نظام العمل؟"),
    ("contract", "ما مقدار الراتب الشهري المتفق عليه في العقد؟"),
]


def _describe(url: str) -> str:
    """host/database from a connection URL, with the credentials stripped."""
    return url.rsplit("@", 1)[-1] if "@" in url else url.rsplit("//", 1)[-1]


def _load_corpus(limit: int | None) -> list[dict]:
    if not CORPUS.exists():
        raise SystemExit(
            f"corpus not found at {CORPUS}\n"
            "It ships with the repo; if it is missing, regenerate it with\n"
            "  uv run --with requests,beautifulsoup4 python scripts/fetch_hrsd_labor_law.py"
        )
    with CORPUS.open(encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    return records[:limit] if limit else records


def _embed_all(texts: list[str]) -> list[list[float]]:
    provider = CompanyEmbeddingProvider()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        vectors.extend(provider.embed(batch))
        print(f"  embedded {min(start + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)
    return vectors


def _seeded_cases(session: Session) -> list[Case]:
    return list(session.exec(select(Case).where(Case.description == SEED_MARKER)).all())


def cleanup(session: Session, quiet: bool = False) -> None:
    cases = _seeded_cases(session)
    emails = [email for email, _, _ in DEMO_USERS]

    case_ids = [case.id for case in cases]
    documents = [
        document
        for case_id in case_ids
        for document in session.exec(select(Document).where(Document.case_id == case_id)).all()
    ]

    # Deleted in dependency order, committing between phases. Interleaving the
    # phases does not work: a query issued while a delete is still pending
    # triggers an autoflush, and the half-applied order hits the foreign key it
    # was about to satisfy.
    for case_id in case_ids:
        for chunk in session.exec(
            select(DocumentChunk).where(DocumentChunk.case_id == case_id)
        ).all():
            session.delete(chunk)
    session.commit()

    # Documents this script seeded have no ingestion job — their chunks were
    # written directly. One *uploaded during a demo* does, and the job holds an
    # FK to the document. Without this the reset aborts at exactly the moment it
    # is most needed: something went wrong on stage and the fix is one command.
    for document in documents:
        for job in session.exec(
            select(IngestionJob).where(IngestionJob.document_id == document.id)
        ).all():
            session.delete(job)
    session.commit()

    for document in documents:
        session.delete(document)
    session.commit()

    for case_id in case_ids:
        for assignment in session.exec(
            select(Assignment).where(Assignment.case_id == case_id)
        ).all():
            session.delete(assignment)
    session.commit()

    for case in cases:
        session.delete(case)
    session.commit()

    for email in emails:
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            continue
        # Sessions hold an FK to the user; a live login would otherwise block
        # the delete with a constraint error rather than a useful message.
        for row in session.exec(select(SessionModel).where(SessionModel.user_id == user.id)).all():
            session.delete(row)
        for row in session.exec(select(Assignment).where(Assignment.user_id == user.id)).all():
            session.delete(row)
        session.delete(user)
    session.commit()

    if not quiet:
        print(f"removed {len(cases)} seeded case(s) and {len(emails)} demo user(s)")


def _make_user(session: Session, email: str, name: str, role: Role) -> User:
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password(PASSWORD),
        role=role,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_case(session: Session, title: str, status: CaseStatus) -> Case:
    case = Case(title=title, description=SEED_MARKER, status=status)
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def _add_document(
    session: Session, case: Case, filename: str, uploaded_by: int, chunks: list[dict]
) -> int:
    document = Document(
        case_id=case.id,
        filename=filename,
        # No file on disk: these chunks were never uploaded, so pointing at a
        # path that does not exist would be a lie a later re-ingestion would
        # trip over. The name says so out loud.
        file_path=f"seeded-no-file-{filename}",
        uploaded_by=uploaded_by,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    texts = [c["text"] for c in chunks]
    print(f"embedding {len(texts)} chunks for {filename}")
    vectors = _embed_all(texts)

    for sequence, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            DocumentChunk(
                case_id=case.id,
                document_id=document.id,
                page_number=1,
                sequence=sequence,
                text=chunk["text"],
                embedding=vector,
            )
        )
    session.commit()
    return len(texts)


def seed(session: Session, limit: int | None) -> None:
    if _seeded_cases(session):
        raise SystemExit(
            "demo data is already present — re-run with --reset to rebuild it, "
            "or --cleanup to remove it"
        )

    corpus = _load_corpus(limit)

    users = {role.value: _make_user(session, email, name, role) for email, name, role in DEMO_USERS}
    partner, attorney, paralegal = users["partner"], users["attorney"], users["paralegal"]

    labor_case = _make_case(session, LABOR_CASE_TITLE, CaseStatus.IN_PROGRESS)
    contract_case = _make_case(session, CONTRACT_CASE_TITLE, CaseStatus.DRAFT)

    # The partner gets no assignment row on purpose — case:read:any means they
    # can already read both, and a partner with zero assignments is precisely
    # the case the security tests exist to cover.
    session.add(Assignment(case_id=labor_case.id, user_id=attorney.id))
    session.add(Assignment(case_id=contract_case.id, user_id=paralegal.id))
    session.commit()

    labor_chunks = _add_document(session, labor_case, "hrsd_labor_law.pdf", partner.id, corpus)
    contract_chunks = _add_document(
        session, contract_case, "employment_contract.pdf", partner.id, CONTRACT_CHUNKS
    )

    print()
    print(f"Seeded {labor_chunks + contract_chunks} chunks across 2 cases.")
    print()
    print(f"  Sign in at http://localhost:3000/login — password for all three: {PASSWORD}")
    for email, _, role in DEMO_USERS:
        print(f"    {email:28} {role.value}")
    print()
    print(f"  Case {labor_case.id}: {LABOR_CASE_TITLE}  (attorney assigned)")
    print(f"  Case {contract_case.id}: {CONTRACT_CASE_TITLE}  (paralegal assigned)")
    print()
    for which, question in DEMO_QUESTIONS:
        print(f"  Ask ({which}): {question}")
    print()
    print("  The authorization moment: ask the attorney's account the contract")
    print("  question. It answers for the partner and refuses for the attorney.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reset", action="store_true", help="remove existing demo data, then seed")
    parser.add_argument("--cleanup", action="store_true", help="remove demo data and stop")
    parser.add_argument(
        "--limit", type=int, default=None, help="seed only the first N corpus chunks"
    )
    args = parser.parse_args()

    url = os.environ["DATABASE_URL"]
    # Say which database out loud. backend/.env is loaded above, so an unset
    # DATABASE_URL does not fail — it quietly falls through to whatever .env
    # names, which is the dev database. That is the right default for the
    # common case and the wrong one to discover after running --cleanup.
    print(f"database: {_describe(url)}\n")

    engine = create_engine(url)
    with Session(engine) as session:
        if args.cleanup:
            cleanup(session)
            return
        if args.reset:
            cleanup(session, quiet=True)
        seed(session, args.limit)


if __name__ == "__main__":
    main()
