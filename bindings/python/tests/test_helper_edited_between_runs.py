# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A helper edited between two runs in one process answers as its file now reads.

A modeller in a notebook edits ``loadings.py`` beside the model and runs the
model again. The model file was executed afresh on every load, but a helper
imported from the same directory stayed in Python's module cache, so the
second run computed with the old helper while the record -- which stamps the
files on disk -- named the edited one.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.runner import load_model_from_path

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = """\
import loadings


def main(af):
    af.prem = loadings.load(af.sa)
    return af
"""


def _premiums(model: Path) -> list[float]:
    main = load_model_from_path(model, "main")
    af = main(ActuarialFrame(pl.DataFrame({"sa": [500.0, 800.0]})))
    return af.collect()["prem"].to_list()


def test_an_edited_helper_is_run_as_it_now_reads(tmp_path: Path) -> None:
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    helper = tmp_path / "loadings.py"
    helper.write_text("def load(x):\n    return x * 1.05\n")
    assert _premiums(model) == [525.0, 840.0]
    helper.write_text("def load(x):\n    return x * 1.25\n")
    assert _premiums(model) == [625.0, 1000.0]


def test_a_helper_the_caller_imported_is_run_as_it_now_reads(tmp_path: Path) -> None:
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    helper = tmp_path / "loadings.py"
    helper.write_text("def load(x):\n    return x * 2.0\n")
    sys.path.insert(0, str(tmp_path))
    try:
        import loadings  # noqa: F401 - the notebook's own import

        helper.write_text("def load(x):\n    return x * 3.0\n")
        assert _premiums(model) == [1500.0, 2400.0]
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("loadings", None)


def test_an_accessor_a_helper_declares_takes_its_edited_definition(
    tmp_path: Path,
) -> None:
    accessor = """\
from gaspatchio.accessors.base import BaseColumnAccessor
from gaspatchio.frame.registry import register_accessor


@register_accessor("b3_loading", kind="column")
class Loading(BaseColumnAccessor):
    def times(self):
        return self._proxy * {factor}
"""
    model = tmp_path / "model.py"
    model.write_text(
        "import b3_accessors\n\n\n"
        "def main(af):\n    af.prem = af.sa.b3_loading.times()\n    return af\n"
    )
    helper = tmp_path / "b3_accessors.py"
    helper.write_text(accessor.format(factor="1.5"))
    assert _premiums(model) == [750.0, 1200.0]
    helper.write_text(accessor.format(factor="2.0"))
    assert _premiums(model) == [1000.0, 1600.0]
