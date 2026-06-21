import logging
import time

import anthropic

from .base import LLMProvider, CompletionResult

logger = logging.getLogger(__name__)

_COST_RATES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5":   (15.0,  75.0),
    "claude-sonnet-4-6": (3.0,   15.0),
    "claude-haiku-4-5":  (0.80,  4.0),
}
_DEFAULT_RATE = (15.0, 75.0)

# When a 429 is hit, wait this many seconds before retrying
_RATE_LIMIT_WAIT = 65  # slightly over 1 minute to let the token bucket refill
_MAX_RETRIES = 5


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-opus-4-5"):
        # max_retries=0 — we handle retries ourselves so we can wait long enough
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self._model = model
        self._input_rate, self._output_rate = _COST_RATES.get(model, _DEFAULT_RATE)

    @property
    def provider_name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(
        self,
        system: str,
        source_text: str,
        user_prompt: str,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"<source_material>\n{source_text}\n</source_material>",
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ]

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                full_text = ""
                with self._client.messages.stream(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=messages,
                ) as stream:
                    for chunk in stream.text_stream:
                        full_text += chunk
                    usage = stream.get_final_message().usage

                tokens_in = usage.input_tokens
                tokens_out = usage.output_tokens
                cost = (tokens_in * self._input_rate + tokens_out * self._output_rate) / 1_000_000
                return CompletionResult(
                    text=full_text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                )

            except anthropic.RateLimitError as exc:
                if attempt == _MAX_RETRIES:
                    raise
                wait = _RATE_LIMIT_WAIT * attempt  # 65s, 130s, 195s ...
                logger.warning(
                    "Rate limit hit (attempt %d/%d). Waiting %ds before retry. Error: %s",
                    attempt, _MAX_RETRIES, wait, exc,
                )
                time.sleep(wait)

            except anthropic.APIStatusError as exc:
                # 529 overloaded — shorter wait then retry
                if exc.status_code == 529 and attempt < _MAX_RETRIES:
                    wait = 30 * attempt
                    logger.warning("API overloaded, waiting %ds (attempt %d/%d)", wait, attempt, _MAX_RETRIES)
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("Exhausted all retries")  # never reached
