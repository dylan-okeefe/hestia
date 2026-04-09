"""Hestia error types."""


class HestiaError(Exception):
    """Base class for all Hestia errors."""

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
