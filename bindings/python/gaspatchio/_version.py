# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: The installed gaspatchio's version, read from its distribution metadata.
# ABOUTME: Shared by gaspatchio.__version__ and gspio --version so the two agree.
"""The installed gaspatchio's version, read from its distribution metadata."""

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    """Return the installed gaspatchio's version.

    Read from the distribution's metadata rather than written into the
    source, so it is the version that was actually installed.

    Returns:
        The version string, or ``"unknown"`` in a source checkout that was
        never installed and so carries no metadata.

    Examples:
        >>> package_version() != ""
        True

    """
    try:
        return version("gaspatchio")
    except PackageNotFoundError:
        return "unknown"
