from __future__ import annotations

import logging
from typing import AsyncIterator, List

import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import APIError, RateLimitError

from app.core.config import settings
from app.core.exceptions import LLMError
from app.core.tracing import observability_status

# Use langfuse drop-in wrapper when Langfuse is configured — gives automatic
# token tracking, latency, and prompt/completion logging on every LLM call.
if observability_status()["langfuse_enabled"]:
    from langfuse.openai import AsyncAzureOpenAI, AsyncOpenAI
    import logging
    logging.getLogger(__name__).info("LLMClient using langfuse.openai wrapper (tracing enabled)")
else:
    from openai import AsyncAzureOpenAI, AsyncOpenAI

logger = logging.getLogger(__name__)

# tiktoken encoding for token counting (cl100k_base covers GPT-4 models)
_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


class LLMClient:
    """Single entry point for all LLM and embedding calls.

    Automatically uses Azure OpenAI when credentials are present,
    falls back to direct OpenAI otherwise.
    """

    def __init__(self) -> None:
        if settings.use_azure:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
            self._gpt4o = settings.azure_deployment_gpt4o
            self._gpt4o_mini = settings.azure_deployment_gpt4o_mini
            self._embedding_model = settings.azure_deployment_embedding
            logger.info("LLMClient initialised with Azure OpenAI")
        else:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._gpt4o = "gpt-4o"
            self._gpt4o_mini = "gpt-4o-mini"
            self._embedding_model = "text-embedding-3-large"
            logger.info("LLMClient initialised with direct OpenAI")

    @property
    def strong_model(self) -> str:
        """GPT-4o — use for Reasoning and Validation agents."""
        return self._gpt4o

    @property
    def fast_model(self) -> str:
        """Lightweight model — use for Intent, Grader, Summariser agents."""
        return self._gpt4o_mini

    @retry(
        retry=retry_if_exception_type((APIError, RateLimitError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        """Send a chat completion request and return the response text."""
        model = model or self._gpt4o
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except (APIError, RateLimitError):
            raise
        except Exception as e:
            raise LLMError(f"Unexpected LLM error: {e}") from e

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream tokens one chunk at a time."""
        model = model or self._gpt4o
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as e:
            raise LLMError(f"Streaming error: {e}") from e

    @retry(
        retry=retry_if_exception_type((APIError, RateLimitError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings for a list of strings."""
        try:
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except (APIError, RateLimitError):
            raise
        except Exception as e:
            raise LLMError(f"Embedding error: {e}") from e


# Module-level singleton — import this everywhere
llm_client = LLMClient()
