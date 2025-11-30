# ABOUTME: Tests for gspio docs command.
# ABOUTME: Tests CLI argument parsing, JSON output, and error handling.
"""Tests for gspio docs command."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gaspatchio_core.api.models import SearchResponse, SearchResult
from gaspatchio_core.cli import app

runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs command."""

    def test_docs_help_shows_usage_guidance(self):
        """Docs --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "Search Gaspatchio framework documentation" in result.output
        assert "IMPORTANT: Prefer search results" in result.output
        assert "Use sparingly" in result.output  # On --answer flag

    def test_docs_help_shows_examples(self):
        """Docs --help shows example queries."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert (
            "cumulative survival" in result.output.lower()
            or "example" in result.output.lower()
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_returns_json(self, mock_client_class):
        """Docs command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = SearchResponse(
            results=[
                SearchResult(
                    text="cumulative_survival() calculates...",
                    source="projection.py",
                    content_type="code_example",
                    score=0.92,
                )
            ],
            query="cumulative survival",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "cumulative survival"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "results" in output
        assert output["query"] == "cumulative survival"

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_limit_option(self, mock_client_class):
        """Docs -n flag sets result limit."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = SearchResponse(
            results=[],
            query="test",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "test", "-n", "10"])

        assert result.exit_code == 0
        mock_client.search_docs.assert_called_once_with("test", answer=False, limit=10)

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_answer_flag(self, mock_client_class):
        """Docs --answer returns generated answer."""
        from gaspatchio_core.api.models import AnswerResponse, SourceReference

        mock_client = MagicMock()
        mock_client.search_docs.return_value = AnswerResponse(
            answer="To calculate cumulative survival, use...",
            sources=[SourceReference(source="projection.py", score=0.9)],
            query="how to calculate survival",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "how to calculate survival", "--answer"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output
        mock_client.search_docs.assert_called_once_with(
            "how to calculate survival", answer=True, limit=5
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_api_error_exits_nonzero(self, mock_client_class):
        """Docs exits with error code on API failure."""
        from gaspatchio_core.api.client import APIConnectionError

        mock_client = MagicMock()
        mock_client.search_docs.side_effect = APIConnectionError("API unavailable")
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "test"])

        assert result.exit_code == 1
        assert "API unavailable" in result.output
