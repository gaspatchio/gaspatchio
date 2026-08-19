# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The fuzzy-match reference sets must track the API they describe.

``COMMON_VALIDATION_VALUES["projection_end_types"]`` is a hand-maintained copy
of the ``until=`` Literal in ``accessors/projection_frame.py``. It had already
drifted — it predated ``next_anniversary`` — and a comment saying "keep in
sync" is not a mechanism. These assertions are.
"""

import typing

from gaspatchio.accessors import projection_frame as _pf
from gaspatchio.errors.constants import COMMON_VALIDATION_VALUES
from gaspatchio.frame.base import ActuarialFrame

ProjectionFrameAccessor = _pf.ProjectionFrameAccessor


def _until_literal_values() -> set[str]:
    # `set` returns ActuarialFrame, imported under TYPE_CHECKING in that module,
    # so the module globals alone cannot resolve the annotations.
    hints = typing.get_type_hints(
        ProjectionFrameAccessor.set,
        globalns=vars(_pf),
        localns={"ActuarialFrame": ActuarialFrame},
    )
    until_hint = hints["until"]
    # `Literal[...] | None` — pull the Literal arm out of the union.
    for arm in typing.get_args(until_hint):
        args = typing.get_args(arm)
        if args and all(isinstance(a, str) for a in args):
            return set(args)
    msg = f"could not find the Literal arm of until=: {until_hint!r}"
    raise AssertionError(msg)


def test_projection_end_types_match_the_until_literal() -> None:
    """The reference set must equal the Literal it copies."""
    declared = set(COMMON_VALIDATION_VALUES["projection_end_types"])
    actual = _until_literal_values()
    assert declared == actual, (
        "errors/constants.py projection_end_types has drifted from the until= "
        f"Literal in projection_frame.py: only in constants {declared - actual}, "
        f"only in the Literal {actual - declared}"
    )
