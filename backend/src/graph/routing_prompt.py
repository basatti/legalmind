"""The instruction sheet the router hands to the model (LEG-76).

Its own module, as ordinary code, for the same reason as `services.prompt`: the
wording is the only real control over the classification, so it should be
readable in review and testable on its own rather than buried in a node.

The two answers are fixed tokens rather than sentences. Prose varies between
models, drifts with temperature, and would have to be recognised in Arabic as
well as English — the corpus is Saudi labour law, so questions arrive in both.
Two exact strings are checkable in any language.
"""

SINGLE_SHOT = "SINGLE_SHOT"
"""Exact reply meaning "one search of the documents can answer this"."""

MULTI_STEP = "MULTI_STEP"
"""Exact reply meaning "this needs several lookups, or one lookup decides the
next"."""


INSTRUCTIONS = """\
Classify the question below into exactly one category.

{single_shot} - one thing to look up. A single search of the documents finds \
the answer.
{multi_step} - more than one thing to look up, and they must be combined; or \
the answer to one part decides what to look up next.

Judge only the shape of the question. Do not try to answer it, and do not \
consider whether the documents happen to contain the answer.

Reply with exactly {single_shot} or {multi_step} and nothing else.
"""


def build_routing_prompt(question: str) -> str:
    """Assemble the exact text sent to the model to classify one question.

    Deliberately does not include any passages. Routing happens before
    retrieval, so there is nothing to show the model yet — and asking it to
    judge shape rather than content is what keeps this call cheap: one short
    prompt, no documents, against a question of a few words.
    """
    return (
        f"{INSTRUCTIONS.format(single_shot=SINGLE_SHOT, multi_step=MULTI_STEP)}\n"
        f"Question: {question}\n\n"
        f"Classification:"
    )
