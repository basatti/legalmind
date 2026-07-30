# Handoff notes — document ingestion (LEG-57 / LEG-13)

## What's done

- **PDF parser** (`backend/src/parsers/pdf_parser.py`) — reads Arabic PDFs correctly (handles a broken-font bug some PDFs have). Tested.
- **Chunkers** (`backend/src/chunkers/`) — splits a document into overlapping pieces ready for embedding. Two versions:
  - `FixedSizeChunker` — for plain PDFs (page by page). Built by Yazan.
  - `CaseChunker` — for structured cases (splits by section: facts / reasoning / verdict, or by law article). Never merges two different sections or two different cases together.

This satisfies LEG-57's requirements. Ready to commit.

## What data we have (in `backend/data/corpus/`, not in git — too big)

| Source | What it is | Size |
|---|---|---|
| ALARB | Commercial court cases | 13,341 cases → 65,394 chunks |
| Labor Law | The full Saudi Labor Law, article by article | 249 articles → 254 chunks |

Both are clean, verified real data — no corrupted text, no fake data.

## What's missing

**General court, personal-status (custody/divorce/alimony), and criminal case text.** We looked hard for this (a government portal, several public datasets, a paper that has the exact right data but no download link, and a government statistics platform) and none of them had downloadable full case text for these areas — only case counts/metadata, or blocked by anti-bot protection.

This is a known gap, not an oversight. Whoever works on this next can decide if it's worth chasing further (e.g. emailing the paper's authors) or just moving forward without it for now.

## For LEG-58 (embeddings)

The two data files above are ready to be embedded as-is. Each chunk already has the info needed (which case it's from, which section, in order) — no extra prep required.

## Sharing the data

The corpus files in `backend/data/corpus/` are gitignored (too large for a normal commit) and aren't in this push. They need to be shared separately — a GitHub Release is the planned way to do that, not yet done.
