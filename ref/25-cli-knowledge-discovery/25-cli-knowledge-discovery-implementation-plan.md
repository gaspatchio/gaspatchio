# CLI Knowledge Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `gspio docs` and `gspio knowledge` commands that enable LLMs to search Gaspatchio documentation and actuarial knowledge bases.

**Architecture:** Thin CLI client that makes HTTP calls to a knowledge API. Commands return JSON search results by default, with optional `--answer` flag for RAG-generated responses. Rich `--help` output guides LLMs to prefer search over generated answers.

**Tech Stack:** Typer (CLI), httpx (HTTP client), Pydantic (response models)

---

## Task 1: Create API Client Response Models

**Files:**
- Create: `gaspatchio_core/api/models.py`
- Test: `tests/api/test_models.py`

**Step 1: Write the failing test**

```python
# tests/api/test_models.py
"""Tests for API response models."""

import pytest
from gaspatchio_core.api.models import (
    SearchResult,
    SearchResponse,
    AnswerResponse,
    APIError,
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'gaspatchio_core.api'"

**Step 3: Create the api package directory**

```bash
mkdir -p gaspatchio_core/api
touch gaspatchio_core/api/__init__.py
```

**Step 4: Write minimal implementation**

```python
# gaspatchio_core/api/models.py
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
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add gaspatchio_core/api/ tests/api/
git commit -m "feat(api): add response models for knowledge API"
```

---

## Task 2: Create API Client

**Files:**
- Create: `gaspatchio_core/api/client.py`
- Test: `tests/api/test_client.py`

**Step 1: Write the failing test**

```python
# tests/api/test_client.py
"""Tests for the knowledge API client."""

import json
import pytest
from unittest.mock import patch, MagicMock
from gaspatchio_core.api.client import KnowledgeAPIClient, APIConnectionError
from gaspatchio_core.api.models import SearchResponse, AnswerResponse, APIError


class TestKnowledgeAPIClient:
    """Tests for KnowledgeAPIClient."""

    def test_client_uses_env_var_for_base_url(self, monkeypatch):
        """Client reads GASPATCHIO_API_URL from environment."""
        monkeypatch.setenv("GASPATCHIO_API_URL", "https://custom.api.com")
        client = KnowledgeAPIClient()
        assert client.base_url == "https://custom.api.com"

    def test_client_uses_default_url_when_env_not_set(self, monkeypatch):
        """Client uses default URL when env var not set."""
        monkeypatch.delenv("GASPATCHIO_API_URL", raising=False)
        client = KnowledgeAPIClient()
        assert client.base_url == "https://api.gaspatchio.com"

    def test_client_includes_version_in_requests(self):
        """Client includes gaspatchio version in all requests."""
        client = KnowledgeAPIClient(version="0.4.2")
        assert client.version == "0.4.2"

    @patch("httpx.Client.post")
    def test_search_docs_returns_search_response(self, mock_post):
        """search_docs returns SearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "test",
                    "source": "file.py",
                    "content_type": "code",
                    "score": 0.9,
                }
            ],
            "query": "test",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_docs("test query")

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 1

    @patch("httpx.Client.post")
    def test_search_docs_with_answer_returns_answer_response(self, mock_post):
        """search_docs with answer=True returns AnswerResponse."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "The answer is...",
            "sources": [{"source": "file.py", "score": 0.9}],
            "query": "test",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_docs("test query", answer=True)

        assert isinstance(result, AnswerResponse)
        assert result.answer == "The answer is..."

    @patch("httpx.Client.post")
    def test_search_docs_raises_on_connection_error(self, mock_post):
        """search_docs raises APIConnectionError on network failure."""
        import httpx
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = KnowledgeAPIClient(version="0.4.2")
        with pytest.raises(APIConnectionError) as exc_info:
            client.search_docs("test query")

        assert "API unavailable" in str(exc_info.value)

    @patch("httpx.Client.post")
    def test_search_knowledge_returns_search_response(self, mock_post):
        """search_knowledge returns SearchResponse on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "text": "IFRS 17...",
                    "source": "ifrs17.pdf",
                    "content_type": "regulatory",
                    "score": 0.88,
                    "page": 42,
                }
            ],
            "query": "CSM",
            "version": "0.4.2",
        }
        mock_post.return_value = mock_response

        client = KnowledgeAPIClient(version="0.4.2")
        result = client.search_knowledge("CSM")

        assert isinstance(result, SearchResponse)
        assert result.results[0].page == 42
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'gaspatchio_core.api.client'"

**Step 3: Write minimal implementation**

```python
# gaspatchio_core/api/client.py
# ABOUTME: HTTP client for the Gaspatchio knowledge API.
# ABOUTME: Handles docs and knowledge search requests.
"""HTTP client for Gaspatchio knowledge API."""

import os
from typing import Literal

import httpx

from .models import SearchResponse, AnswerResponse, APIError


class APIConnectionError(Exception):
    """Raised when the API is unavailable."""

    pass


class KnowledgeAPIClient:
    """Client for the Gaspatchio knowledge API.

    Handles searching framework documentation and actuarial knowledge bases.
    """

    DEFAULT_BASE_URL = "https://api.gaspatchio.com"
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: str | None = None,
        version: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
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
        except Exception:
            return "unknown"

    def _make_request(
        self,
        endpoint: str,
        query: str,
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
            raise APIConnectionError(
                f"API unavailable: Could not connect to {self.base_url}. "
                "Please check your network connection or try again later."
            ) from e
        except httpx.TimeoutException as e:
            raise APIConnectionError(
                f"API unavailable: Request to {self.base_url} timed out. "
                "Please try again later."
            ) from e

        if response.status_code >= 400:
            try:
                error_data = response.json()
                error = APIError.model_validate(error_data)
                raise APIConnectionError(
                    f"API error ({error.status}): {error.message}"
                )
            except Exception:
                raise APIConnectionError(
                    f"API error: {response.status_code} - {response.text}"
                )

        data = response.json()
        if answer:
            return AnswerResponse.model_validate(data)
        return SearchResponse.model_validate(data)

    def search_docs(
        self,
        query: str,
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
        return self._make_request("/v1/docs/search", query, answer, limit)

    def search_knowledge(
        self,
        query: str,
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
        return self._make_request("/v1/knowledge/search", query, answer, limit)
```

**Step 4: Update api package __init__.py**

```python
# gaspatchio_core/api/__init__.py
# ABOUTME: API client package for Gaspatchio knowledge services.
# ABOUTME: Exports client and models for docs/knowledge search.
"""Gaspatchio API client package."""

from .client import KnowledgeAPIClient, APIConnectionError
from .models import (
    SearchResult,
    SearchResponse,
    AnswerResponse,
    APIError,
)

__all__ = [
    "KnowledgeAPIClient",
    "APIConnectionError",
    "SearchResult",
    "SearchResponse",
    "AnswerResponse",
    "APIError",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/api/test_client.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add gaspatchio_core/api/ tests/api/
git commit -m "feat(api): add knowledge API client"
```

---

## Task 3: Add `docs` Command to CLI

**Files:**
- Modify: `gaspatchio_core/cli.py`
- Test: `tests/test_cli_docs.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_docs.py
"""Tests for gspio docs command."""

import json
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from gaspatchio_core.cli import app
from gaspatchio_core.api.models import SearchResponse, SearchResult


runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs command."""

    def test_docs_help_shows_usage_guidance(self):
        """docs --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "Search Gaspatchio framework documentation" in result.output
        assert "IMPORTANT: Prefer search results" in result.output
        assert "Use sparingly" in result.output  # On --answer flag

    def test_docs_help_shows_examples(self):
        """docs --help shows example queries."""
        result = runner.invoke(app, ["docs", "--help"])
        assert result.exit_code == 0
        assert "cumulative survival" in result.output.lower() or "example" in result.output.lower()

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_returns_json(self, mock_client_class):
        """docs command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = SearchResponse(
            results=[
                SearchResult(
                    text="cumulative_survival() calculates...",
                    source="projection.py",
                    content_type="code_example",
                    score=0.92,
                )
            ],
            query="cumulative survival",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "cumulative survival"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "results" in output
        assert output["query"] == "cumulative survival"

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_limit_option(self, mock_client_class):
        """docs -n flag sets result limit."""
        mock_client = MagicMock()
        mock_client.search_docs.return_value = SearchResponse(
            results=[],
            query="test",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "test", "-n", "10"])

        assert result.exit_code == 0
        mock_client.search_docs.assert_called_once_with(
            "test", answer=False, limit=10
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_with_answer_flag(self, mock_client_class):
        """docs --answer returns generated answer."""
        from gaspatchio_core.api.models import AnswerResponse, SourceReference

        mock_client = MagicMock()
        mock_client.search_docs.return_value = AnswerResponse(
            answer="To calculate cumulative survival, use...",
            sources=[SourceReference(source="projection.py", score=0.9)],
            query="how to calculate survival",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "how to calculate survival", "--answer"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output
        mock_client.search_docs.assert_called_once_with(
            "how to calculate survival", answer=True, limit=5
        )

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_docs_api_error_exits_nonzero(self, mock_client_class):
        """docs exits with error code on API failure."""
        from gaspatchio_core.api.client import APIConnectionError

        mock_client = MagicMock()
        mock_client.search_docs.side_effect = APIConnectionError("API unavailable")
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["docs", "test"])

        assert result.exit_code == 1
        assert "API unavailable" in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_docs.py -v`
Expected: FAIL with "No such command 'docs'"

**Step 3: Add docs command to cli.py**

Add the following to `gaspatchio_core/cli.py` after the existing imports:

```python
from .api import KnowledgeAPIClient, APIConnectionError, SearchResponse, AnswerResponse
```

Add the following command before the `if __name__ == "__main__":` block:

```python
# Help text constants for LLM discoverability
DOCS_HELP = """Search Gaspatchio framework documentation.

[bold yellow]IMPORTANT: Prefer search results (default) over --answer.[/bold yellow]
Search returns multiple relevant excerpts that you can evaluate
in context. Only use --answer when you need a quick summary and
don't have specific context requirements.

[bold]Use this command when you need to find:[/bold]
• API methods on ActuarialFrame (e.g., "how to add a column")
• Accessor methods (.projection, .excel, .finance, .mortality)
• Code patterns and examples from working models
• Function signatures and parameters

[bold green]Examples:[/bold green]
    gspio docs "ActuarialFrame"                               # ← preferred
    gspio docs "how do I shift values by one period?"         # ← preferred
    gspio docs "projection accessor methods"                  # ← preferred
    gspio docs "excel pv function" -n 10                      # ← preferred
    gspio docs "what is when then otherwise?" --answer        # ← only for quick summaries
"""


@app.command(
    name="docs",
    help="Search Gaspatchio framework documentation (API, accessors, examples)",
    rich_help_panel="Knowledge Discovery",
)
def docs(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - can be a question or keywords",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Return a generated answer instead of search results. "
            "Prefer default search - it returns multiple results you can evaluate with your context.",
            rich_help_panel="Search Options",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of results to return",
            min=1,
            max=20,
            rich_help_panel="Search Options",
        ),
    ] = 5,
):
    """Search Gaspatchio framework documentation.

    IMPORTANT: Prefer search results (default) over --answer.
    Search returns multiple relevant excerpts that you can evaluate
    in context. Only use --answer when you need a quick summary and
    don't have specific context requirements.

    Use this command when you need to find:
    • API methods on ActuarialFrame (e.g., "how to add a column")
    • Accessor methods (.projection, .excel, .finance, .mortality)
    • Code patterns and examples from working models
    • Function signatures and parameters

    [bold green]Examples:[/bold green]
        gspio docs "ActuarialFrame"                               # ← preferred
        gspio docs "how do I shift values by one period?"         # ← preferred
        gspio docs "projection accessor methods"                  # ← preferred
        gspio docs "excel pv function" -n 10                      # ← preferred
        gspio docs "what is when then otherwise?" --answer        # ← only for quick summaries
    """
    try:
        client = KnowledgeAPIClient()
        result = client.search_docs(query, answer=answer, limit=limit)
        # Output JSON directly for LLM consumption
        print(result.model_dump_json(indent=2))
    except APIConnectionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_docs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/cli.py tests/test_cli_docs.py
git commit -m "feat(cli): add docs command for framework documentation search"
```

---

## Task 4: Add `knowledge` Command to CLI

**Files:**
- Modify: `gaspatchio_core/cli.py`
- Test: `tests/test_cli_knowledge.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_knowledge.py
"""Tests for gspio knowledge command."""

import json
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from gaspatchio_core.cli import app
from gaspatchio_core.api.models import SearchResponse, SearchResult


runner = CliRunner()


class TestKnowledgeCommand:
    """Tests for the knowledge command."""

    def test_knowledge_help_shows_usage_guidance(self):
        """knowledge --help shows LLM-friendly guidance."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "Search the actuarial knowledge base" in result.output
        assert "IMPORTANT: Prefer search results" in result.output
        assert "Use sparingly" in result.output

    def test_knowledge_help_shows_examples(self):
        """knowledge --help shows example queries."""
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "IFRS" in result.output or "actuarial" in result.output.lower()

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_returns_json(self, mock_client_class):
        """knowledge command returns JSON output."""
        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = SearchResponse(
            results=[
                SearchResult(
                    text="The Contractual Service Margin (CSM)...",
                    source="IFRS17_Guide.pdf",
                    content_type="regulatory",
                    score=0.88,
                    page=42,
                )
            ],
            query="IFRS 17 CSM",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "IFRS 17 CSM"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "results" in output
        assert output["results"][0]["page"] == 42

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_with_answer_flag(self, mock_client_class):
        """knowledge --answer returns generated answer."""
        from gaspatchio_core.api.models import AnswerResponse, SourceReference

        mock_client = MagicMock()
        mock_client.search_knowledge.return_value = AnswerResponse(
            answer="The risk adjustment under IFRS 17 is...",
            sources=[SourceReference(source="ifrs17.pdf", score=0.9)],
            query="what is risk adjustment",
            version="0.4.2",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "what is risk adjustment", "-a"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "answer" in output

    @patch("gaspatchio_core.cli.KnowledgeAPIClient")
    def test_knowledge_api_error_exits_nonzero(self, mock_client_class):
        """knowledge exits with error code on API failure."""
        from gaspatchio_core.api.client import APIConnectionError

        mock_client = MagicMock()
        mock_client.search_knowledge.side_effect = APIConnectionError("API unavailable")
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["knowledge", "test"])

        assert result.exit_code == 1
        assert "API unavailable" in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_knowledge.py -v`
Expected: FAIL with "No such command 'knowledge'"

**Step 3: Add knowledge command to cli.py**

Add the following command after the `docs` command in `gaspatchio_core/cli.py`:

```python
@app.command(
    name="knowledge",
    help="Search actuarial knowledge base (IFRS 17, Solvency II, regulations)",
    rich_help_panel="Knowledge Discovery",
)
def knowledge(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query - can be a question or keywords",
        ),
    ],
    answer: Annotated[
        bool,
        typer.Option(
            "--answer",
            "-a",
            help="(Use sparingly) Return a generated answer instead of search results. "
            "Prefer default search - it returns multiple excerpts you can evaluate with your context.",
            rich_help_panel="Search Options",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum number of results to return",
            min=1,
            max=20,
            rich_help_panel="Search Options",
        ),
    ] = 5,
):
    """Search the actuarial knowledge base.

    IMPORTANT: Prefer search results (default) over --answer.
    Search returns multiple relevant excerpts from regulatory documents
    that you can evaluate in context. Only use --answer when you need
    a quick conceptual summary.

    Use this command when you need to understand:
    • Regulatory frameworks (IFRS 17, Solvency II, US GAAP)
    • Actuarial concepts (CSM, risk adjustment, PAA, BBA)
    • Industry standards and guidance
    • Mortality, morbidity, and lapse assumptions

    [bold green]Examples:[/bold green]
        gspio knowledge "IFRS 17 CSM"                             # ← preferred
        gspio knowledge "Solvency II technical provisions"        # ← preferred
        gspio knowledge "lapse rate assumptions" -n 10            # ← preferred
        gspio knowledge "risk adjustment calculation methods"     # ← preferred
        gspio knowledge "what is BBA vs PAA?" --answer            # ← only for quick summaries
    """
    try:
        client = KnowledgeAPIClient()
        result = client.search_knowledge(query, answer=answer, limit=limit)
        # Output JSON directly for LLM consumption
        print(result.model_dump_json(indent=2))
    except APIConnectionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_knowledge.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/cli.py tests/test_cli_knowledge.py
git commit -m "feat(cli): add knowledge command for actuarial knowledge search"
```

---

## Task 5: Enhance Main Help Output

**Files:**
- Modify: `gaspatchio_core/cli.py`
- Test: `tests/test_cli_help.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_help.py
"""Tests for gspio --help output."""

import pytest
from typer.testing import CliRunner
from gaspatchio_core.cli import app


runner = CliRunner()


class TestMainHelp:
    """Tests for the main --help output."""

    def test_main_help_shows_knowledge_discovery_section(self):
        """Main --help shows Knowledge Discovery command group."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Knowledge Discovery" in result.output

    def test_main_help_shows_model_execution_section(self):
        """Main --help shows Model Execution command group."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Model Execution" in result.output

    def test_main_help_shows_prefer_search_guidance(self):
        """Main --help includes guidance to prefer search over --answer."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Check for the guidance text
        assert "prefer" in result.output.lower() or "search" in result.output.lower()

    def test_main_help_shows_docs_and_knowledge_commands(self):
        """Main --help lists docs and knowledge commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "docs" in result.output
        assert "knowledge" in result.output

    def test_main_help_shows_usage_examples(self):
        """Main --help includes usage examples."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Should have some example commands
        assert "gspio" in result.output
```

**Step 2: Run test to verify it fails (may partially pass)**

Run: `uv run pytest tests/test_cli_help.py -v`
Expected: Some tests may fail if command grouping or guidance text not present

**Step 3: Update the main callback and app configuration**

Update the `app` definition and `main` callback in `gaspatchio_core/cli.py`:

```python
app = typer.Typer(
    name="gspio",
    help="""Gaspatchio CLI for running actuarial models and discovering knowledge.

This CLI serves two purposes:
1. Execute actuarial models (run-model, run-single-policy)
2. Search documentation and actuarial knowledge (docs, knowledge)

[bold]When building a model and you need to find:[/bold]
• How to use a Gaspatchio feature → [cyan]gspio docs "your question"[/cyan]
• Actuarial concepts or regulations → [cyan]gspio knowledge "your question"[/cyan]

[bold yellow]IMPORTANT: Always prefer search results (default) over --answer.[/bold yellow]
Search returns multiple excerpts you can evaluate against your
current context. Reserve --answer for quick summaries only when
you don't need to weigh multiple options.

[bold green]Examples:[/bold green]
    gspio docs "cumulative survival probability"              # ← preferred
    gspio docs "projection accessor methods"                  # ← preferred
    gspio docs "how do I shift time?" --answer                # ← only for quick summaries
    gspio knowledge "IFRS 17 contractual service margin"      # ← preferred
    gspio knowledge "what is risk adjustment?" --answer       # ← only for quick summaries
    gspio run-model model.py data.parquet --mode debug
    gspio run-single-policy model.py data.parquet "POL001"
""",
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)
```

Also update existing commands to use `rich_help_panel` for grouping:

For `run-model` and `run-single-policy`, add to the decorator:
```python
@app.command(
    name="run-model",
    help="Execute an actuarial model from a file",
    rich_help_panel="Model Execution",  # ADD THIS
)
```

```python
@app.command(
    name="run-single-policy",
    help="Execute an actuarial model for a single policy",
    rich_help_panel="Model Execution",  # ADD THIS
)
```

For `describe`:
```python
@app.command(
    name="describe",
    help="Describe the structure of a data file",
    rich_help_panel="Data Inspection",  # ADD THIS
)
```

For `calc-graph`:
```python
@app.command(
    name="calc-graph",
    help="Generate a calculation graph from a model run",
    rich_help_panel="Model Execution",  # ADD THIS
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_help.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add gaspatchio_core/cli.py tests/test_cli_help.py
git commit -m "feat(cli): enhance main --help with command groups and LLM guidance"
```

---

## Task 6: Run Full Test Suite and Type Checks

**Files:**
- All modified files

**Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS

**Step 2: Run type checks**

```bash
uv run mypy gaspatchio_core/api/
uv run pyright gaspatchio_core/api/
```

Expected: No errors

**Step 3: Verify CLI help output manually**

```bash
uv run gspio --help
uv run gspio docs --help
uv run gspio knowledge --help
```

Verify output matches design.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: ensure all tests pass and types check"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | API response models | `api/models.py`, `tests/api/test_models.py` |
| 2 | API client | `api/client.py`, `tests/api/test_client.py` |
| 3 | `docs` command | `cli.py`, `tests/test_cli_docs.py` |
| 4 | `knowledge` command | `cli.py`, `tests/test_cli_knowledge.py` |
| 5 | Enhanced main help | `cli.py`, `tests/test_cli_help.py` |
| 6 | Full test suite verification | All |

**Total commits:** 6
**Estimated time:** 1-2 hours following TDD strictly
