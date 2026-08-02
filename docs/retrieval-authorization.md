# Retrieval authorization — why it's built this way (LEG-66)

Covers the reasoning behind `RetrievalService.retrieve()` and
`DocumentChunkRepository.search()` (LEG-62): why filtering happens inside the
query, top-k as a bounded max-heap problem, cosine vs. dot-product, and what
pgvector's index trades off.

## 1. Why filtering must happen inside the query, not after

`DocumentChunkRepository.search()` does this in one statement:

```python
statement = select(DocumentChunk).order_by(
    DocumentChunk.embedding.cosine_distance(query_vector)
)
if isinstance(within, TheseCases):
    if not within.case_ids:
        return []
    statement = statement.where(col(DocumentChunk.case_id).in_(list(within.case_ids)))
return list(session.exec(statement.limit(limit)).all())
```

The `WHERE case_id IN (...)` runs *before* `ORDER BY ... LIMIT k`. That
ordering is the entire security property this code exists to guarantee.

The alternative — rank the whole table by similarity, take the top k, then
throw away any that fail an authorization check — is a real vulnerability
class, not just a style preference. Search-then-filter has two independent
failure modes:

- **Silent under-fetching.** If all k of the top matches happen to belong to
  cases the user isn't authorized for, post-filtering leaves zero results even
  though authorized, relevant chunks exist further down the ranking — the
  user gets a wrong "no answer" instead of a real one.
- **A missed filter is a leak, not a wrong answer.** If a later refactor
  removes or forgets the post-hoc filter step, the failure mode isn't "slower"
  or "less relevant" — it's a chunk from a case the user was never assigned to
  showing up as a cited source in a grounded legal answer. Filtering inside
  the query means there is no code path that can produce a chunk outside the
  authorized set at all; there's nothing to forget to call.

This is a set-intersection problem: the authorized set (`AuthorizedCases`,
LEG-64) and the candidate set (all chunks) get intersected *before* ranking,
not after. `AllCases` vs. `TheseCases(frozenset())` (unscoped vs.
authorized-for-nothing) are different types specifically so this branch can't
be skipped by accident — see `foundation/authorization.py`.

## 2. Top-k as a bounded max-heap problem

"Give me the k closest vectors out of N" is the classic partial-sort problem.
Two ways to solve it:

- **Full sort:** order all N candidates by distance, take the first k.
  O(N log N).
- **Bounded max-heap:** keep a heap of size k. For each candidate, compare
  against the heap's current maximum (the worst of the current top-k); if the
  candidate is closer, evict the max and insert the candidate. O(N log k).

When k is small and fixed (here, k=5) and N is large, O(N log k) beats
O(N log N) — you never need the full ordering of everything that *isn't* in
the top k, only enough structure to know the current worst-of-the-best.

This code never implements that heap directly — `ORDER BY ... LIMIT k` hands
the problem to Postgres/pgvector, which already solves it this way internally
(see §4). The reason to know the underlying algorithm anyway: it's what
explains *why* an index can answer "top k" without fully sorting the table,
and it's the same shape of problem that shows up anywhere "closest k of N"
appears — nearest-neighbor search, event scheduling, leaderboards.

## 3. Cosine vs. dot-product similarity, and why normalization matters

Two vectors' similarity can be measured by:

- **Dot product:** `a · b = Σ aᵢbᵢ`. Sensitive to both the angle *and* the
  magnitude of each vector.
- **Cosine similarity:** `(a · b) / (|a| |b|)`. Only the angle between the
  vectors matters; magnitude is divided out.

`BgeM3EmbeddingProvider` (LEG-58) explicitly L2-normalizes every vector to
unit length before storing it (`embeddings/bge_m3.py`). Once every vector has
length 1, `|a| |b| = 1`, and cosine similarity *becomes* the dot product —
they're the same operation on normalized vectors. That's why the query can
use pgvector's `cosine_distance` operator without a separate normalization
step at query time: the normalization already happened at embedding time, for
every chunk and every question alike.

Why normalize at all, rather than just use raw dot product? Embedding
magnitude tends to correlate with things that have nothing to do with
relevance — text length, word frequency, how "generic" a passage is not how
well it matches the question. A long chunk can have a larger-magnitude vector
than a short one purely from having more content, and dot product would rank
it higher for that reason alone. Normalizing forces every comparison to be
about *direction* (meaning) only, so ranking reflects semantic closeness, not
an artifact of chunk length.

## 4. What pgvector's HNSW/IVF index trades off vs. a brute-force scan

The `search()` query above has no index hint — as written, it performs a
brute-force scan: compute the distance from the query vector to *every* row's
embedding, then sort. That's exact (it always finds the true top k) and
O(N) per query. Fine at the corpus sizes this project runs at now; it stops
being fine as the table grows into the millions of rows, since every query
touches every row.

pgvector supports two approximate-nearest-neighbor index types that trade
exactness for speed:

- **IVF (`ivfflat`)**: partitions vectors into clusters at index-build time.
  A query only scans the clusters nearest the query vector, not the whole
  table. Cheaper to build than HNSW, but recall (how often it finds the true
  top k, not an approximation) depends heavily on picking the right number of
  clusters, and it needs representative data present before the index is
  built to place clusters well.
- **HNSW**: builds a multi-layer graph where each vector links to its nearest
  neighbors; search walks the graph from a coarse layer down to a fine one.
  Slower and more memory-hungry to build than IVF, but typically better
  recall at a given speed, and — unlike IVF — doesn't need the data
  distribution known in advance to build a good index.

Both give up the brute-force scan's guarantee of exact results in exchange
for sub-linear query time: instead of "check every row," they check a
bounded, much smaller neighborhood likely to contain the true top-k. The
practical tradeoff is recall vs. speed vs. build cost, and which one wins
depends on corpus size and how much an occasional near-miss in the top-5
actually costs — for a document search feature, a rare 5th-best-instead-of-
4th-best result is usually a fine price for not scanning the whole table on
every question.

This project uses a brute-force scan today because the corpus is small enough
that it's already fast. Adding an index is a schema/migration change to make
later, not a change to `search()`'s query logic — the `WHERE` before `ORDER
BY ... LIMIT` shape stays exactly the same either way.
