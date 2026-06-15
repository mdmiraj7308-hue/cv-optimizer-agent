import logging

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

from src.config.settings import settings

logger = logging.getLogger(__name__)


class TokenUsageLogger(BaseCallbackHandler):
    """Log OpenAI token usage per LLM call for cost observability.

    Attach via `chain.invoke(..., config={"callbacks": [TokenUsageLogger("optimizer")]})`.
    """

    def __init__(self, label: str) -> None:
        self.label = label

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: ANN001
        usage: dict = {}
        try:
            if getattr(response, "llm_output", None):
                usage = response.llm_output.get("token_usage") or {}
            if not usage and response.generations:
                message = getattr(response.generations[0][0], "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
        except Exception:  # pragma: no cover - logging must never break a run
            usage = {}

        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        logger.info(
            "[tokens] agent=%s model=%s prompt=%s completion=%s total=%s",
            self.label,
            settings.openai_model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )


def get_llm(temperature: float = 0.2, max_tokens: int | None = None) -> ChatOpenAI:
    """Return a ChatOpenAI instance configured from settings."""
    kwargs: dict = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
