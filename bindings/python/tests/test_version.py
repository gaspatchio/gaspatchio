# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for gaspatchio.__version__ and its agreement with gspio --version.
# ABOUTME: Covers the installed version and a source checkout with no metadata.
"""``gaspatchio.__version__`` says what ``gspio --version`` says."""

import importlib.metadata

import pytest
from typer.testing import CliRunner

import gaspatchio
from gaspatchio import _version
from gaspatchio.cli import app


def test_version_matches_what_gspio_reports() -> None:
    """The attribute users reach for agrees with the CLI's own answer."""
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"Python package version: {gaspatchio.__version__}" in " ".join(
        result.stdout.split()
    )


def test_version_is_the_installed_distributions() -> None:
    """Read from the installed metadata, not written into the source."""
    assert gaspatchio.__version__ == importlib.metadata.version("gaspatchio")


def test_version_is_not_exported_by_star_import() -> None:
    """Module metadata, not API: ``from gaspatchio import *`` leaves it out."""
    assert "__version__" not in gaspatchio.__all__


def test_source_checkout_without_metadata_says_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no installed metadata the version is "unknown", as gspio says."""

    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(_version, "version", missing)

    assert _version.package_version() == "unknown"
