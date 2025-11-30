# ABOUTME: API client package for Gaspatchio knowledge services.
# ABOUTME: Exports client and models for docs/knowledge search.
"""Gaspatchio API client package."""

from .client import APIConnectionError, KnowledgeAPIClient
from .models import (
    AnswerResponse,
    APIError,
    SearchResponse,
    SearchResult,
    SourceReference,
)

__all__ = [
    "APIConnectionError",
    "APIError",
    "AnswerResponse",
    "KnowledgeAPIClient",
    "SearchResponse",
    "SearchResult",
    "SourceReference",
]
