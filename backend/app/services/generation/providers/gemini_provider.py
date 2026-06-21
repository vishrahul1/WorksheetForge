import logging

from google import genai
from google.genai.types import GenerateContentConfig

from .base import LLMProvider, CompletionResult

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (google-genai SDK uses v1 endpoint — all models available)
_COST_RATES: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash-lite":  (0.075, 0.30),
    "gemini-2.0-flash":       (0.10,  0.40),
    "gemini-2.5-flash":       (0.15,  0.60),
}
_DEFAULT_RATE = (0.075, 0.30)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-lite"):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._input_rate, self._output_rate = _COST_RATES.get(model, _DEFAULT_RATE)

    @property
    def provider_name(self) -> str:
        return f"gemini/{self._model_name}"

    def complete(
        self,
        system: str,
        source_text: str,
        user_prompt: str,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        prompt = (
            f"<source_material>\n{source_text}\n</source_material>\n\n"
            f"{user_prompt}"
        )

        config = GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        )

        full_text = ""
        last_chunk = None

        for chunk in self._client.models.generate_content_stream(
            model=self._model_name,
            contents=prompt,
            config=config,
        ):
            last_chunk = chunk
            try:
                if chunk.text:
                    full_text += chunk.text
            except Exception:
                # Chunk has no text — check finish reason
                finish_reason = None
                try:
                    finish_reason = chunk.candidates[0].finish_reason
                except Exception:
                    pass
                logger.warning(
                    "Gemini chunk skipped (finish_reason=%s)", finish_reason
                )

        if not full_text.strip():
            raise ValueError(
                f"Gemini ({self._model_name}) returned an empty response. "
                "Content may have been blocked by safety filters."
            )

        # Usage metadata is on the last chunk
        tokens_in = 0
        tokens_out = 0
        if last_chunk and hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
            tokens_in = last_chunk.usage_metadata.prompt_token_count or 0
            tokens_out = last_chunk.usage_metadata.candidates_token_count or 0

        cost = (tokens_in * self._input_rate + tokens_out * self._output_rate) / 1_000_000

        return CompletionResult(
            text=full_text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
