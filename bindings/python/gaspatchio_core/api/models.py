# ABOUTME: Pydantic models for API request/response schemas.
# ABOUTME: Used by docs and knowledge CLI commands.
"""Pydantic models for Gaspatchio API responses."""

from pydantic import BaseModel


class DocResult(BaseModel):
    """A single result from docs search."""

    text: str
    score: float
    content_type: str
    source_file: str
    object_path: str | None
    has_code: bool


class KnowledgeResult(BaseModel):
    """A single result from knowledge search."""

    text: str
    score: float
    doc_id: str
    tags: list[str]
    jurisdiction: str | None
    doc_type: str | None
    chunk_id: str | None = None
    chunk_index: int | None = None
    page_number: int | None = None
    title: str | None = None


class DocsSearchResponse(BaseModel):
    """Response from docs search endpoint."""

    results: list[DocResult]
    query: str
    count: int
    search_type: str
    took_ms: float


class KnowledgeSearchResponse(BaseModel):
    """Response from knowledge search endpoint."""

    results: list[KnowledgeResult]
    query: str
    count: int
    search_type: str
    retrieval_mode: str
    took_ms: float


class DocsAnswerResponse(BaseModel):
    """Response from docs answer endpoint."""

    answer: str
    sources: list[DocResult]
    query: str
    model: str
    tokens_used: int
    took_ms: float


class KnowledgeAnswerResponse(BaseModel):
    """Response from knowledge answer endpoint."""

    answer: str
    sources: list[KnowledgeResult]
    query: str
    model: str
    tokens_used: int
    took_ms: float


class ValidationErrorDetail(BaseModel):
    """Detail of a validation error."""

    loc: list[str | int]
    msg: str
    type: str


class HTTPValidationError(BaseModel):
    """Validation error response from the API."""

    detail: list[ValidationErrorDetail]
