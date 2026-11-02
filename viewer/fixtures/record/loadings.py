# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The loadings the model applies, kept beside it as its own module."""


def margin() -> float:
    """Return the claims margin."""
    return 1.1


def inflation() -> float:
    """Return a year's expense inflation."""
    return 1.03
