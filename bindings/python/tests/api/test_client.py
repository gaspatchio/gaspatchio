# ABOUTME: Tests for the knowledge API client.
# ABOUTME: Covers HTTP requests, error handling, and response parsing.
"""Tests for the knowledge API client."""

from unittest.mock import MagicMock, patch

import pytest

from gaspatchio_core.api.client import APIConnectionError, KnowledgeAPIClient
from gaspatchio_core.api.models import (
    DocsAnswerResponse,
    DocsSearchResponse,
    KnowledgeAnswerResponse,
    KnowledgeSearchResponse,
)


class TestKnowledgeAPIClient:
    """Tests for KnowledgeAPIClient."""

    def test_client_uses_env_var_for_base_url(self, monkeypatch):
        """Client reads GASPATCHIO_API_URL from environment."""
        monkeypatch.setenv("GASPATCHIO_API_URL", "https://custom.api.com")
        client = KnowledgeAPIClient()
        assert client.base_url == "https://custom.api.com"

    def test_client_uses_default_url_when_env_not_set(self, monkeypatch):
        """Client uses default URL when env var not set."""
        monkeypatch.delenv("GASPATCHIO_API_URL", raising=False)
        client = KnowledgeAPIClient()
        assert client.base_url == "https://gaspatchio-mix.fly.dev"

    @patch("httpx.Client.post")
    def test_search_docs_returns_docs_search_response(self, mock_post):
        """search_docs returns DocsSearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "test",
                    "source_file": "file.py",
                    "content_type": "code",
                    "score": 0.9,
                    "object_path": None,
                    "has_code": True,
                }
            ],
            "query": "test",
            "count": 1,
            "search_type": "hybrid",
            "took_ms": 42.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        result = client.search_docs("test query")

        assert isinstance(result, DocsSearchResponse)
        assert len(result.results) == 1

    @patch("httpx.Client.post")
    def test_answer_docs_returns_docs_answer_response(self, mock_post):
        """answer_docs returns DocsAnswerResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "The answer is...",
            "sources": [
                {
                    "text": "source text",
                    "source_file": "file.py",
                    "content_type": "code",
                    "score": 0.9,
                    "object_path": None,
                    "has_code": True,
                }
            ],
            "query": "test",
            "model": "claude-3-sonnet",
            "tokens_used": 100,
            "took_ms": 1000.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        result = client.answer_docs("test query")

        assert isinstance(result, DocsAnswerResponse)
        assert result.answer == "The answer is..."

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_connection_error(self, mock_post):
        """search_docs raises APIConnectionError on network failure."""
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = KnowledgeAPIClient()
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API unavailable" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_knowledge_returns_knowledge_search_response(self, mock_post):
        """search_knowledge returns KnowledgeSearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "IFRS 17...",
                    "score": 0.88,
                    "doc_id": "ifrs17",
                    "tags": ["IFRS17"],
                    "jurisdiction": "EU",
                    "doc_type": "standard",
                    "page_number": 42,
                }
            ],
            "query": "CSM",
            "count": 1,
            "search_type": "hybrid",
            "retrieval_mode": "chunks",
            "took_ms": 55.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        result = client.search_knowledge("CSM")

        assert isinstance(result, KnowledgeSearchResponse)
        assert result.results[0].page_number == 42

    @patch("httpx.Client.post")
    def test_answer_knowledge_returns_knowledge_answer_response(self, mock_post):
        """answer_knowledge returns KnowledgeAnswerResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "The Contractual Service Margin (CSM) is...",
            "sources": [
                {
                    "text": "CSM definition",
                    "score": 0.9,
                    "doc_id": "ifrs17",
                    "tags": ["IFRS17", "CSM"],
                    "jurisdiction": "EU",
                    "doc_type": "standard",
                }
            ],
            "query": "CSM",
            "model": "claude-3-sonnet",
            "tokens_used": 150,
            "took_ms": 1200.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        result = client.answer_knowledge("CSM")

        assert isinstance(result, KnowledgeAnswerResponse)
        assert result.answer == "The Contractual Service Margin (CSM) is..."

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_timeout(self, mock_post):
        """search_docs raises APIConnectionError on timeout."""
        import httpx

        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        client = KnowledgeAPIClient()
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "timed out" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_http_422_validation_error(self, mock_post):
        """search_docs raises APIConnectionError on HTTP 422 validation error."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "detail": [
                {
                    "loc": ["body", "query"],
                    "msg": "Field required",
                    "type": "missing",
                }
            ]
        }
        mock_response.text = "Unprocessable Entity"
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API validation error" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_http_500_error(self, mock_post):
        """search_docs raises APIConnectionError on HTTP 500."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("Not JSON")
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API error: 500" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_with_content_type_filter(self, mock_post):
        """search_docs passes content_type filter to API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [],
            "query": "test",
            "count": 0,
            "search_type": "hybrid",
            "took_ms": 10.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        client.search_docs("test", content_type=["code", "docstring"])

        # Verify the request payload
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["content_type"] == ["code", "docstring"]

    @patch("httpx.Client.post")
    def test_search_knowledge_with_filters(self, mock_post):
        """search_knowledge passes filters to API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [],
            "query": "test",
            "count": 0,
            "search_type": "hybrid",
            "retrieval_mode": "chunks",
            "took_ms": 10.0,
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient()
        client.search_knowledge(
            "IFRS 17",
            tags=["IFRS17"],
            jurisdiction="EU",
            doc_type="standard",
        )

        # Verify the request payload
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["tags"] == ["IFRS17"]
        assert payload["jurisdiction"] == "EU"
        assert payload["doc_type"] == "standard"
