# ABOUTME: API client package for Gaspatchio knowledge services.
# ABOUTME: Exports client and models for docs/knowledge search.
"""Gaspatchio API client package."""

from .client import APIConnectionError, KnowledgeAPIClient
from .models import (
    DocResult,
    DocsAnswerResponse,
    DocsSearchResponse,
    HTTPValidationError,
    KnowledgeAnswerResponse,
    KnowledgeResult,
    KnowledgeSearchResponse,
    ValidationErrorDetail,
)

__all__ = [
    "APIConnectionError",
    "DocResult",
    "DocsAnswerResponse",
    "DocsSearchResponse",
    "HTTPValidationError",
    "KnowledgeAPIClient",
    "KnowledgeAnswerResponse",
    "KnowledgeResult",
    "KnowledgeSearchResponse",
    "ValidationErrorDetail",
]
