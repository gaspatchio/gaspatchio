# ABOUTME: Tests for API response models.
# ABOUTME: Validates Pydantic models can parse API responses correctly.
"""Tests for API response models."""

from gaspatchio_core.api.models import (
    AnswerResponse,
    APIError,
    SearchResponse,
    SearchResult,
)


def test_search_result_from_dict():
    """SearchResult can be created from API response dict."""
    data = {
        "text": "cumulative_survival() calculates...",
        "source": "gaspatchio_core/accessors/projection.py",
        "content_type": "code_example",
        "score": 0.92,
    }
    result = SearchResult.model_validate(data)
    assert result.text == "cumulative_survival() calculates..."
    assert result.source == "gaspatchio_core/accessors/projection.py"
    assert result.content_type == "code_example"
    assert result.score == 0.92


def test_search_response_from_dict():
    """SearchResponse can be created from API response."""
    data = {
        "results": [
            {
                "text": "some text",
                "source": "file.py",
                "content_type": "markdown",
                "score": 0.8,
            }
        ],
        "query": "test query",
        "version": "0.4.2",
    }
    response = SearchResponse.model_validate(data)
    assert len(response.results) == 1
    assert response.query == "test query"
    assert response.version == "0.4.2"


def test_answer_response_from_dict():
    """AnswerResponse can be created from API response."""
    data = {
        "answer": "To calculate cumulative survival...",
        "sources": [{"source": "file.py", "score": 0.9}],
        "query": "how do I calculate survival?",
        "version": "0.4.2",
    }
    response = AnswerResponse.model_validate(data)
    assert response.answer == "To calculate cumulative survival..."
    assert len(response.sources) == 1


def test_api_error_from_dict():
    """APIError can be created from error response."""
    data = {
        "error": "API unavailable",
        "status": 503,
        "message": "Service temporarily unavailable",
    }
    error = APIError.model_validate(data)
    assert error.error == "API unavailable"
    assert error.status == 503
