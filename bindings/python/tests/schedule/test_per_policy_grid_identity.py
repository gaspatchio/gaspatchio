# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy grid's identity is its rule, never another policy's horizon.

On a per-policy axis -- a term column, or a maximum age read against each
policy's issue age -- every policy runs to its own horizon, and no policy's
value depends on how long any other policy runs. The grid's recipe therefore
states no ``n_periods``: the identity is the kind, the cadence, the calendar,
the shared start, the horizon kind and the column or age. So a model's
``graph_fingerprint`` is one figure whatever other policies share the book,
when one policy runs alone, and at every batch size; and a change of the rule
still moves it.

The hand values: policy P1 (term 12 months, 100 a month, 3% a year) discounts
on ``t_years`` to 1280.982466692113 in every book it sits in; Q1 (issue age
95, 50 a year to age 100 at 4%) is ``math.fsum(50 * 1.04 ** -k, k = 0..5)``,
272.5911165508102.
"""

from __future__ import annotations

import datetime
import json
import math
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import Sum, run_aggregated

if TYPE_CHECKING:
    from pathlib import Path

_VALUATION = datetime.date(2025, 1, 1)
_P1_PV = 1280.982466692113
_Q1_PV = 272.5911165508102


def _term_model(
    af: ActuarialFrame, *, column: str = "term_months", frequency: str = "monthly"
) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=_VALUATION,
        until="term_months",
        until_value=column,
        frequency=frequency,
    )
    af.t_years = af.projection.t_years()
    af.disc = (1.0 + af.rate) ** (-af.t_years)
    af.pv = (af.cf * af.disc).list.sum()
    return af


def _age_model(af: ActuarialFrame, *, age: int = 100) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=_VALUATION,
        until="maximum_age",
        until_value=age,
        frequency="annual",
    )
    af.t = af.projection.t_years()
    af.v = (1.0 + af.i) ** (-af.t)
    af.pv = (af.prem * af.v).list.sum()
    return af


def _term_book(terms: list[int]) -> pl.DataFrame:
    n = len(terms)
    return pl.DataFrame(
        {
            "id": [f"P{k + 1}" for k in range(n)],
            "term_months": terms,
            "cf": [100.0] * n,
            "rate": [0.03] * n,
        }
    )


def _age_book(ages: list[int]) -> pl.DataFrame:
    n = len(ages)
    return pl.DataFrame(
        {
            "pid": [f"Q{k}" for k in range(n)],
            "issue_age": ages,
            "prem": [50.0] * n,
            "i": [0.04] * n,
        }
    )


def _audit(af: ActuarialFrame, book: pl.DataFrame) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(
        GraphExporter(af, data_columns=book.columns).export(profile="audit")
    )
    return doc


def _schedules(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry["payload"]
        for entry in doc.get("assumptions", [])
        if entry.get("kind") == "schedule"
    ]


def test_the_hand_values() -> None:
    """The hand values the module pins are what the arithmetic gives."""
    assert math.fsum(50.0 * 1.04 ** (-k) for k in range(6)) == _Q1_PV
    p1 = math.fsum(100.0 * 1.03 ** (-(k / 12)) for k in range(13))
    assert p1 == pytest.approx(_P1_PV, rel=1e-15)


def test_a_term_grid_is_one_figure_across_other_policies_terms() -> None:
    """P2's term, and P1 running alone, leave the model's identity where it was."""
    books = {
        "base": _term_book([12, 24]),
        "P2 term 24 -> 36": _term_book([12, 36]),
        "P1 alone": _term_book([12]),
    }
    figures = {}
    for name, book in books.items():
        af = _term_model(ActuarialFrame(book))
        doc = _audit(af, book)
        (payload,) = _schedules(doc)
        assert payload["kind"] == "per_policy_grid"
        assert "n_periods" not in payload
        result = af.collect()
        assert result["pv"][0] == _P1_PV
        figures[name] = (doc["graph_fingerprint"], doc["formulas_fingerprint"])
    assert len(set(figures.values())) == 1, figures


def test_a_maximum_age_grid_is_one_figure_across_other_policies_ages() -> None:
    """The youngest life in the book does not move a maximum-age grid's identity."""
    books = {
        "ages 90, 95": _age_book([90, 95]),
        "ages 80, 95": _age_book([80, 95]),
        "Q1 alone": _age_book([90, 95]).tail(1),
    }
    figures = set()
    for book in books.values():
        af = _age_model(ActuarialFrame(book))
        doc = _audit(af, book)
        (payload,) = _schedules(doc)
        assert payload["until_kind"] == "maximum_age"
        assert "n_periods" not in payload
        result = af.collect()
        assert result.filter(pl.col("pid") == "Q1")["pv"].item() == _Q1_PV
        figures.add(doc["graph_fingerprint"])
    assert len(figures) == 1, figures


def test_a_change_of_the_rule_still_moves_the_figure() -> None:
    """The column, the cadence and the age are the rule, and each one moves it."""
    base_book = _term_book([12, 24])
    base = _audit(_term_model(ActuarialFrame(base_book)), base_book)
    renamed_book = base_book.rename({"term_months": "tm"})
    renamed = _audit(
        _term_model(ActuarialFrame(renamed_book), column="tm"), renamed_book
    )
    quarterly = _audit(
        _term_model(ActuarialFrame(base_book), frequency="quarterly"), base_book
    )
    assert len({d["graph_fingerprint"] for d in (base, renamed, quarterly)}) == 3

    ages = _age_book([90, 95])
    to_100 = _audit(_age_model(ActuarialFrame(ages)), ages)
    to_99 = _audit(_age_model(ActuarialFrame(ages), age=99), ages)
    assert to_100["graph_fingerprint"] != to_99["graph_fingerprint"]


@pytest.mark.parametrize("batch_size", [1, 2, 4])
def test_a_batched_audit_record_states_the_whole_book_figure(
    tmp_path: Path, batch_size: int
) -> None:
    """At batch size 1, 2 and N the audit record carries one figure, never null."""
    book = _age_book([80, 95, 81, 94])
    whole = _audit(_age_model(ActuarialFrame(book)), book)["graph_fingerprint"]
    record_path = tmp_path / f"audit-{batch_size}.json"
    run_aggregated(
        _age_model,
        book,
        [Sum("pv").alias("tot")],
        batch_size=batch_size,
        audit=record_path,
    )
    record = json.loads(record_path.read_text())
    assert record["graph_fingerprint"] == whole
    # The longest horizon is a fact of the run: 80 to 100 annually, 21 boundaries.
    assert record["run_metadata"]["n_periods"] == 21


def test_the_grid_takes_no_period_count() -> None:
    """``from_per_policy_grid`` states no ``n_periods``, and has none to read."""
    grid = Schedule.from_per_policy_grid(
        start_date=_VALUATION,
        frequency="1M",
        until_kind="term_months",
        until_value_column="term_months",
    )
    assert grid.n_periods is None
    assert "n_periods" not in grid.canonical_form()
    with pytest.raises(TypeError):
        Schedule.from_per_policy_grid(  # type: ignore[call-arg]
            start_date=_VALUATION,
            n_periods=24,
            frequency="1M",
            until_kind="term_months",
            until_value_column="term_months",
        )


@pytest.mark.parametrize(
    ("method", "fill"),
    [("is_in_force", True), ("contract_boundary", False)],
)
def test_a_book_of_zero_terms_first_leaves_the_next_books_masks_whole(
    method: str, *, fill: bool
) -> None:
    """One process, one rule, two books: the second book's masks are its own.

    The two books' grids share one recipe, so they share one registered
    schedule. Were a lowering still to test a period count before taking
    the per-policy branch, the first book's (nought) would answer for the
    second, and terms 12 and 24 would read ``[0, 0]``.
    """

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            valuation_date=_VALUATION,
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.mask = getattr(af.projection, method)()
        return af

    zero = model(
        ActuarialFrame(pl.DataFrame({"id": ["Z1", "Z2"], "term_months": [0, 0]}))
    )
    assert [len(m) for m in zero.collect()["mask"]] == [0, 0]
    terms = model(
        ActuarialFrame(pl.DataFrame({"id": ["P1", "P2"], "term_months": [12, 24]}))
    )
    masks = terms.collect()["mask"].to_list()
    assert masks == [[fill] * 12, [fill] * 24]
