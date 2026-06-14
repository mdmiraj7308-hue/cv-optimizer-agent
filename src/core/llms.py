from langchain_openai import ChatOpenAI
from src.config.settings import settings


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
