"""The language model interface (LEG-63).

Text in, text out — the narrowest possible description of a language model.

Code that needs text generated depends on this interface, never on a specific
provider. A provider implements it and is chosen in one place, so swapping one
for another leaves RagService, the prompt and the tests untouched.
"""

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """A provider could not produce a reply at all.

    Distinct from a reply that is unusable — a network failure or an exhausted
    quota is a temporary condition worth retrying or reporting as such, while a
    model that answered badly is a different problem with a different response.
    """


class LLMProvider(ABC):
    """Anything that can turn a prompt into a reply."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the model's reply to prompt.

        Takes only the prompt. Settings that change how the model behaves —
        which model, temperature, token limits — belong in an implementation's
        constructor, not in this signature. A grounded answer needs those fixed
        and low-variance for every question; letting each caller pass its own
        would make the product's behaviour depend on the call site rather than
        on a decision made once.
        """
