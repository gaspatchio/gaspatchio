# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests that docs searches ask for the docs of the gaspatchio that is
# ABOUTME: installed, so an older install is not answered with a newer API.
"""Tests that docs requests carry the installed gaspatchio version."""

from unittest.mock import MagicMock, patch

import pytest

from gaspatchio.api.client import KnowledgeAPIClient
from gaspatchio.api.models import DocsAnswerResponse, DocsSearchResponse

SEARCH = {
    "results": [],
    "query": "q",
    "count": 0,
    "search_type": "hybrid",
    "took_ms": 1.0,
}
ANSWER = {
    "answer": "a",
    "sources": [],
    "query": "q",
    "model": "m",
    "tokens_used": 1,
    "took_ms": 1.0,
}


def _ok(body: dict) -> MagicMock:
    return MagicMock(status_code=200, json=MagicMock(return_value=body))


@pytest.mark.parametrize(("method", "body"), [("search_docs", SEARCH), ("answer_docs", ANSWER)])
@patch("gaspatchio.api.client.package_version", return_value="1.0.0rc1")
@patch("httpx.Client.post")
def test_docs_requests_send_the_installed_version(mock_post, _version, method, body):
    mock_post.return_value = _ok(body)

    getattr(KnowledgeAPIClient(), method)("projection")

    assert mock_post.call_args.kwargs["json"]["version"] == "1.0.0rc1"


@pytest.mark.parametrize(("method", "body"), [("search_docs", SEARCH), ("answer_docs", ANSWER)])
@patch("gaspatchio.api.client.package_version", return_value="1.0.0rc1")
@patch("httpx.Client.post")
def test_an_explicit_version_wins(mock_post, _version, method, body):
    mock_post.return_value = _ok(body)

    getattr(KnowledgeAPIClient(), method)("projection", version="0.9.0")

    assert mock_post.call_args.kwargs["json"]["version"] == "0.9.0"


@pytest.mark.parametrize("installed", ["unknown", "1.0.0 dirty", "x" * 65, ""])
@patch("httpx.Client.post")
def test_a_version_the_index_cannot_name_is_not_sent(mock_post, installed):
    """An uninstalled checkout says "unknown"; asking for it would only earn a note."""
    mock_post.return_value = _ok(SEARCH)

    with patch("gaspatchio.api.client.package_version", return_value=installed):
        KnowledgeAPIClient().search_docs("projection")

    assert "version" not in mock_post.call_args.kwargs["json"]


@patch("httpx.Client.post")
def test_knowledge_searches_carry_no_version(mock_post):
    """The actuarial knowledge base is not tied to a gaspatchio version."""
    mock_post.return_value = _ok({**SEARCH, "retrieval_mode": "chunks"})

    KnowledgeAPIClient().search_knowledge("CSM")

    assert "version" not in mock_post.call_args.kwargs["json"]


def test_responses_carry_the_version_served_and_why():
    search = DocsSearchResponse.model_validate(
        {**SEARCH, "version": "0.9.0", "version_note": "nearest older"}
    )
    answer = DocsAnswerResponse.model_validate({**ANSWER, "version": "0.9.0"})

    assert (search.version, search.version_note) == ("0.9.0", "nearest older")
    assert (answer.version, answer.version_note) == ("0.9.0", None)


def test_a_server_that_predates_versions_still_parses():
    search = DocsSearchResponse.model_validate(SEARCH)

    assert search.version is None and search.version_note is None
