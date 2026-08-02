"""The instruction sheet handed to the language model (LEG-63).

This is the only real control over what the model does. It is kept in its own
module, as ordinary code, so it can be read in review and tested directly —
the ticket requires the template itself to be covered by tests, not just the
service that uses it.

Passages are numbered rather than labelled with filenames. The model can only
ever cite a number that was given to it, so a citation pointing at a passage
that was never sent is detectable rather than plausible.
"""

NOT_FOUND = "NOT_FOUND"
"""Exact reply meaning "the passages do not answer this question".

A fixed token rather than a sentence: prose varies between models, changes with
temperature, and would have to be matched in Arabic as well as English. One
exact string is checkable.
"""


INSTRUCTIONS = """\
Answer the question using ONLY the numbered passages below.

Rules:
- Use only what the passages say. Never use knowledge from your training.
- Do not guess, infer beyond what is written, or add background context.
- After every claim, cite the passage it came from, like this: [2].
- Cite only passage numbers that appear below.
- If the passages do not contain the answer, reply with exactly {not_found} \
and nothing else.
- Answer in the same language as the question.
- Keep the answer under four sentences.
"""


def build_prompt(question: str, passages: list[str]) -> str:
    """Assemble the exact text sent to the model.

    Refuses to build a prompt with no passages. A model asked a question with
    nothing to read has only its training to answer from, which is the single
    outcome this ticket exists to prevent — so that call is made impossible
    here rather than left to each caller to remember.
    """
    if not passages:
        raise ValueError("Cannot build a prompt with no passages")

    numbered = "\n\n".join(f"[{number}] {text}" for number, text in enumerate(passages, start=1))

    return (
        f"{INSTRUCTIONS.format(not_found=NOT_FOUND)}\n"
        f"Passages:\n{numbered}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )
