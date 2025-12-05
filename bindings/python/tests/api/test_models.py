# ABOUTME: Tests for API response models.
# ABOUTME: Validates Pydantic models can parse API responses correctly.
"""Tests for API response models."""

from gaspatchio_core.api.models import (
    DocResult,
    DocsAnswerResponse,
    DocsSearchResponse,
    HTTPValidationError,
    KnowledgeAnswerResponse,
    KnowledgeResult,
    KnowledgeSearchResponse,
)


def test_doc_result_from_dict():
    """DocResult can be created from API response dict."""
    data = {
        "text": "cumulative_survival() calculates...",
        "source_file": "gaspatchio_core/accessors/projection.py",
        "content_type": "code_example",
        "score": 0.92,
        "object_path": "projection.cumulative_survival",
        "has_code": True,
    }
    result = DocResult.model_validate(data)
    assert result.text == "cumulative_survival() calculates..."
    assert result.source_file == "gaspatchio_core/accessors/projection.py"
    assert result.content_type == "code_example"
    assert result.score == 0.92
    assert result.object_path == "projection.cumulative_survival"
    assert result.has_code is True


def test_knowledge_result_from_dict():
    """KnowledgeResult can be created from API response dict."""
    data = {
        "text": "The Contractual Service Margin (CSM)...",
        "score": 0.88,
        "doc_id": "ifrs17-guide",
        "tags": ["IFRS17", "CSM"],
        "jurisdiction": "EU",
        "doc_type": "regulatory",
        "page_number": 42,
        "title": "IFRS 17 Guide",
    }
    result = KnowledgeResult.model_validate(data)
    assert result.text == "The Contractual Service Margin (CSM)..."
    assert result.score == 0.88
    assert result.doc_id == "ifrs17-guide"
    assert result.tags == ["IFRS17", "CSM"]
    assert result.jurisdiction == "EU"
    assert result.doc_type == "regulatory"
    assert result.page_number == 42
    assert result.title == "IFRS 17 Guide"


def test_docs_search_response_from_dict():
    """DocsSearchResponse can be created from API response."""
    data = {
        "results": [
            {
                "text": "some text",
                "source_file": "file.py",
                "content_type": "markdown",
                "score": 0.8,
                "object_path": None,
                "has_code": False,
            }
        ],
        "query": "test query",
        "count": 1,
        "search_type": "hybrid",
        "took_ms": 42.5,
    }
    response = DocsSearchResponse.model_validate(data)
    assert len(response.results) == 1
    assert response.query == "test query"
    assert response.count == 1
    assert response.search_type == "hybrid"
    assert response.took_ms == 42.5


def test_knowledge_search_response_from_dict():
    """KnowledgeSearchResponse can be created from API response."""
    data = {
        "results": [
            {
                "text": "IFRS 17 requires...",
                "score": 0.9,
                "doc_id": "ifrs17",
                "tags": ["IFRS17"],
                "jurisdiction": "EU",
                "doc_type": "standard",
            }
        ],
        "query": "IFRS 17 requirements",
        "count": 1,
        "search_type": "hybrid",
        "retrieval_mode": "chunks",
        "took_ms": 55.3,
    }
    response = KnowledgeSearchResponse.model_validate(data)
    assert len(response.results) == 1
    assert response.query == "IFRS 17 requirements"
    assert response.count == 1
    assert response.retrieval_mode == "chunks"


def test_docs_answer_response_from_dict():
    """DocsAnswerResponse can be created from API response."""
    data = {
        "answer": "To calculate cumulative survival...",
        "sources": [
            {
                "text": "cumulative_survival()...",
                "score": 0.9,
                "content_type": "code",
                "source_file": "projection.py",
                "object_path": None,
                "has_code": True,
            }
        ],
        "query": "how do I calculate survival?",
        "model": "claude-3-sonnet",
        "tokens_used": 150,
        "took_ms": 1200.5,
    }
    response = DocsAnswerResponse.model_validate(data)
    assert response.answer == "To calculate cumulative survival..."
    assert len(response.sources) == 1
    assert response.model == "claude-3-sonnet"
    assert response.tokens_used == 150


def test_knowledge_answer_response_from_dict():
    """KnowledgeAnswerResponse can be created from API response."""
    data = {
        "answer": "The CSM represents the unearned profit...",
        "sources": [
            {
                "text": "CSM definition...",
                "score": 0.9,
                "doc_id": "ifrs17",
                "tags": ["IFRS17", "CSM"],
                "jurisdiction": "EU",
                "doc_type": "standard",
            }
        ],
        "query": "what is CSM?",
        "model": "claude-3-sonnet",
        "tokens_used": 200,
        "took_ms": 1500.0,
    }
    response = KnowledgeAnswerResponse.model_validate(data)
    assert response.answer == "The CSM represents the unearned profit..."
    assert len(response.sources) == 1
    assert response.model == "claude-3-sonnet"


def test_http_validation_error_from_dict():
    """HTTPValidationError can be created from error response."""
    data = {
        "detail": [
            {
                "loc": ["body", "query"],
                "msg": "Field required",
                "type": "missing",
            }
        ]
    }
    error = HTTPValidationError.model_validate(data)
    assert len(error.detail) == 1
    assert error.detail[0].msg == "Field required"
