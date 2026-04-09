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
