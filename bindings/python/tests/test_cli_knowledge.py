# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gspio knowledge command.
# ABOUTME: Tests CLI argument parsing, JSON output, and error handling.
"""Tests for gspio knowledge command."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gaspatchio_core.api.client import APIConnectionError
from gaspatchio_core.api.models import (
    KnowledgeAnswerResponse,
    KnowledgeResult,
    KnowledgeSearchResponse,
)
from gaspatchio_core.cli import app

runner = CliRunner()


class TestKnowledgeCommand:
    """Tests for the knowledge command."""

    def test_knowledge_help_shows_usage_guidance(self):
        """Knowledge --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "Search actuarial knowledge base" in result.output
        assert "Use filters to search by jurisdiction" in result.output

    def test_knowledge_help_shows_filter_options(self):
        """Knowledge --help shows filter options for LLM discoverability."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        # Check for short options or key terms (robust against terminal width)
        assert "-T" in result.output or "tag" in result.output
        assert "-j" in result.output or "jurisdiction" in result.output
        assert "-d" in result.output or "doc-type" in result.output
        assert "-r" in result.output or "retrieval" in result.output
        assert "IFRS17" in result.output
        assert "SolvencyII" in result.output

    def test_knowledge_help_shows_examples(self):
        """Knowledge --help shows example queries."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "gspio knowledge" in result.output

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_returns_json(self, mock_client_class):
        """Knowledge command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[
                KnowledgeResult(
                    text="The Contractual Service Margin (CSM)...",
                    score=0.88,
                    doc_id="ifrs17-guide",
                    tags=["IFRS17", "CSM"],
                    jurisdiction="EU",
                    doc_type="regulatory",
                    page_number=42,
                )
            ],
            query="IFRS 17 CSM",
            count=1,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=55.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "IFRS 17 CSM"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "results" in output
        assert output["results"][0]["page_number"] == 42

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_limit_option(self, mock_client_class):
        """Knowledge -n flag sets result limit."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "test", "-n", "15"])

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "test",
            limit=15,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=None,
            jurisdiction=None,
            doc_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_tag_filter(self, mock_client_class):
        """Knowledge -T flag filters by tag."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "CSM", "-T", "IFRS17"])

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "CSM",
            limit=10,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=["IFRS17"],
            jurisdiction=None,
            doc_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_jurisdiction_filter(self, mock_client_class):
        """Knowledge -j flag filters by jurisdiction."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "technical provisions", "-j", "EU"])

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "technical provisions",
            limit=10,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=None,
            jurisdiction="EU",
            doc_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_doc_type_filter(self, mock_client_class):
        """Knowledge -d flag filters by document type."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "risk adjustment", "-d", "standard"])

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "risk adjustment",
            limit=10,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=None,
            jurisdiction=None,
            doc_type="standard",
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_retrieval_mode(self, mock_client_class):
        """Knowledge -r flag sets retrieval mode."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="summaries",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            app, ["knowledge", "IFRS 17 overview", "-r", "summaries"]
        )

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "IFRS 17 overview",
            limit=10,
            search_type="hybrid",
            retrieval_mode="summaries",
            tags=None,
            jurisdiction=None,
            doc_type=None,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_combined_filters(self, mock_client_class):
        """Knowledge command accepts multiple filters together."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[],
            query="test",
            count=0,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            app,
            [
                "knowledge",
                "discount rates",
                "-T",
                "IFRS17",
                "-j",
                "EU",
                "-d",
                "standard",
                "-n",
                "20",
            ],
        )

        assert result.exit_code == 0
        mock_client.search_knowledge.assert_called_once_with(
            "discount rates",
            limit=20,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=["IFRS17"],
            jurisdiction="EU",
            doc_type="standard",
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_answer_flag(self, mock_client_class):
        """Knowledge --answer returns generated answer."""
        mock_client = MagicMock()
        mock_client.answer_knowledge.return_value = KnowledgeAnswerResponse(
            answer="The risk adjustment under IFRS 17 is...",
            sources=[
                KnowledgeResult(
                    text="Risk adjustment definition",
                    score=0.9,
                    doc_id="ifrs17",
                    tags=["IFRS17"],
                    jurisdiction="EU",
                    doc_type="standard",
                )
            ],
            query="what is risk adjustment",
            model="claude-3-sonnet",
            tokens_used=150,
            took_ms=1200.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "what is risk adjustment", "-a"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output
        mock_client.answer_knowledge.assert_called_once_with(
            "what is risk adjustment",
            limit=10,
            search_type="hybrid",
            retrieval_mode="chunks",
            tags=None,
            jurisdiction=None,
            doc_type=None,
        )

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


class TestKnowledgePayloadTrimming:
    """#120: near-duplicate collapse and per-hit truncation by default."""

    @staticmethod
    def _hit(text: str, doc_id: str) -> KnowledgeResult:
        return KnowledgeResult(
            text=text,
            score=0.9,
            doc_id=doc_id,
            tags=[],
            jurisdiction=None,
            doc_type=None,
        )

    def _mock_response(self, hits: list[KnowledgeResult]) -> KnowledgeSearchResponse:
        return KnowledgeSearchResponse(
            results=hits,
            query="net premium reserve",
            count=len(hits),
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_near_duplicate_hits_collapse_by_default(self, mock_client_class):
        """The observed #120 case: one preamble ingested under two doc_ids."""
        preamble = "The purpose of this practice note is to provide background. " * 60
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = self._mock_response(
            [
                self._hit(preamble, "VM-20"),
                self._hit(preamble + " Minor trailing variation.", "VM-20 _2"),
                self._hit("Term Insurance uses the NPR methodology.", "VM-20"),
            ]
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "net premium reserve"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["deduplicated"] == 1
        assert len(output["results"]) == 2

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_long_hit_truncates_with_marker(self, mock_client_class):
        """A long hit is windowed and carries the --full marker."""
        long_text = "Reserve methodology background prose. " * 200
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = self._mock_response(
            [self._hit(long_text, "VM-20")]
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "reserve methodology"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        hit = output["results"][0]
        assert hit["truncated"] is True
        assert hit["full_chars"] == len(long_text)
        assert "--full" in hit["text"]
        assert len(hit["text"]) < len(long_text)

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_full_flag_returns_everything(self, mock_client_class):
        """--full skips both dedup and truncation."""
        long_text = "Reserve methodology background prose. " * 200
        preamble_hits = [
            self._hit(long_text, "VM-20"),
            self._hit(long_text, "VM-20 _2"),
        ]
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = self._mock_response(preamble_hits)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "reserve methodology", "--full"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["deduplicated"] == 0
        assert len(output["results"]) == 2
        assert output["results"][0]["text"] == long_text
        assert output["results"][0]["truncated"] is False


class TestKnowledgeAnswerFallback:
    """#119: a dead answer backend degrades to search, mirroring docs."""

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_answer_server_error_falls_back_to_search(self, mock_client_class):
        """A 5xx from /answer yields search results with the situation named."""
        mock_client = MagicMock()
        mock_client.answer_knowledge.side_effect = APIConnectionError(
            'API error: 500 - {"detail":"Internal server error."}',
            status_code=500,
        )
        mock_client.search_knowledge.return_value = KnowledgeSearchResponse(
            results=[
                KnowledgeResult(
                    text="The net premium reserve is defined in VM-20 3.B.",
                    score=0.9,
                    doc_id="VM-20",
                    tags=[],
                    jurisdiction=None,
                    doc_type=None,
                )
            ],
            query="net premium reserve",
            count=1,
            search_type="hybrid",
            retrieval_mode="chunks",
            took_ms=10.0,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "net premium reserve", "--answer"])

        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["results"]
        assert "--answer" in (output.get("note") or "")
        assert "Search still works" in result.stderr
        mock_client.search_knowledge.assert_called_once()

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_no_search_promise_when_fallback_search_also_fails(self, mock_client_class):
        """The notice must not announce search results that never arrive."""
        mock_client = MagicMock()
        mock_client.answer_knowledge.side_effect = APIConnectionError(
            'API error: 500 - {"detail":"Internal server error."}',
            status_code=500,
        )
        mock_client.search_knowledge.side_effect = APIConnectionError(
            "API error: 500 - search is down too",
            status_code=500,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "net premium reserve", "--answer"])

        assert result.exit_code == 1
        assert "Search still works" not in result.stderr
