"""Tests for user-facing error message sanitization in TurnFinalization."""

from hestia.errors import (
    ContextTooLargeError,
    HestiaError,
    InferenceBusyError,
    InferenceConnectionError,
    InferenceServerError,
    InferenceTimeoutError,
    MaxIterationsError,
    PolicyFailureError,
    ToolExecutionError,
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

    def test_busy_still_has_own_message(self) -> None:
        msg = sanitize_user_error(InferenceBusyError("at capacity"))
        assert (
            msg
            == "I'm busy working on another request right now — please try again in a moment."
        )

    def test_context_too_large_still_has_own_message(self) -> None:
        msg = sanitize_user_error(ContextTooLargeError("ctx overflow"))
        assert "conversation has grown very long" in msg

    def test_tool_execution_names_the_tool(self) -> None:
        msg = sanitize_user_error(ToolExecutionError("browser", RuntimeError("boom")))
        assert "browser" in msg

    def test_max_iterations_still_has_own_message(self) -> None:
        msg = sanitize_user_error(MaxIterationsError("too many"))
        assert msg == "I'm having trouble responding right now. Please try again."

    def test_policy_failure_passes_message_through(self) -> None:
        msg = sanitize_user_error(PolicyFailureError("policy said stop"))
        assert msg == "policy said stop"

    def test_hestia_error_passes_message_through(self) -> None:
        msg = sanitize_user_error(HestiaError("custom failure"))
        assert msg == "custom failure"

    def test_unknown_error_surfaces_class_and_message(self) -> None:
        """Unclassified errors name the exception class and message so the
        user (and operator) can tell failures apart."""
        msg = sanitize_user_error(KeyError("message_id"))
        assert msg == (
            "Unexpected error: KeyError: 'message_id'. "
            "The operator has been notified."
        )

    def test_unknown_error_without_message_shows_class_only(self) -> None:
        msg = sanitize_user_error(RuntimeError())
        assert msg == "Unexpected error: RuntimeError. The operator has been notified."

    def test_unknown_error_detail_is_capped(self) -> None:
        msg = sanitize_user_error(ValueError("x" * 500))
        detail = msg.removeprefix("Unexpected error: ValueError: ")
        body = detail.removesuffix(". The operator has been notified.")
        assert body.endswith("...")
        assert len(body) <= 200 + len("...")

    def test_unknown_error_strips_filesystem_paths(self) -> None:
        err = OSError("cannot open /home/operator/hestia/slots/turn.jsonl")
        msg = sanitize_user_error(err)
        assert "/home/operator" not in msg
        assert "[path]" in msg

    def test_unknown_error_strips_urls(self) -> None:
        err = ValueError("fetch http://internal-host:8080/v1/keys?token=secret failed")
        msg = sanitize_user_error(err)
        assert "internal-host" not in msg
        assert "secret" not in msg
        assert "[url]" in msg

    def test_unknown_error_is_single_line(self) -> None:
        err = RuntimeError("line one\nline two\tand a tab")
        msg = sanitize_user_error(err)
        assert "\n" not in msg
        assert "\t" not in msg
