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

    def test_shared_long_preamble_with_distinct_substance_survives(self) -> None:
        """A long shared preamble must not mask distinct substance after it.

        Dropping either hit would silently lose relevant material — the
        observed boilerplate preambles run ~3.5 KB.
        """
        substance_a = "Term insurance uses the NPR methodology per VM-20 3.B.4. " * 20
        substance_b = "Universal life secondary guarantees follow VM-20 3.C. " * 20
        hits = [
            _knowledge(PREAMBLE + substance_a, "VM-20"),
            _knowledge(PREAMBLE + substance_b, "VM-20 _2"),
        ]

        kept, dropped = dedupe_results(hits)

        assert dropped == 0
        assert len(kept) == 2


class TestDedupeShortTails:
    """A dominant preamble must not swallow short distinct substance."""

    def test_short_distinct_tails_survive_a_dominant_preamble(self) -> None:
        """Even one distinct load-bearing sentence after boilerplate is content.

        The global ratio stays above threshold when the tails are short
        relative to the preamble, so the judgement must fall on what
        remains after the shared prefix.
        """
        tail_a = (
            "Term insurance uses the net premium reserve methodology defined "
            "in VM-20 section 3.B.4 for the base reserve calculation. " * 3
        )
        tail_b = (
            "Universal life secondary guarantees are valued under the VM-20 "
            "section 3.C stochastic exclusion ratio test instead. " * 3
        )
        hits = [
            _knowledge(PREAMBLE + tail_a, "VM-20"),
            _knowledge(PREAMBLE + tail_b, "VM-20 _2"),
        ]

        kept, dropped = dedupe_results(hits)

        assert dropped == 0
        assert len(kept) == 2

    def test_trivial_trailing_variation_still_collapses(self) -> None:
        """A few words of tail difference is noise, not substance."""
        hits = [
            _knowledge(PREAMBLE, "VM-20"),
            _knowledge(PREAMBLE + " Revised August 2026.", "VM-20 _2"),
        ]

        kept, dropped = dedupe_results(hits)

        assert dropped == 1
        assert len(kept) == 1


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

    def test_window_anchors_on_the_word_not_a_substring(self) -> None:
        """A substring hit inside a longer word must not steal the anchor.

        "rate" inside "generated" loses to the real "rate table" later in
        the document.
        """
        decoy = "Charts were generated from integrated data sources. " * 40
        text = decoy + "The rate table maps attained age to mortality. " + decoy
        result = _doc(text)

        out = truncate_result(result, query="rate table", max_chars=300)

        assert out.truncated is True
        assert "rate table maps attained age" in out.text

    def test_exact_word_outranks_an_earlier_inflected_form(self) -> None:
        """An earlier prefix match ("rates") must not hide a later exact word.

        Exact-word occurrences win the anchor; inflected forms are the
        second tier, substrings the third.
        """
        decoy = "Corporate bond rates moved with the yield curve. " * 40
        text = decoy + "The rate table maps attained age to mortality. " + decoy
        result = _doc(text)

        out = truncate_result(result, query="rate", max_chars=300)

        assert out.truncated is True
        assert "rate table maps attained age" in out.text

    def test_inflected_form_still_anchors_when_no_exact_word_exists(self) -> None:
        """With only "rates" present, the inflected form beats mid-word noise.

        "generated" appears earlier than "rates", but a boundary-prefix
        match outranks a bare substring.
        """
        decoy = "Charts were generated from integrated data sources. " * 40
        text = decoy + "Mortality rates vary by attained age and duration. " + decoy
        result = _doc(text)

        out = truncate_result(result, query="rate", max_chars=300)

        assert out.truncated is True
        assert "Mortality rates vary" in out.text

    def test_substring_match_is_still_better_than_the_head(self) -> None:
        """A bare substring hit still beats windowing the head blindly.

        With no word-boundary occurrence at all ('flow' appears only inside
        'cashflow'), the substring position is the best available anchor.
        """
        filler = "Background prose about projection mechanics. " * 40
        text = filler + "The cashflow vector nets premiums against claims. " + filler
        result = _doc(text)

        out = truncate_result(result, query="flow", max_chars=300)

        assert out.truncated is True
        assert "cashflow vector" in out.text
