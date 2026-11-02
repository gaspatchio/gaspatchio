# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book holding policies with no run answers, on both engines, without a panic.

Two lines raised Rust panics -- a ``PanicException``, a ``BaseException``
that walks past ``except Exception`` -- over null outer lists, which 11.1.12,
11.1.19 and 11.1.25 answer:

- ``(af.pols * af.prem).round_sig_figs(3)``, with one side of the product
  absent for some policies, panicked the in-memory engine: ``called
  Result::unwrap() on an Err value: SchemaMismatch(... expected List, got
  f64 for series with name v)``. The run arithmetic leaves null carries
  values under its null, and Polars' evaluation of significant figures read
  them; an absent policy is now handed to the evaluation as an empty run
  and given its null back.
- ``af.qx.projection.cumulative_survival()``, over a book whose first two
  policies have no run, panicked the streaming engine: ``type Float64 is
  incompatible with expected type Null``. The opening value was prepended
  with ``concat_list`` and the run cut back; it is shifted along inside each
  policy's run instead, the same sequence.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_ENGINES = ["in-memory", "streaming"]


@pytest.mark.parametrize("engine", _ENGINES)
def test_significant_figures_of_a_product_with_an_absent_side(engine: str) -> None:
    book = pl.DataFrame(
        [
            pl.Series(
                "pols", [[1.0, 0.99], None, [1.0, 0.98]], dtype=pl.List(pl.Float64)
            ),
            pl.Series(
                "prem", [[12.345, 12.345], [5.0, 5.0], None], dtype=pl.List(pl.Float64)
            ),
        ]
    )
    af = ActuarialFrame(book)
    af.premium = (af.pols * af.prem).round_sig_figs(3)
    af.rounded = (af.pols * af.prem).round(2)
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    # By hand: 12.345 is 12.3 to three figures, 0.99 * 12.345 = 12.22155 is
    # 12.2; to two places 12.345 is a tie, to the even 12.34, and 12.22155 is
    # 12.22. A policy with either side absent has no run.
    assert out["premium"].to_list() == [[12.3, 12.2], None, None]
    assert out["rounded"].to_list() == [[12.34, 12.22], None, None]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("start_at", [None, 0.5])
@pytest.mark.parametrize("from_survival", [False, True])
def test_survival_over_a_book_opening_with_absent_policies(
    *, engine: str, start_at: float | None, from_survival: bool
) -> None:
    qx = [None, None, [0.1, 0.25], [0.001], [1.0, 0.25]]
    af = ActuarialFrame(pl.DataFrame({"qx": pl.Series(qx, dtype=pl.List(pl.Float64))}))
    kwargs: dict[str, object] = {"from_survival": from_survival}
    if start_at is not None:
        kwargs["start_at"] = start_at
    af.tpx = af.qx.projection.cumulative_survival(**kwargs)  # type: ignore[arg-type]
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    a = 1.0 if start_at is None else start_at
    # By hand, beginning of period: [a, f0, f0 * f1, ...] cut to the run's
    # length, f the survival factor (1 - q, or q itself from survival).
    if from_survival:
        expected = [None, None, [a, 0.1], [a], [a, 1.0]]
    else:
        expected = [None, None, [a, 0.9], [a], [a, 0.0]]
    assert out["tpx"].to_list() == expected
