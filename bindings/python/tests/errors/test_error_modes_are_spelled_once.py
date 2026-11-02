# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The error modes are spelled once, in ``gaspatchio.util``, and imported.

``AF_ERROR_MODE`` takes ``basic``, ``enhanced``, ``debug`` or ``off``. The
setter that validates it, the validation decorator and the collect-time
handlers each wrote the names out for themselves, and the test session kept
a copy of its own. Spelled in five places, the set one of them accepts and
the sets the others branch on could drift apart without a test noticing.
They now read three constants: every mode, the two that rewrite an error,
and the kill-switch.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import gaspatchio.errors.formatting_errors
import gaspatchio.errors.validation
import gaspatchio.util
from gaspatchio.util import set_error_mode

if TYPE_CHECKING:
    from types import ModuleType

_READERS = (gaspatchio.errors.validation, gaspatchio.errors.formatting_errors)


@pytest.mark.parametrize("module", _READERS, ids=lambda module: module.__name__)
def test_no_error_handler_spells_a_mode_out(module: ModuleType) -> None:
    """The handlers branch on the constants, never on a name written out."""
    source = Path(str(module.__file__)).read_text()

    assert '"enhanced"' not in source
    assert '"off"' not in source
    assert '"basic"' not in source


def test_the_setter_accepts_exactly_the_one_set() -> None:
    """set_error_mode() validates against the same set the handlers read."""
    from gaspatchio.util import (
        _ENHANCING_ERROR_MODES,
        _ERROR_MODE_OFF,
        _ERROR_MODES,
    )

    assert _ENHANCING_ERROR_MODES < _ERROR_MODES
    assert _ERROR_MODE_OFF in _ERROR_MODES - _ENHANCING_ERROR_MODES
    for mode in _ERROR_MODES:
        set_error_mode(mode)
        assert gaspatchio.util.get_error_mode() == mode
    with pytest.raises(ValueError, match="Invalid error mode"):
        set_error_mode("verbose")


@pytest.mark.parametrize(
    ("mode", "frame_mode", "rewritten"),
    [("basic", "debug", True), ("basic", "optimize", False), ("off", "debug", False)],
)
def test_basic_rewrites_a_missing_column_only_on_a_debug_frame(
    mode: str, frame_mode: str, *, rewritten: bool
) -> None:
    """What the comment over the modes says basic and off do, held to it."""
    import polars as pl

    from gaspatchio import ActuarialFrame

    set_error_mode(mode)
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0]}), mode=frame_mode)
    af["commission"] = pl.col("premum") * 0.1

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()

    assert ("Available columns are:" in str(caught.value)) is rewritten
