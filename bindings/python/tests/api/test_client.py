# ABOUTME: Tests for the knowledge API client.
# ABOUTME: Covers HTTP requests, error handling, and response parsing.
"""Tests for the knowledge API client."""

from unittest.mock import MagicMock, patch

import pytest

from gaspatchio_core.api.client import APIConnectionError, KnowledgeAPIClient
from gaspatchio_core.api.models import AnswerResponse, SearchResponse


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
        assert client.base_url == "https://api.gaspatchio.com"

    def test_client_includes_version_in_requests(self):
        """Client includes gaspatchio version in all requests."""
        client = KnowledgeAPIClient(version="0.4.2")
        assert client.version == "0.4.2"

    @patch("httpx.Client.post")
    def test_search_docs_returns_search_response(self, mock_post):
        """search_docs returns SearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "test",
                    "source": "file.py",
                    "content_type": "code",
                    "score": 0.9,
                }
            ],
            "query": "test",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_docs("test query")

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 1

    @patch("httpx.Client.post")
    def test_search_docs_with_answer_returns_answer_response(self, mock_post):
        """search_docs with answer=True returns AnswerResponse."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "The answer is...",
            "sources": [{"source": "file.py", "score": 0.9}],
            "query": "test",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_docs("test query", answer=True)

        assert isinstance(result, AnswerResponse)
        assert result.answer == "The answer is..."

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_connection_error(self, mock_post):
        """search_docs raises APIConnectionError on network failure."""
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API unavailable" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_knowledge_returns_search_response(self, mock_post):
        """search_knowledge returns SearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "IFRS 17...",
                    "source": "ifrs17.pdf",
                    "content_type": "regulatory",
                    "score": 0.88,
                    "page": 42,
                }
            ],
            "query": "CSM",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_knowledge("CSM")

        assert isinstance(result, SearchResponse)
        assert result.results[0].page == 42

    @patch("httpx.Client.post")
    def test_search_knowledge_with_answer_returns_answer_response(self, mock_post):
        """search_knowledge with answer=True returns AnswerResponse."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "The Contractual Service Margin (CSM) is...",
            "sources": [{"source": "ifrs17.pdf", "score": 0.9}],
            "query": "CSM",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_knowledge("CSM", answer=True)

        assert isinstance(result, AnswerResponse)
        assert result.answer == "The Contractual Service Margin (CSM) is..."

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_timeout(self, mock_post):
        """search_docs raises APIConnectionError on timeout."""
        import httpx

        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "timed out" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_http_400_with_json_error(self, mock_post):
        """search_docs raises APIConnectionError on HTTP 400 with APIError JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "bad_request",
            "status": 400,
            "message": "Invalid query parameter",
        }
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API error (400)" in str(exc_info.value)
        assert "Invalid query parameter" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_http_500_with_json_error(self, mock_post):
        """search_docs raises APIConnectionError on HTTP 500 with APIError JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "error": "internal_server_error",
            "status": 500,
            "message": "Internal server error",
        }
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API error (500)" in str(exc_info.value)
        assert "Internal server error" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_http_error_with_non_json_response(self, mock_post):
        """search_docs raises error on HTTP error with non-JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.side_effect = Exception("Not JSON")
        mock_response.text = "Service temporarily unavailable"
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API error: 503" in str(exc_info.value)
        assert "Service temporarily unavailable" in str(exc_info.value)
