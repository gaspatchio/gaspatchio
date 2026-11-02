# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A tail direction or level that would be read as another is refused by name.

``CTE``/``PeriodCTE`` compared ``direction`` with ``"upper"`` and averaged the
lower tail for anything else, so ``direction="Upper"`` (or ``up`` from YAML)
answered an SCR 33 times too small. ``Quantile(99.5)`` -- a percent for a
probability -- answered the largest value, ``Quantile(-0.2)`` extrapolated
below the smallest, and ``CTE(level=1.5)`` answered a number. Each is refused
where the aggregator is built, from code and from YAML alike.
"""

from __future__ import annotations

import pytest

from gaspatchio.scenarios import CTE, PeriodCTE, PeriodQuantile, Quantile
from gaspatchio.scenarios._config import parse_aggregations


@pytest.mark.parametrize("direction", ["Upper", "UPPER", "up", "sideways", "upper "])
@pytest.mark.parametrize("kind", [CTE, PeriodCTE])
def test_a_direction_other_than_upper_or_lower_is_refused(
    kind: type, direction: str
) -> None:
    with pytest.raises(ValueError, match=r"direction is \"upper\""):
        kind("loss", level=0.01, direction=direction)


@pytest.mark.parametrize("levels", [(99.5,), (-0.2,), (0.5, 1.5), (float("nan"),)])
@pytest.mark.parametrize("kind", [Quantile, PeriodQuantile])
def test_a_quantile_level_outside_zero_to_one_is_refused(
    kind: type, levels: tuple[float, ...]
) -> None:
    with pytest.raises(ValueError, match=r"a quantile level is a probability"):
        kind("loss", levels=levels)


@pytest.mark.parametrize("level", [0.0, -0.2, 1.5, float("nan"), True])
@pytest.mark.parametrize("kind", [CTE, PeriodCTE])
def test_a_tail_level_outside_zero_to_one_is_refused(kind: type, level: float) -> None:
    with pytest.raises(ValueError, match=r"a tail level is the probability"):
        kind("loss", level=level)


def test_yaml_refuses_a_misspelt_direction() -> None:
    entry = {"kind": "CTE", "alias": "scr", "column": "loss", "direction": "up"}
    with pytest.raises(ValueError, match=r"CTE\(direction='up'\)"):
        parse_aggregations([entry])


@pytest.mark.parametrize("kind", [CTE, PeriodCTE])
def test_the_spellings_and_bounds_that_mean_something_still_build(kind: type) -> None:
    for direction in ("upper", "lower"):
        for level in (0.005, 1.0):
            kind("loss", level=level, direction=direction)
    for quantile in (Quantile, PeriodQuantile):
        quantile("loss", levels=(0.0, 0.5, 0.995, 1.0))
