# ABOUTME: API client package for Gaspatchio knowledge services.
# ABOUTME: Exports client and models for docs/knowledge search.
"""Gaspatchio API client package."""

from .models import (
    AnswerResponse,
    APIError,
    SearchResponse,
    SearchResult,
    SourceReference,
)

__all__ = [
    "APIError",
    "AnswerResponse",
    "SearchResponse",
    "SearchResult",
    "SourceReference",
]
