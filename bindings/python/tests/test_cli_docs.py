# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gspio docs command.
# ABOUTME: Tests CLI argument parsing, JSON output, and error handling.
"""Tests for gspio docs command."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gaspatchio_core.api.models import (
    DocResult,
    DocsAnswerResponse,
    DocsSearchResponse,
)
from gaspatchio_core.cli import app

runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs command."""

    def test_docs_help_shows_usage_guidance(self):
        """Docs --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "Search Gaspatchio framework documentation" in result.output
        # The help text mentions filtering and multiple searches
        assert "filters" in result.output
        assert "multiple searches" in result.output

    def test_docs_help_shows_filter_options(self):
        """Docs --help shows filter options for LLM discoverability."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        # Check for short options (more robust against terminal width variations)
        # or the default values which indicate the options exist
        assert "-s" in result.output or "hybrid" in result.output  # search-type
        assert "-t" in result.output or "content-type" in result.output
        assert "code_example" in result.output
        assert "hybrid" in result.output

    def test_docs_help_shows_examples(self):
        """Docs --help shows example queries."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "gspio docs" in result.output

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_returns_json(self, mock_client_class):
        """Docs command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = DocsSearchResponse(
            results=[
                DocResult(
                    text="cumulative_survival() calculates...",
                    source_file="projection.py",
                    content_type="code_example",
                    score=0.92,
                    object_path=None,
                    has_code=True,
                )
            ],
            query="cumulative survival",
            count=1,
            search_type="hybrid",
            took_ms=42.0,
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
        mock_client.search_docs.return_value = DocsSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "test", "-n", "15"])

        assert result.exit_code == 0
        mock_client.search_docs.assert_called_once_with(
            "test",
            limit=15,
            search_type="hybrid",
            content_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_search_type_option(self, mock_client_class):
        """Docs -s flag sets search type."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = DocsSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="keyword",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "previous_period", "-s", "keyword"])

        assert result.exit_code == 0
        mock_client.search_docs.assert_called_once_with(
            "previous_period",
            limit=10,
            search_type="keyword",
            content_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_content_type_filter(self, mock_client_class):
        """Docs -t flag filters by content type."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = DocsSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            app, ["docs", "cumulative survival", "-t", "code_example"]
        )

        assert result.exit_code == 0
        mock_client.search_docs.assert_called_once_with(
            "cumulative survival",
            limit=10,
            search_type="hybrid",
            content_type=["code_example"],
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_answer_flag(self, mock_client_class):
        """Docs --answer returns generated answer."""
        mock_client = MagicMock()
        mock_client.answer_docs.return_value = DocsAnswerResponse(
            answer="To calculate cumulative survival, use...",
            sources=[
                DocResult(
                    text="source text",
                    source_file="projection.py",
                    content_type="code",
                    score=0.9,
                    object_path=None,
                    has_code=True,
                )
            ],
            query="how to calculate survival",
            model="claude-3-sonnet",
            tokens_used=100,
            took_ms=1000.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "how to calculate survival", "--answer"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output
        mock_client.answer_docs.assert_called_once_with(
            "how to calculate survival",
            limit=10,
            search_type="hybrid",
            content_type=None,
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
