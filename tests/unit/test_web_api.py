"""Unit tests for the web dashboard FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hestia.web.api import create_web_app


class TestCreateWebApp:
    """Tests for create_web_app factory."""

    def test_returns_fastapi_instance(self) -> None:
        app = create_web_app()
        assert app.title == "Hestia Dashboard"
        assert app.docs_url is None
        assert app.redoc_url is None

    def test_serves_index_html(self) -> None:
        app = create_web_app()
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "Hello Hestia" in response.text
