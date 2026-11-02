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
from typing import Final

from gaspatchio.api.client import knowledge_filters
from gaspatchio.api.models import (
    DocResult,
    DocsSearchResponse,
    KnowledgeResult,
    KnowledgeSearchResponse,
)

# What a docs search and a knowledge search answer with: printed alike. A plain
# union rather than a ``type`` statement, so that it is the union at run time as
# well, which is what the stub check compares it with.
SearchResponse = DocsSearchResponse | KnowledgeSearchResponse

# Near-duplicate detection compares the FULL normalised texts; 0.9 collapses
# re-ingested copies of the same source (which differ in whitespace or a
# trailing variation) while distinct prose stays comfortably below it. The
# comparison must never be capped to a prefix: the observed boilerplate
# preambles run ~3.5 KB, so a prefix probe would collapse two chunks whose
# substantive content only diverges after the shared preamble.
_DEDUPE_THRESHOLD = 0.9

# Query terms shorter than this are too common to anchor a snippet window.
_MIN_TERM_CHARS = 4

# Ingestion noise has a specific shape: one text is exactly the other plus a
# trailing stamp — a strict extension. Only that shape may collapse without
# comparing tails, and only when the addendum is stamp-sized (a few words,
# not a sentence). Divergent continuations — both texts carrying their own
# words past the shared prefix — are content however short, and when the
# heuristic cannot tell, it keeps both: a visible near-duplicate is cheap,
# silently dropped content is not.
_STAMP_CHARS = 40


def _normalise(text: str) -> str:
    """Lowercase and collapse whitespace for comparison."""
    return " ".join(text.lower().split())


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the longest common prefix of two strings."""
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i
    return limit


def _is_near_duplicate(a: str, b: str, threshold: float) -> bool:
    """Whether two normalised texts carry the same content.

    The global ratio is a fast gate: below threshold the texts are
    clearly distinct. Above it, the shared prefix is stripped and the
    remainders judged on their own. A strict extension (one remainder
    empty) with a stamp-sized addendum is ingestion noise; anything else
    is duplicate only if the remainders are themselves similar.
    """
    matcher = SequenceMatcher(None, a, b)
    if not (
        matcher.real_quick_ratio() >= threshold
        and matcher.quick_ratio() >= threshold
        and matcher.ratio() >= threshold
    ):
        return False

    prefix_len = _common_prefix_len(a, b)
    rest_a = a[prefix_len:]
    rest_b = b[prefix_len:]
    if min(len(rest_a), len(rest_b)) == 0:
        return max(len(rest_a), len(rest_b)) <= _STAMP_CHARS
    return SequenceMatcher(None, rest_a, rest_b).ratio() >= threshold


def dedupe_results[R: (DocResult, KnowledgeResult)](
    results: list[R],
    threshold: float = _DEDUPE_THRESHOLD,
) -> tuple[list[R], int]:
    """Collapse near-identical hits, keeping the first (highest-ranked) copy.

    Returns the surviving results in their original order and the number of
    hits dropped as near-duplicates.
    """
    kept: list[R] = []
    kept_norms: list[str] = []
    dropped = 0
    for result in results:
        norm = _normalise(result.text)
        is_duplicate = any(
            _is_near_duplicate(norm, seen, threshold) for seen in kept_norms
        )
        if is_duplicate:
            dropped += 1
            continue
        kept.append(result)
        kept_norms.append(norm)
    return kept, dropped


def _first_match_position(text: str, query: str) -> int | None:
    """Position of the earliest query-term occurrence in text, if any.

    Three anchor tiers, strongest non-empty tier wins: an exact word
    ("rate" as its own word), then a boundary prefix ("rate" starting
    "rates" — inflected forms are usually the match the reader wants),
    then a bare substring ("flow" inside "cashflow" — still better than
    windowing the head blindly). Without the tiers a mid-word hit like
    "rate" inside "generated", or an earlier "rates", would steal the
    window from the passage the query actually names.
    """
    terms = [t for t in re.split(r"\W+", query) if len(t) >= _MIN_TERM_CHARS]
    lowered = text.lower()

    exact_positions = []
    prefix_positions = []
    substring_positions = []
    for term in terms:
        escaped = re.escape(term.lower())
        match = re.search(rf"\b{escaped}\b", lowered)
        if match:
            exact_positions.append(match.start())
        match = re.search(rf"\b{escaped}", lowered)
        if match:
            prefix_positions.append(match.start())
        pos = lowered.find(term.lower())
        if pos >= 0:
            substring_positions.append(pos)

    for positions in (exact_positions, prefix_positions, substring_positions):
        if positions:
            return min(positions)
    return None


def truncate_result[R: (DocResult, KnowledgeResult)](
    result: R, query: str, max_chars: int
) -> R:
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


def trimmed(search: SearchResponse, query: str, max_chars: int) -> SearchResponse:
    """Return a search with near-duplicate results dropped and long texts windowed.

    What ``gspio docs`` and ``gspio knowledge`` print unless asked for
    ``--full``: :func:`dedupe_results` over the results, then
    :func:`truncate_result` over each one kept, with the count of those
    dropped carried on the response so that nothing is hidden.

    Args:
        search: The response the API client returned, of either search.
        query: The query the search was for, which each window centres on.
        max_chars: How long a result's text may run before it is windowed.

    Returns:
        The same kind of response, with the results trimmed.

    """
    if isinstance(search, DocsSearchResponse):
        docs, dropped = _trimmed(search.results, query, max_chars)
        return search.model_copy(update={"results": docs, "deduplicated": dropped})
    found, dropped = _trimmed(search.results, query, max_chars)
    return search.model_copy(update={"results": found, "deduplicated": dropped})


def _trimmed[R: (DocResult, KnowledgeResult)](
    results: list[R], query: str, max_chars: int
) -> tuple[list[R], int]:
    """Return the results kept, each windowed, and how many were dropped."""
    kept, dropped = dedupe_results(results)
    return [truncate_result(result, query, max_chars) for result in kept], dropped


# The values the hosted knowledge index filters on. Measured on 2026-10-08
# against the service the client queries by default (KnowledgeAPIClient's
# DEFAULT_BASE_URL): 160 searches (80 varied actuarial queries, each in chunk
# and in summary retrieval, 50 results apiece, 1,897
# distinct documents between them) gave every value below; each was then
# tried as a filter on its own, as were some 70 plausible others (mortality,
# lapse, csm, ldti, usgaap, solvencyii, risk_adjustment, ca, educational,
# regulatory and more), which matched nothing. The index stores every value in
# lower case. It can gain values without a release of this package, so these
# serve only to tell a reader what exists once a filter has matched nothing: a
# value missing here is still sent, and never refused before the index has
# been asked.
KNOWLEDGE_TAGS: Final[tuple[str, ...]] = (
    "capital",
    "gaap",
    "general",
    "health",
    "ifrs",
    "ifrs17",
    "life",
    "naic",
    "property",
    "reserve",
    "solvency",
)
KNOWLEDGE_JURISDICTIONS: Final[tuple[str, ...]] = (
    "au",
    "eu",
    "international",
    "uk",
    "us",
)
KNOWLEDGE_DOC_TYPES: Final[tuple[str, ...]] = (
    "comment",
    "guidance",
    "practice-note",
    "regulation",
    "standard",
)


def unmatched_filters_note(
    *,
    tags: list[str] | None,
    jurisdiction: str | None,
    doc_type: str | None,
) -> str | None:
    """Say why a filtered knowledge search came back empty, and what to try.

    A filter value the index does not use matches nothing, and an empty
    result alone cannot tell a reader whether the knowledge is missing or the
    filter is misspelt. This names the filters, picks out any value the index
    is not known to use, lists the values it does use, and points at the
    search without filters, whose every result shows its own tags. It never
    drops a filter or retries without one: which value was meant is the
    reader's call.

    Args:
        tags: The ``--tag`` values asked for, if any.
        jurisdiction: The ``--jurisdiction`` asked for, if any.
        doc_type: The ``--doc-type`` asked for, if any.

    Returns:
        The note, or ``None`` where no filter was asked for, since an
        unfiltered search that finds nothing has no filter to blame.

    Examples:
        >>> note = unmatched_filters_note(
        ...     tags=["Mortality"], jurisdiction=None, doc_type=None
        ... )
        >>> note.startswith("No knowledge results matched --tag mortality.")
        True
        >>> "The index is not known to use --tag mortality." in note
        True
        >>> unmatched_filters_note(tags=None, jurisdiction=None, doc_type=None)

    """
    sent = knowledge_filters(tags=tags, jurisdiction=jurisdiction, doc_type=doc_type)
    asked: list[tuple[str, str, tuple[str, ...]]] = [
        ("--tag", tag, KNOWLEDGE_TAGS) for tag in sent.get("tags", [])
    ]
    for option, key, known in (
        ("--jurisdiction", "jurisdiction", KNOWLEDGE_JURISDICTIONS),
        ("--doc-type", "doc_type", KNOWLEDGE_DOC_TYPES),
    ):
        value = sent.get(key)
        if isinstance(value, str):
            asked.append((option, value, known))
    if not asked:
        return None

    filters = " ".join(f"{option} {value}" for option, value, _ in asked)
    unknown = [
        f"{option} {value}" for option, value, known in asked if value not in known
    ]
    if unknown:
        why = (
            f"The index is not known to use {', '.join(unknown)}. Its tags are "
            f"{', '.join(KNOWLEDGE_TAGS)}; its jurisdictions "
            f"{', '.join(KNOWLEDGE_JURISDICTIONS)}; its document types "
            f"{', '.join(KNOWLEDGE_DOC_TYPES)}."
        )
    else:
        why = (
            "Each of those values is one the index uses, so it is the query "
            "and the filters together that match nothing."
        )
    return (
        f"No knowledge results matched {filters}. {why} Re-run without the "
        "filters: every result shows its tags, jurisdiction and doc_type."
    )
