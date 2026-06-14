# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Locks in the deletion of af.date.create_projection_timeline().

If this test fails (i.e. the method is still present), the migration
has been silently regressed.
"""

from __future__ import annotations

import pytest

from gaspatchio_core import ActuarialFrame


def test_create_projection_timeline_attribute_error() -> None:
    af = ActuarialFrame({"id": ["P1"], "issue_age": [30]})
    with pytest.raises(AttributeError):
        af.date.create_projection_timeline  # noqa: B018
