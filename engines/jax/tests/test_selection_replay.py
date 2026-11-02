# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A replay values exactly the policies the model valued (spec section 7.6).

The adversarial review's model (``scratch/w5-adv/m1``): four term policies, P4
lapsed, a filter on ``status == "IF"`` and a product table joined on. Before
the ruling the executable artifact carried no selection, so this engine valued
all four rows -- net cash flow at t=0 came out -89.35174 where the model said
-69.94987, the difference P4's own -19.40187 -- under the model's own
``graph_fingerprint``. Each test here fails on the tree before the ruling.
"""

from __future__ import annotations

import datetime
import json
import math
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.engines.protocol import FrameSink, digest_of_inputs
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import PeriodSum
from gaspatchio_jax.engine import JaxEngine

if TYPE_CHECKING:
    from collections.abc import Callable

BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3", "P4"],
        "issue_age": [30, 45, 60, 52],
        "sum_assured": [100_000.0, 250_000.0, 50_000.0, 80_000.0],
        "term_m": [120, 60, 24, 36],
        "status": ["IF", "IF", "IF", "LAPSED"],
        "product": ["T10", "T5", "T2", "T3"],
    }
)
PRODUCTS = pl.DataFrame(
    {"product": ["T10", "T5", "T2", "T3"], "prem_rate": [0.002, 0.003, 0.004, 0.005]}
)
MORTALITY = pl.DataFrame(
    {
        "age": list(range(20, 121)),
        "qx": [min(1.0, 0.0005 * 1.09 ** (age - 20)) for age in range(20, 121)],
    }
)


def _p4_net_cf_at_0() -> float:
    """Return P4's net cash flow at t=0 by hand: premium less expected claims."""
    qx = 0.0005 * 1.09**32
    monthly_q = 1 - (1 - qx) ** (1 / 12)
    return 80_000 * 0.005 / 12 - 80_000 * monthly_q


def _model(
    select: Callable[[ActuarialFrame], ActuarialFrame],
    *,
    drop_status: bool = False,
) -> ActuarialFrame:
    mortality = Table(
        name="selection_replay_mortality",
        source=MORTALITY,
        dimensions={"age": "age"},
        value="qx",
    )
    af = select(ActuarialFrame(BOOK))
    af = af.join(PRODUCTS, on="product", how="left")
    af = af.materialize()
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )
    af.attained_age = af.issue_age + af.month // 12
    af.qx = mortality.lookup(age=af.attained_age)
    af.q_m = 1 - (1 - af.qx) ** (1 / 12)
    af.surv = af.q_m.projection.cumulative_survival()
    af.claims = af.sum_assured * af.q_m * af.surv
    af.prem = af.sum_assured * af.prem_rate / 12 * af.surv
    af.net_cf = af.prem - af.claims
    if drop_status:
        af = af.drop("status")
    return af


def _in_force(af: ActuarialFrame) -> ActuarialFrame:
    return af.filter(pl.col("status") == "IF")


def _executable(af: ActuarialFrame) -> dict[str, object]:
    return json.loads(GraphExporter(af).export(profile="executable"))


def _run(document: dict[str, object]) -> pl.DataFrame:
    return JaxEngine().run(document, BOOK, FrameSink()).columns


def _net_cf_total_at_0(document: dict[str, object]) -> float:
    result = JaxEngine().aggregate(
        document, BOOK, [PeriodSum("net_cf").alias("net_cf")]
    )
    return float(result.aggregations["net_cf"][0])


def test_the_engine_values_only_the_policies_the_model_kept() -> None:
    af = _model(_in_force)
    document = _executable(af)
    model_rows = af.collect()["policy_id"].to_list()
    result = _run(document)
    ids = [name for name, node in _ids(document).items() if node == "policy_id"]
    assert model_rows == ["P1", "P2", "P3"]
    assert result[ids[0]].to_list() == model_rows


def _ids(document: dict[str, object]) -> dict[str, str]:
    return {
        str(node["id"]): str(node["column"])  # type: ignore[index]
        for node in document["nodes"]  # type: ignore[attr-defined]
        if node["in_final_schema"]  # type: ignore[index]
    }


def test_the_folded_total_excludes_the_lapsed_policy_by_its_hand_value() -> None:
    selected = _net_cf_total_at_0(_executable(_model(_in_force)))
    everything = _net_cf_total_at_0(_executable(_model(lambda af: af)))
    assert math.isclose(everything - selected, _p4_net_cf_at_0(), rel_tol=1e-12)
    assert math.isclose(selected, -69.94986998332729, rel_tol=1e-12)


def test_the_result_stamps_the_book_it_was_handed_so_record_and_result_match() -> None:
    document = _executable(_model(_in_force, drop_status=True))
    result = JaxEngine().run(document, BOOK, FrameSink())
    columns = document["book"]["columns"]  # type: ignore[index]
    assert "status" in columns
    assert result.manifest.inputs_digest == digest_of_inputs(BOOK, columns)


def test_a_semi_join_s_right_side_travels_and_is_replayed() -> None:
    def kept(af: ActuarialFrame) -> ActuarialFrame:
        return af.join(
            pl.DataFrame({"product": ["T10", "T2"]}), on="product", how="semi"
        )

    af = _model(kept)
    result = _run(_executable(af))
    ids = [
        name for name, column in _ids(_executable(af)).items() if column == "policy_id"
    ]
    assert result[ids[0]].to_list() == ["P1", "P3"]


def test_the_frame_s_engine_door_selects_from_the_book_even_after_a_drop() -> None:
    af = _model(_in_force, drop_status=True)
    on_jax = af.collect(engine="jax")
    assert on_jax["policy_id"].to_list() == ["P1", "P2", "P3"]


def test_a_book_without_the_column_the_selection_reads_is_refused() -> None:
    document = _executable(_model(_in_force, drop_status=True))
    with pytest.raises(EngineRefusal, match="status"):
        JaxEngine().run(document, BOOK.drop("status"), FrameSink())


def _in_force_premium(af: ActuarialFrame) -> ActuarialFrame:
    af = af.filter(af.status == "IF")
    af.premium = af.sum_assured * 0.002
    return af


@pytest.mark.parametrize("engine", [None, "jax"])
def test_the_fold_counts_the_policies_the_model_valued_on_either_engine(
    engine: str | None,
) -> None:
    """Three of four policies are in force; both engines say three, and 800 by hand."""
    from gaspatchio.scenarios import Sum, run_aggregated

    result = run_aggregated(
        _in_force_premium, BOOK, [Sum("premium").alias("premium")], engine=engine
    )
    assert result.n_policies == 3
    assert math.isclose(result.premium, 0.002 * (100_000 + 250_000 + 50_000))


def test_a_model_that_only_selects_is_replayed_by_the_engine() -> None:
    """A model whose one step is the selection exports, and the engine keeps P1-P3."""
    af = ActuarialFrame(BOOK).filter(pl.col("status") == "IF")
    columns = _run(_executable(af))
    assert columns["policy_id"].to_list() == ["P1", "P2", "P3"]
    assert af.collect(engine="jax")["policy_id"].to_list() == ["P1", "P2", "P3"]


def test_a_filter_on_a_rollforward_state_is_refused_at_the_engine_door_by_name() -> (
    None
):
    """A replay selects from the book before it projects; a state is calculated."""
    from gaspatchio import compile_rollforward

    af = ActuarialFrame(
        {
            "policy_id": ["P001", "P002"],
            "init": [100.0, -50.0],
            "term_months": [2, 2],
            "premium": [[10.0, 10.0], [10.0, 10.0]],
        }
    )
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 31),
        until="term_months",
        until_value="term_months",
        frequency="monthly",
        per_policy=True,
    )
    builder = af.projection.rollforward(states={"av": af["init"]})
    builder["av"].add(af["premium"])
    af = af.filter(compile_rollforward(builder).expr_for("av").list.get(0) > 0)
    af.y = af.init * 2.0
    assert af.collect()["policy_id"].to_list() == ["P001"]
    with pytest.raises(
        ValueError,
        match=r"selection:1 \(.*\) chooses rows on the rollforward state 'av' "
        r"\(rollforward:.*calculates",
    ):
        af.collect(engine="jax")
