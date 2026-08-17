# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for client-side search-result post-processing (#120/#130).
# ABOUTME: Guards near-duplicate collapse and per-result snippet truncation.
"""Tests for docs/knowledge result dedup and truncation."""

from __future__ import annotations

from gaspatchio_core.api.models import DocResult, KnowledgeResult
from gaspatchio_core.api.postprocess import dedupe_results, truncate_result

PREAMBLE = (
    "The purpose of this practice note is to provide actuaries with background "
    "on the valuation manual and its requirements for principle-based reserves. "
) * 30


def _doc(text: str) -> DocResult:
    return DocResult(
        text=text,
        score=0.9,
        content_type="overview",
        source_file="doc.md",
        object_path=None,
        has_code=False,
    )


def _knowledge(text: str, doc_id: str) -> KnowledgeResult:
    return KnowledgeResult(
        text=text,
        score=0.9,
        doc_id=doc_id,
        tags=[],
        jurisdiction=None,
        doc_type=None,
    )


class TestDedupe:
    """Near-duplicate collapse keeps the first copy and counts the drops."""

    def test_near_identical_chunks_collapse(self) -> None:
        """The #120 case: the same preamble ingested under two doc_ids."""
        hits = [
            _knowledge(PREAMBLE, "VM-20"),
            _knowledge(PREAMBLE + " Trailing variation.", "VM-20 _2"),
            _knowledge(
                "Term Insurance uses the NPR methodology per VM-20 3.B.4.", "VM-20"
            ),
        ]

        kept, dropped = dedupe_results(hits)

        assert dropped == 1
        assert len(kept) == 2
        assert kept[0].doc_id == "VM-20"
        assert "NPR methodology" in kept[1].text

    def test_distinct_chunks_survive(self) -> None:
        """Genuinely different prose is never collapsed."""
        hits = [
            _doc("cumulative_survival() computes the running product of tpx."),
            _doc("previous_period() shifts a list column back one period."),
        ]

        kept, dropped = dedupe_results(hits)

        assert dropped == 0
        assert len(kept) == 2

    def test_first_occurrence_wins(self) -> None:
        """The higher-ranked copy is the one kept."""
        hits = [_doc(PREAMBLE), _doc(PREAMBLE)]

        kept, dropped = dedupe_results(hits)

        assert dropped == 1
        assert kept[0].text == PREAMBLE


class TestTruncate:
    """Snippet windowing around the first query match."""

    def test_short_text_untouched(self) -> None:
        """Texts within budget pass through byte-identical."""
        result = _doc("short text")

        out = truncate_result(result, query="short", max_chars=100)

        assert out.text == "short text"
        assert out.truncated is False
        assert out.full_chars is None

    def test_zero_budget_means_unlimited(self) -> None:
        """max_chars=0 disables truncation entirely."""
        result = _doc(PREAMBLE)

        out = truncate_result(result, query="valuation", max_chars=0)

        assert out.text == PREAMBLE
        assert out.truncated is False

    def test_long_text_windows_around_the_match(self) -> None:
        """The kept window contains the matching sentence, not just the head."""
        sentence = " The load-bearing sentence names cumulative_survival here. "
        text = PREAMBLE + sentence + PREAMBLE
        result = _doc(text)

        out = truncate_result(result, query="cumulative survival", max_chars=400)

        assert out.truncated is True
        assert out.full_chars == len(text)
        assert "cumulative_survival" in out.text
        # The marker names the escape hatch.
        assert "--full" in out.text
        # Budget respected (marker and ellipses excluded from the window budget).
        assert len(out.text) < 400 + 200

    def test_no_match_keeps_the_head(self) -> None:
        """With no query-term match the head of the text is kept."""
        result = _doc(PREAMBLE)

        out = truncate_result(result, query="zzzznotfound", max_chars=300)

        assert out.truncated is True
        assert out.text.startswith(PREAMBLE[:40])
        assert "--full" in out.text
