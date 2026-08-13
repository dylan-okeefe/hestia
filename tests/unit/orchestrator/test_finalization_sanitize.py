"""Tests for user-facing error message sanitization in TurnFinalization."""

from hestia.errors import (
    InferenceConnectionError,
    InferenceServerError,
    InferenceTimeoutError,
)
from hestia.orchestrator.finalization import sanitize_user_error


class TestSanitizeUserError:
    def test_connection_error_surfaces_real_cause(self) -> None:
        """Transport failures show the operator the actual low-level reason."""
        err = InferenceConnectionError(
            "POST /v1/chat/completions",
            "RemoteProtocolError: peer closed connection without sending "
            "complete message body (incomplete chunked read)",
        )
        msg = sanitize_user_error(err)
        assert "peer closed connection" in msg
        assert "inference server" in msg

    def test_connection_error_is_inference_server_error(self) -> None:
        """Existing InferenceServerError handlers catch the subclass."""
        err = InferenceConnectionError("POST /tokenize", "ConnectError: refused")
        assert isinstance(err, InferenceServerError)

    def test_timeout_still_has_own_message(self) -> None:
        msg = sanitize_user_error(InferenceTimeoutError("timed out"))
        assert msg == "The AI is taking longer than expected. Try again in a moment."

    def test_unknown_error_still_sanitized(self) -> None:
        """Unclassified internals (SQL, paths, traces) stay hidden from users."""
        msg = sanitize_user_error(KeyError("message_id"))
        assert msg == "Something went wrong. The operator has been notified."
