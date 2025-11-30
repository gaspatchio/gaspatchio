# ABOUTME: HTTP client for the Gaspatchio knowledge API.
# ABOUTME: Handles docs and knowledge search requests.
"""HTTP client for Gaspatchio knowledge API."""

import os
import typing

import httpx

from .models import AnswerResponse, APIError, SearchResponse


class APIConnectionError(Exception):
    """Raised when the API is unavailable."""


class KnowledgeAPIClient:
    """Client for the Gaspatchio knowledge API.

    Handles searching framework documentation and actuarial knowledge bases.
    """

    DEFAULT_BASE_URL = "https://api.gaspatchio.com"
    DEFAULT_TIMEOUT = 30.0
    HTTP_ERROR_THRESHOLD = 400

    def __init__(
        self,
        base_url: str | None = None,
        version: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the API client.

        Args:
            base_url: API base URL. Defaults to GASPATCHIO_API_URL env var
                or https://api.gaspatchio.com
            version: Gaspatchio version to include in requests.
            timeout: Request timeout in seconds.

        """
        self.base_url = base_url or os.environ.get(
            "GASPATCHIO_API_URL", self.DEFAULT_BASE_URL
        )
        self.version = version or self._get_package_version()
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _get_package_version(self) -> str:
        """Get the gaspatchio package version."""
        try:
            from importlib.metadata import version

            return version("gaspatchio-core")
        except (ImportError, ModuleNotFoundError):
            return "unknown"

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
        self._raise_api_error(response)
        msg = "Unreachable"
        raise AssertionError(msg)

    def _raise_api_error(self, response: httpx.Response) -> typing.NoReturn:
        """Parse response and raise appropriate error."""
        try:
            error_data = response.json()
            error = APIError.model_validate(error_data)
        except Exception:  # noqa: BLE001
            self._raise_generic_error(response.status_code, response.text)
        else:
            self._raise_formatted_error(error.status, error.message)
        msg = "Unreachable"
        raise AssertionError(msg)

    def _raise_formatted_error(self, status: int, message: str) -> typing.NoReturn:
        """Raise error with formatted API error message."""
        msg = f"API error ({status}): {message}"
        raise APIConnectionError(msg) from None

    def _raise_generic_error(self, status_code: int, text: str) -> typing.NoReturn:
        """Raise error with generic error message."""
        msg = f"API error: {status_code} - {text}"
        raise APIConnectionError(msg) from None

    def _make_request(
        self,
        endpoint: str,
        query: str,
        *,
        answer: bool = False,
        limit: int = 5,
    ) -> SearchResponse | AnswerResponse:
        """Make a request to the API.

        Args:
            endpoint: API endpoint path.
            query: Search query.
            answer: Whether to request a generated answer.
            limit: Maximum number of results.

        Returns:
            SearchResponse or AnswerResponse depending on answer flag.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        url = f"{self.base_url}{endpoint}"
        payload = {
            "query": query,
            "version": self.version,
            "answer": answer,
            "limit": limit,
        }

        try:
            response = self._client.post(url, json=payload)
        except httpx.ConnectError as e:
            self._raise_connection_error(e)
        except httpx.TimeoutException as e:
            self._raise_timeout_error(e)

        if response.status_code >= self.HTTP_ERROR_THRESHOLD:
            self._raise_http_error(response)

        data = response.json()
        if answer:
            return AnswerResponse.model_validate(data)
        return SearchResponse.model_validate(data)

    def search_docs(
        self,
        query: str,
        *,
        answer: bool = False,
        limit: int = 5,
    ) -> SearchResponse | AnswerResponse:
        """Search Gaspatchio framework documentation.

        Args:
            query: Search query - can be keywords or a question.
            answer: If True, return a generated answer instead of results.
            limit: Maximum number of results to return.

        Returns:
            SearchResponse with results, or AnswerResponse if answer=True.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        return self._make_request("/v1/docs/search", query, answer=answer, limit=limit)

    def search_knowledge(
        self,
        query: str,
        *,
        answer: bool = False,
        limit: int = 5,
    ) -> SearchResponse | AnswerResponse:
        """Search actuarial knowledge base.

        Args:
            query: Search query - can be keywords or a question.
            answer: If True, return a generated answer instead of results.
            limit: Maximum number of results to return.

        Returns:
            SearchResponse with results, or AnswerResponse if answer=True.

        Raises:
            APIConnectionError: If the API is unavailable.

        """
        return self._make_request(
            "/v1/knowledge/search", query, answer=answer, limit=limit
        )
