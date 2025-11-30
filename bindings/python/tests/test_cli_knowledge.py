"""Tests for gspio knowledge command."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gaspatchio_core.api.models import SearchResponse, SearchResult
from gaspatchio_core.cli import app

runner = CliRunner()


class TestKnowledgeCommand:
    """Tests for the knowledge command."""

    def test_knowledge_help_shows_usage_guidance(self):
        """Knowledge --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "Search the actuarial knowledge base" in result.output
        assert "IMPORTANT: Prefer search results" in result.output
        assert "Use sparingly" in result.output

    def test_knowledge_help_shows_examples(self):
        """Knowledge --help shows example queries."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "IFRS" in result.output or "actuarial" in result.output.lower()

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_returns_json(self, mock_client_class):
        """Knowledge command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = SearchResponse(
            results=[
                SearchResult(
                    text="The Contractual Service Margin (CSM)...",
                    source="IFRS17_Guide.pdf",
                    content_type="regulatory",
                    score=0.88,
                    page=42,
                )
            ],
            query="IFRS 17 CSM",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "IFRS 17 CSM"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "results" in output
        assert output["results"][0]["page"] == 42

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_answer_flag(self, mock_client_class):
        """Knowledge --answer returns generated answer."""
        from gaspatchio_core.api.models import AnswerResponse, SourceReference

        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = AnswerResponse(
            answer="The risk adjustment under IFRS 17 is...",
            sources=[SourceReference(source="ifrs17.pdf", score=0.9)],
            query="what is risk adjustment",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "what is risk adjustment", "-a"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_api_error_exits_nonzero(self, mock_client_class):
        """Knowledge exits with error code on API failure."""
        from gaspatchio_core.api.client import APIConnectionError

        mock_client = MagicMock()
        mock_client.search_knowledge.side_effect = APIConnectionError("API unavailable")
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "test"])

        assert result.exit_code == 1
        assert "API unavailable" in result.output
