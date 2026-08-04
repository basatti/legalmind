"""The instruction sheet the reason node hands to the model (LEG-78).

Own module, same reason as routing_prompt.py: the wording is the real control
over the decision, so it should be readable in review and testable on its own
rather than buried in the node.

Tokens rather than sentences, for the same reason as routing_prompt.py -
questions arrive in Arabic and English (the corpus is Saudi labour law), and
two exact strings are checkable in either language regardless of how a model
phrases its reasoning around them.
"""

CONTINUE = "CONTINUE"
"""Exact reply meaning "another retrieval pass is needed before this can be
answered"."""

DONE = "DONE"
"""Exact reply meaning "enough has been retrieved to attempt an answer"."""


INSTRUCTIONS = """\
You are working through a multi-step question by retrieving passages in \
several passes. Decide whether another retrieval pass is needed, or whether \
enough has been found to answer.

Reply on the first line with exactly {continue_token} or {done_token} and \
nothing else on that line.

If you reply {continue_token}, give the next sub-question to search for on \
the second line - a single, specific lookup, not a restatement of the \
original question.

Judge only whether the retrieved passages so far are enough to answer the \
original question. Do not attempt the answer itself.
"""


def build_reasoning_prompt(
    question: str, reasoning: list[str], retrieved_summaries: list[str]
) -> str:
    """Assemble the exact text sent to the model for one reasoning pass.

    reasoning carries what earlier passes concluded, and retrieved_summaries
    is what has been found so far - both grow across passes, so the model is
    judging the accumulated picture, not just the latest retrieval.
    """
    lines = [INSTRUCTIONS.format(continue_token=CONTINUE, done_token=DONE)]
    lines.append(f"Original question: {question}\n")

    if reasoning:
        lines.append("Reasoning so far:")
        for i, step in enumerate(reasoning, start=1):
            lines.append(f"{i}. {step}")
        lines.append("")

    if retrieved_summaries:
        lines.append("Retrieved so far:")
        for summary in retrieved_summaries:
            lines.append(f"- {summary}")
        lines.append("")
    else:
        lines.append("Nothing retrieved yet.\n")

    lines.append("Decision:")
    return "\n".join(lines)
