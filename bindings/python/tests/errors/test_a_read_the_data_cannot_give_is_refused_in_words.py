# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A position a run does not hold, and text that is not a date, are refused in words.

Both refusals are right (sections 11.1.22 and 11.1.7) and both came in
Polars' words. ``af.av.list.get(36)`` over a book holding a 24-period policy
said ``get index is out of bounds`` above an expression dump, named neither
the policy nor a way through, and said the same of a missing run and a
missing position. ``af.t.str.to_date("%Y-%m-%d")`` over ``"31/12/2025"``
said ``conversion from `str` to `date` failed`` with Polars' own advice, and
under the default streaming engine lost the line that wrote it. Each now
opens with the framework's sentence -- the column, what was not there, the
way through -- names the line on either engine, and keeps the engine's text
beneath it.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_ENGINES = ["in-memory", "streaming"]


def _runs(av: pl.Series, k: pl.Series | None = None) -> ActuarialFrame:
    columns = {"policy_id": ["P1", "P2"], "av": av}
    if k is not None:
        columns["k"] = k
    return ActuarialFrame(pl.DataFrame(columns))


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_position_past_one_policy_s_run_names_the_run_the_policy_and_the_move(
    engine: str,
) -> None:
    af = _runs(pl.Series([[1.0] * 40, [2.0] * 24]))
    af.last_av = af.av.list.get(36)

    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine=engine)

    said = str(refused.value)
    assert said.startswith(
        "A position is read from column 'av' with list.get that one policy's run "
        "does not hold"
    )
    assert "af.av.list.len()" in said
    assert "Policy:         policy_id=P2 (row 1)" in said
    assert "Failing column: 'last_av'" in said
    assert "index is out of bounds" in said


@pytest.mark.parametrize(
    ("av", "k"),
    [
        (pl.Series([[1.0] * 3, None], dtype=pl.List(pl.Float64)), None),
        (pl.Series([[1.0] * 3, [2.0] * 3]), pl.Series([1, None], dtype=pl.Int64)),
    ],
    ids=["a missing run", "a missing position"],
)
def test_a_missing_run_or_position_is_named_with_its_policy(
    av: pl.Series, k: pl.Series | None
) -> None:
    af = _runs(av, k)
    af.read = af.av.list.get(af.k if k is not None else 0)

    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine="streaming")

    said = str(refused.value)
    assert said.startswith("A position is read from column 'av' with list.get")
    assert "fill a missing run or position" in said
    assert "Policy:         policy_id=P2 (row 1)" in said


@pytest.mark.parametrize("engine", _ENGINES)
def test_text_that_is_not_a_date_names_the_column_the_value_and_the_format(
    engine: str,
) -> None:
    af = ActuarialFrame(pl.DataFrame({"issue_text": ["2025-01-01", "31/12/2025"]}))
    af.issue = af.issue_text.str.to_date("%Y-%m-%d")

    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect(engine=engine)

    said = str(refused.value)
    assert said.startswith(
        "Column 'issue_text' holds text that does not read as a date in the "
        'format the line gives -- "31/12/2025" among them'
    )
    assert "strict=False" in said
    assert "Failing column: 'issue'" in said
    assert "conversion from `str` to `date` failed" in said


def test_a_position_past_the_replay_s_head_still_names_its_line() -> None:
    """The refused policy is the 10,001st, past the rows a replay reads."""
    policies = 10_001
    runs = [[1.0] * 40] * (policies - 1) + [[2.0] * 24]
    af = ActuarialFrame(pl.DataFrame({"av": pl.Series(runs)}))
    af.last_av = af.av.list.get(36)

    with pytest.raises(pl.exceptions.ComputeError) as refused:
        af.collect(engine="streaming")

    assert "Failing column: 'last_av'" in str(refused.value)


def test_text_past_the_replay_s_head_still_names_its_line() -> None:
    policies = 10_001
    texts = ["2025-01-01"] * (policies - 1) + ["31/12/2025"]
    af = ActuarialFrame(pl.DataFrame({"issue_text": texts}))
    af.issue = af.issue_text.str.to_date("%Y-%m-%d")

    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect(engine="streaming")

    assert "Failing column: 'issue'" in str(refused.value)
