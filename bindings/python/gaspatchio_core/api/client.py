# ABOUTME: HTTP client for the Gaspatchio knowledge API.
# ABOUTME: Handles docs and knowledge search requests.
"""HTTP client for Gaspatchio knowledge API."""

import os
import typing

import httpx
from loguru import logger

from .models import (
    DocsAnswerResponse,
    DocsSearchResponse,
    HTTPValidationError,
    KnowledgeAnswerResponse,
    KnowledgeSearchResponse,
)


class APIConnectionError(Exception):
    """Raised when the API is unavailable."""


class KnowledgeAPIClient:
    """Client for the Gaspatchio knowledge API.

    Handles searching framework documentation and actuarial knowledge bases.
    """

    DEFAULT_BASE_URL = "https://gaspatchio-mix.fly.dev"
    DEFAULT_TIMEOUT = 30.0
    HTTP_ERROR_THRESHOLD = 400
    HTTP_VALIDATION_ERROR = 422

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the API client.

        Args:
            base_url: API base URL. Defaults to GASPATCHIO_API_URL env var
                or https://gaspatchio-mix.fly.dev
            timeout: Request timeout in seconds.

        """
        self.base_url = base_url or os.environ.get(
            "GASPATCHIO_API_URL", self.DEFAULT_BASE_URL
        )
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _raise_connection_error(self, e: httpx.ConnectError) -> typing.NoReturn:
        """Raise connection error with formatted message."""
        msg = (
            f"API unavailable: Could not connect to {self.base_url}. "
            "Please check your network connection or try again later."
        )
        raise APIConnectionError(msg) from e

    def _raise_timeout_error(self, e: httpx.TimeoutException) -> typing.NoReturn:
        """Raise timeout error with formatted message."""
        msg = (
            f"API unavailable: Request to {self.base_url} timed out. "
            "Please try again later."
        )
        raise APIConnectionError(msg) from e

    def _raise_http_error(self, response: httpx.Response) -> typing.NoReturn:
        """Raise HTTP error with formatted message."""
        # Try to parse validation error first (422)
        if response.status_code == self.HTTP_VALIDATION_ERROR:
            self._raise_validation_error(response)
        else:
            self._raise_generic_error(response.status_code, response.text)
        msg = "Unreachable"
        raise AssertionError(msg)

    def _raise_validation_error(self, response: httpx.Response) -> typing.NoReturn:
        """Parse validation error and raise with formatted message."""
        try:
            error_data = response.json()
            error = HTTPValidationError.model_validate(error_data)
            messages = [f"{d.msg} at {d.loc}" for d in error.detail]
            msg = f"API validation error: {'; '.join(messages)}"
        except Exception:  # noqa: BLE001
            msg = f"API validation error: {response.text}"
        raise APIConnectionError(msg) from None

    def _raise_generic_error(self, status_code: int, text: str) -> typing.NoReturn:
        """Raise error with generic error message."""
        msg = f"API error: {status_code} - {text}"
        raise APIConnectionError(msg) from None

    def _post(
        self,
        endpoint: str,
        payload: dict[str, typing.Any],
    ) -> dict[str, typing.Any]:
        """Make a POST request to the API.

        Args:
            endpoint: API endpoint path (e.g., "/api/v1/docs/search").
            payload: Request payload.

        Returns:
            Parsed JSON response.

        Raises:
            APIConnectionError: If the API is unavailable or returns an error.

        """
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"API request: POST {url}")

        try:
            response = self._client.post(url, json=payload)
        except httpx.ConnectError as e:
            self._raise_connection_error(e)
        except httpx.TimeoutException as e:
            self._raise_timeout_error(e)

        if response.status_code >= self.HTTP_ERROR_THRESHOLD:
            self._raise_http_error(response)

        return response.json()

    def search_docs(
        self,
        query: str,
        *,
        limit: int = 10,
        search_type: str = "hybrid",
        content_type: list[str] | None = None,
    ) -> DocsSearchResponse:
        """Search Gaspatchio framework documentation.

        Args:
            query: Search query - can be keywords or a question.
            limit: Maximum number of results to return.
            search_type: Search method - "hybrid", "semantic", or "keyword".
            content_type: Filter by content types (e.g., ["code", "docstring"]).

        Returns:
            DocsSearchResponse with search results.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        payload: dict[str, typing.Any] = {
            "query": query,
            "limit": limit,
            "search_type": search_type,
        }
        if content_type is not None:
            payload["content_type"] = content_type

        data = self._post("/api/v1/docs/search", payload)
        return DocsSearchResponse.model_validate(data)

    def answer_docs(
        self,
        query: str,
        *,
        limit: int = 5,
        search_type: str = "hybrid",
        content_type: list[str] | None = None,
    ) -> DocsAnswerResponse:
        """Get a generated answer from Gaspatchio documentation.

        Args:
            query: Question to answer.
            limit: Number of sources to use for generation.
            search_type: Search method - "hybrid", "semantic", or "keyword".
            content_type: Filter by content types (e.g., ["code", "docstring"]).

        Returns:
            DocsAnswerResponse with generated answer and sources.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        payload: dict[str, typing.Any] = {
            "query": query,
            "limit": limit,
            "search_type": search_type,
        }
        if content_type is not None:
            payload["content_type"] = content_type

        data = self._post("/api/v1/docs/answer", payload)
        return DocsAnswerResponse.model_validate(data)

    def search_knowledge(  # noqa: PLR0913
        self,
        query: str,
        *,
        limit: int = 10,
        search_type: str = "hybrid",
        retrieval_mode: str = "chunks",
        tags: list[str] | None = None,
        jurisdiction: str | None = None,
        doc_type: str | None = None,
    ) -> KnowledgeSearchResponse:
        """Search actuarial knowledge base.

        Args:
            query: Search query - can be keywords or a question.
            limit: Maximum number of results to return.
            search_type: Search method - "hybrid", "semantic", or "keyword".
            retrieval_mode: How to retrieve results - "summaries", "chunks",
                or "hierarchical".
            tags: Filter by tags (e.g., ["IFRS17", "reserving"]).
            jurisdiction: Filter by jurisdiction (e.g., "US", "EU").
            doc_type: Filter by document type.

        Returns:
            KnowledgeSearchResponse with search results.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        payload: dict[str, typing.Any] = {
            "query": query,
            "limit": limit,
            "search_type": search_type,
            "retrieval_mode": retrieval_mode,
        }
        if tags is not None:
            payload["tags"] = tags
        if jurisdiction is not None:
            payload["jurisdiction"] = jurisdiction
        if doc_type is not None:
            payload["doc_type"] = doc_type

        data = self._post("/api/v1/knowledge/search", payload)
        return KnowledgeSearchResponse.model_validate(data)

    def answer_knowledge(  # noqa: PLR0913
        self,
        query: str,
        *,
        limit: int = 5,
        search_type: str = "hybrid",
        retrieval_mode: str = "chunks",
        tags: list[str] | None = None,
        jurisdiction: str | None = None,
        doc_type: str | None = None,
    ) -> KnowledgeAnswerResponse:
        """Get a generated answer from actuarial knowledge base.

        Args:
            query: Question to answer.
            limit: Number of sources to use for generation.
            search_type: Search method - "hybrid", "semantic", or "keyword".
            retrieval_mode: How to retrieve results - "summaries", "chunks",
                or "hierarchical".
            tags: Filter by tags (e.g., ["IFRS17", "reserving"]).
            jurisdiction: Filter by jurisdiction (e.g., "US", "EU").
            doc_type: Filter by document type.

        Returns:
            KnowledgeAnswerResponse with generated answer and sources.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        payload: dict[str, typing.Any] = {
            "query": query,
            "limit": limit,
            "search_type": search_type,
            "retrieval_mode": retrieval_mode,
        }
        if tags is not None:
            payload["tags"] = tags
        if jurisdiction is not None:
            payload["jurisdiction"] = jurisdiction
        if doc_type is not None:
            payload["doc_type"] = doc_type

        data = self._post("/api/v1/knowledge/answer", payload)
        return KnowledgeAnswerResponse.model_validate(data)
