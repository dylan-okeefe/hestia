"""Hestia error types."""

from enum import StrEnum


class EmailConfigError(ValueError):
    """Raised when email configuration is invalid."""


class HestiaConfigError(ValueError):
    """Raised when the Hestia configuration is invalid or incomplete."""

    pass


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


class ExperimentalFeatureError(HestiaError):
    """Raised when an experimental feature is used without opt-in."""

    pass


class MissingExtraError(HestiaError):
    """Raised when an optional dependency extra is not installed."""

    pass


class WebSearchError(HestiaError):
    """Raised when the configured web-search provider fails."""

    pass


class MaxIterationsError(HestiaError):
    """Orchestrator turn exceeded the configured max iteration count.

    Raised by the engine state machine when a turn loops past
    ``HestiaConfig.max_iterations`` without reaching DONE or FAILED via
    any other path. Carries the iteration count for telemetry.
    """

    def __init__(self, max_iterations: int, iterations: int | None = None) -> None:
        self.max_iterations = max_iterations
        self.iterations = iterations if iterations is not None else max_iterations
        super().__init__(f"Max iterations ({max_iterations}) exceeded")


class PolicyFailureError(HestiaError):
    """Retry policy returned FAIL — orchestrator may not retry.

    Raised by the engine when :meth:`PolicyEngine.retry_after_error`
    returns ``RetryAction.FAIL``. Separates "policy said stop" from
    "the underlying error", which remains available as ``__cause__``.
    """

    pass


class ToolExecutionError(HestiaError):
    """A tool handler raised an unexpected exception during dispatch.

    Wraps the underlying exception so the orchestrator can classify the
    failure by ``inner_type`` without string-matching the message.
    ``ToolRegistry.call`` catches broad ``Exception`` (but not
    ``BaseException`` — asyncio ``CancelledError`` and keyboard interrupts
    still propagate) and raises this in the tool-result JSON.
    """

    def __init__(self, tool_name: str, inner: BaseException) -> None:
        self.tool_name = tool_name
        self.inner = inner
        self.inner_type = type(inner).__name__
        super().__init__(f"{tool_name}: {self.inner_type}: {inner}")


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
        MaxIterationsError: (FailureClass.MAX_ITERATIONS, "medium"),
        WebSearchError: (FailureClass.TOOL_ERROR, "medium"),
        ToolExecutionError: (FailureClass.TOOL_ERROR, "medium"),
    }

    for exc_type, (fc, sev) in mapping.items():
        if isinstance(exc, exc_type):
            return fc, sev

    return FailureClass.UNKNOWN, "medium"
