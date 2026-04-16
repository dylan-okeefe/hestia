"""Hestia error types."""

from enum import StrEnum


class HestiaError(Exception):
    """Base class for all Hestia errors."""

    pass


class PlatformError(HestiaError):
    """Base class for platform adapter errors."""

    pass


class InferenceServerError(HestiaError):
    """llama-server returned a non-200 response."""

    pass


class InferenceTimeoutError(HestiaError):
    """llama-server request timed out."""

    pass


class ContextTooLargeError(HestiaError):
    """Context exceeds budget even after compression."""

    pass


class PersistenceError(HestiaError):
    """Database operation failed."""

    pass


class ArtifactError(HestiaError):
    """Artifact storage error."""

    pass


class ArtifactNotFoundError(ArtifactError):
    """Artifact handle does not exist."""

    pass


class ArtifactExpiredError(ArtifactError):
    """Artifact has expired."""

    pass


class IllegalTransitionError(HestiaError):
    """Attempted an illegal state machine transition."""

    pass


class EmptyResponseError(HestiaError):
    """Model returned empty content and no tool calls."""

    pass


class FailureClass(StrEnum):
    """Classification of failure types for analytics and policy."""

    CONTEXT_OVERFLOW = "context_overflow"
    EMPTY_RESPONSE = "empty_response"
    INFERENCE_TIMEOUT = "inference_timeout"
    INFERENCE_ERROR = "inference_error"
    TOOL_ERROR = "tool_error"
    PERSISTENCE_ERROR = "persistence_error"
    ILLEGAL_TRANSITION = "illegal_transition"
    MAX_ITERATIONS = "max_iterations"
    UNKNOWN = "unknown"


def classify_error(exc: Exception) -> tuple[FailureClass, str]:
    """Classify an exception into a FailureClass and severity.

    Args:
        exc: The exception to classify

    Returns:
        Tuple of (FailureClass, severity) where severity is "low", "medium", or "high"
    """
    mapping: dict[type, tuple[FailureClass, str]] = {
        ContextTooLargeError: (FailureClass.CONTEXT_OVERFLOW, "medium"),
        EmptyResponseError: (FailureClass.EMPTY_RESPONSE, "low"),
        InferenceTimeoutError: (FailureClass.INFERENCE_TIMEOUT, "medium"),
        InferenceServerError: (FailureClass.INFERENCE_ERROR, "high"),
        PersistenceError: (FailureClass.PERSISTENCE_ERROR, "high"),
        IllegalTransitionError: (FailureClass.ILLEGAL_TRANSITION, "high"),
    }

    for exc_type, (fc, sev) in mapping.items():
        if isinstance(exc, exc_type):
            return fc, sev

    error_msg = str(exc).lower()
    if "max iterations" in error_msg:
        return FailureClass.MAX_ITERATIONS, "medium"

    return FailureClass.UNKNOWN, "medium"
