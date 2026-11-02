# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Docstrings state what the methods do, as measured, in the words people search.

Each assertion is a sentence a probe proved false or missing on the 1.0
build: that the two timing conventions agree at constant rates (they differ
by a period at any rate), that ``prospective_value`` steps the beginning-of-
period recursion (its default is end of period, summed in one pass), that
``projection.set`` keeps its start date (the synthetic form moves any start,
the 1st included, to month-end), and the retrieval words a converter
searched for and missed.
"""

from __future__ import annotations

import inspect

from gaspatchio.accessors.projection import ProjectionColumnAccessor
from gaspatchio.accessors.projection_frame import ProjectionFrameAccessor
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.rollforward._builder import _StateHandle


def _doc(obj: object) -> str:
    return " ".join((inspect.getdoc(obj) or "").split())


def test_no_timing_docstring_says_constant_rates_make_the_conventions_agree() -> None:
    survival = _doc(ProjectionColumnAccessor.cumulative_survival)
    nar = _doc(_StateHandle.deduct_nar)
    assert "identical values" not in survival
    assert "do not give the same values, even at a flat rate" in survival
    assert "the two agree" not in nar
    assert "charge different amounts even at flat rates" in nar


def test_prospective_value_states_its_default_formula() -> None:
    doc = _doc(ProjectionColumnAccessor.prospective_value)
    assert "PV(t) = CF(t) + PV(t+1) * v(t)" not in doc
    assert "a discounted reverse cumulative sum" in doc
    assert "PV(t) = v(t) * (CF(t) + PV(t+1))" in doc


def test_set_says_a_synthetic_grid_starts_at_month_end() -> None:
    doc = _doc(ProjectionFrameAccessor.set)
    assert "the 1st included, the grid starts on that month's last day" in doc
    assert "``num_proj_months`` is the number of period boundaries" in doc


def test_the_searched_for_words_are_in_when_to_use() -> None:
    assert "standard normal cumulative distribution function" in _doc(
        ColumnProxy.norm_cdf
    )
    assert "error function" in _doc(ColumnProxy.norm_cdf)
    assert "zeroized" in _doc(ProjectionColumnAccessor.accumulate)
    assert "The year fraction of each period" in _doc(
        ProjectionFrameAccessor.year_fractions
    )
