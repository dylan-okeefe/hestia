"""Unit tests for InferenceClient."""

import pytest

from hestia.core.inference import InferenceClient


class TestInferenceClient:
    """Tests for the inference client."""

    def test_empty_model_name_raises(self):
        """Creating an InferenceClient with an empty model_name raises ValueError."""
        with pytest.raises(ValueError, match="inference.model_name is required"):
            InferenceClient("http://localhost:8001", "")

    def test_valid_model_name_succeeds(self):
        """Creating an InferenceClient with a valid model_name succeeds."""
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        assert client.base_url == "http://localhost:8001"
        assert client.model_name == "my-model.gguf"
