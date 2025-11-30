# ABOUTME: Pydantic models for API request/response schemas.
# ABOUTME: Used by docs and knowledge CLI commands.
"""Pydantic models for Gaspatchio API responses."""

from pydantic import BaseModel


class SearchResult(BaseModel):
    """A single search result from the knowledge API."""

    text: str
    source: str
    content_type: str
    score: float
    # Optional fields that may be present depending on store
    page: int | None = None
    doc_type: str | None = None
    object_path: str | None = None


class SourceReference(BaseModel):
    """A source reference in an answer response."""

    source: str
    score: float


class SearchResponse(BaseModel):
    """Response from a search query."""

    results: list[SearchResult]
    query: str
    version: str


class AnswerResponse(BaseModel):
    """Response from a query with --answer flag."""

    answer: str
    sources: list[SourceReference]
    query: str
    version: str


class APIError(BaseModel):
    """Error response from the API."""

    error: str
    status: int
    message: str
