from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompletionResult:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float = 0.0


class LLMProvider(ABC):
    """Common interface for all LLM backends."""

    @abstractmethod
    def complete(
        self,
        system: str,
        source_text: str,
        user_prompt: str,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        """Send a completion request and return the full result."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name, e.g. 'anthropic/claude-opus-4-5'."""
