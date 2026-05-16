class MultiAgentRAGError(Exception):
    """Base exception for all project errors."""


class LLMError(MultiAgentRAGError):
    """Raised when an LLM call fails after all retries."""


class RetrievalError(MultiAgentRAGError):
    """Raised when retrieval from vector store or SQL fails."""


class ValidationError(MultiAgentRAGError):
    """Raised when the validation agent detects a critical failure."""


class IngestionError(MultiAgentRAGError):
    """Raised when document loading or chunking fails."""


class CacheError(MultiAgentRAGError):
    """Raised on non-critical cache failures — callers should degrade gracefully."""
