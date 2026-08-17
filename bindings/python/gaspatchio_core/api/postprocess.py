# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Client-side post-processing for docs/knowledge search results.
# ABOUTME: Collapses near-duplicate hits and windows long texts around the match.
"""Post-processing for `gspio docs` / `gspio knowledge` search results.

The retrieval surface is a CLI chosen for token efficiency, so per-hit payload
is part of its contract (#120/#130): near-identical chunks ingested under
different doc_ids waste every token they repeat, and a full source document
inlined for one matching section costs ~4k tokens per lookup. Both fixes are
applied here, after the API client returns and before the JSON is printed —
nothing is hidden: dropped duplicates are counted on the response, truncated
texts carry a marker naming ``--full``.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TypeVar

from gaspatchio_core.api.models import DocResult, KnowledgeResult

_ResultT = TypeVar("_ResultT", DocResult, KnowledgeResult)

# Near-duplicate detection compares normalised text prefixes; 0.9 collapses
# re-ingested copies of the same source (which differ in whitespace or a
# trailing variation) while distinct prose stays comfortably below it.
_DEDUPE_THRESHOLD = 0.9
_DEDUPE_PROBE_CHARS = 2000

# Query terms shorter than this are too common to anchor a snippet window.
_MIN_TERM_CHARS = 4


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, and cap length for cheap comparison."""
    return " ".join(text.lower().split())[:_DEDUPE_PROBE_CHARS]


def dedupe_results(
    results: list[_ResultT],
    threshold: float = _DEDUPE_THRESHOLD,
) -> tuple[list[_ResultT], int]:
    """Collapse near-identical hits, keeping the first (highest-ranked) copy.

    Returns the surviving results in their original order and the number of
    hits dropped as near-duplicates.
    """
    kept: list[_ResultT] = []
    kept_norms: list[str] = []
    dropped = 0
    for result in results:
        norm = _normalise(result.text)
        is_duplicate = False
        for seen in kept_norms:
            matcher = SequenceMatcher(None, norm, seen)
            if (
                matcher.real_quick_ratio() >= threshold
                and matcher.quick_ratio() >= threshold
                and matcher.ratio() >= threshold
            ):
                is_duplicate = True
                break
        if is_duplicate:
            dropped += 1
            continue
        kept.append(result)
        kept_norms.append(norm)
    return kept, dropped


def _first_match_position(text: str, query: str) -> int | None:
    """Position of the earliest query-term occurrence in text, if any."""
    terms = [t for t in re.split(r"\W+", query) if len(t) >= _MIN_TERM_CHARS]
    lowered = text.lower()
    positions = [
        pos for pos in (lowered.find(term.lower()) for term in terms) if pos >= 0
    ]
    return min(positions) if positions else None


def truncate_result(result: _ResultT, query: str, max_chars: int) -> _ResultT:
    """Window a long result text around the first query match.

    Texts within ``max_chars`` (or with ``max_chars=0``, meaning unlimited)
    pass through untouched. Longer texts keep a window of ``max_chars``
    characters positioned around the earliest query-term match (the head when
    nothing matches), with a trailing marker naming ``--full`` so the complete
    chunk is one flag away.
    """
    text = result.text
    if max_chars <= 0 or len(text) <= max_chars:
        return result

    match_pos = _first_match_position(text, query)
    start = 0 if match_pos is None else max(0, match_pos - max_chars // 4)
    start = min(start, len(text) - max_chars)
    window = text[start : start + max_chars]

    prefix = "… " if start > 0 else ""
    suffix = " …" if start + max_chars < len(text) else ""
    marker = (
        f"\n[showing {len(window):,} of {len(text):,} chars"
        f"{' around the first match' if match_pos is not None else ''};"
        f" pass --full for the complete text]"
    )
    return result.model_copy(
        update={
            "text": f"{prefix}{window}{suffix}{marker}",
            "truncated": True,
            "full_chars": len(text),
        },
    )
