# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Debug (traced) mode must produce the same numbers as optimize mode.

The setter both records each operation to the calculation log AND applies
it to the LazyFrame; collect()/profile() once replayed the records on top
of the already-applied frame. For fresh columns the replay recomputed the
same value; for self-referential assignments (af["x"] = af["x"] + 1) it
applied the operation twice, so the CLI's default debug mode produced
different numbers from production. The log is record-only metadata now.
"""

import polars as pl

from gaspatchio import ActuarialFrame


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"x": [10.0, 20.0, 30.0]}))


def test_self_referential_bracket_assignment_applies_once_under_tracing():
    af = _frame()
    af._traced_run = True
    af["x"] = af["x"] + 1
    out = af.collect()
    assert out["x"].to_list() == [11.0, 21.0, 31.0]


def test_self_referential_attribute_assignment_applies_once_under_tracing():
    af = _frame()
    af._traced_run = True
    af.x = af.x + 1
    out = af.collect()
    assert out["x"].to_list() == [11.0, 21.0, 31.0]


def test_tracing_and_non_tracing_collect_identical_frames():
    results = {}
    for tracing in (False, True):
        af = _frame()
        af._traced_run = tracing
        af["x"] = af["x"] + 1
        af["y"] = af["x"] * 2
        results[tracing] = af.collect()
    assert results[True].equals(results[False])


def test_profile_matches_collect_under_tracing():
    af = _frame()
    af._traced_run = True
    af["x"] = af["x"] + 1
    collected = af.collect()

    af2 = _frame()
    af2._traced_run = True
    af2["x"] = af2["x"] + 1
    profiled, _profile_info = af2.profile()

    assert profiled["x"].to_list() == collected["x"].to_list()


def test_error_boundary_diagnosis_replays_from_pre_op_baseline():
    """The error-boundary finder must not replay ops on the applied frame.

    _df already contains every recorded calculation; bisecting by replaying
    the window on top of it re-applies self-referential ops during diagnosis
    and misattributes the failing calculation. Diagnosis replays against the
    baseline the attribution window opened over.
    """
    from gaspatchio.errors.boundary import ErrorBoundaryFinder

    af = ActuarialFrame(pl.DataFrame({"x": [1, 2, 3]}))
    af._traced_run = True
    af["x"] = pl.col("x") + 1  # op 0: self-referential, valid
    af["bad"] = pl.col("missing") * 2  # op 1: fails lazily at collect

    try:
        af.collect()
        raised = None
    except Exception as e:  # noqa: BLE001
        raised = e
    assert raised is not None

    finder = ErrorBoundaryFinder(af, raised)
    failing_index, failing_op, last_good = finder.find_failing_operation()

    assert failing_index == 1
    assert failing_op.column == "bad"
    # The last good state applied op 0 exactly ONCE from the baseline.
    assert last_good["x"].to_list() == [2, 3, 4]


def test_the_log_still_records_operations_under_tracing():
    # The log is record-only, but it must still record — calc-graph
    # display and query-plan logging depend on it.
    af = _frame()
    af._traced_run = True
    af["y"] = af["x"] * 2
    assert [record.column for record in af._calculations] == ["y"]


_QUOTIENT_MODEL = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.coi_rate_unit = 1000.0
    af.coi_rate = af.coi_per_1000 / af.coi_rate_unit
    af.coi_rate_lit = af.coi_per_1000 / 1000
    af.coi_years = af.coi_per_1000 // 0.1
    af.monthly_rate = af.annual_rate / 12
    af.face_units = af.face / af.coi_rate_unit
    return af
"""


def test_cli_debug_and_optimize_modes_give_the_same_quotients(tmp_path):
    """``--mode`` changes diagnostics, never numbers (ul-r7 room, LEARNINGS L7).

    Debug mode collects through ``profile()``, which runs Polars' in-memory
    engine. There a per-period column divided by a constant column
    (``af.coi_rate_unit = 1000.0``) reached the float kernel that multiplies by
    the divisor's reciprocal -- 1.892 / 1000 read 0.001892 under debug and
    0.0018919999999999998 under optimize -- so the default mode of
    ``gspio run-model`` disagreed with production in the last place, and every
    COI charge downstream of it. A per-policy column over a number
    (``af.annual_rate / 12``, ``af.face / af.coi_rate_unit``) met the same
    kernel the same way.
    """
    from typer.testing import CliRunner

    from gaspatchio.cli import app

    model_path = tmp_path / "model.py"
    model_path.write_text(_QUOTIENT_MODEL)
    data_path = tmp_path / "model_points.parquet"
    pl.DataFrame(
        {
            "policy_id": ["A", "B", "C"],
            "coi_per_1000": [[1.892, 135.021, 0.3]] * 3,
            "annual_rate": [0.03, 0.06, 0.04],
            "face": [1.892, 135.021, 0.3],
        }
    ).write_parquet(data_path)

    runner = CliRunner()
    outputs = {}
    for mode in ("debug", "optimize"):
        out = tmp_path / f"{mode}.parquet"
        result = runner.invoke(
            app,
            [
                "run-model",
                str(model_path),
                str(data_path),
                "-o",
                str(out),
                "--mode",
                mode,
            ],
        )
        assert result.exit_code == 0, result.output
        outputs[mode] = pl.read_parquet(out)

    ieee = [1.892 / 1000, 135.021 / 1000, 0.3 / 1000]
    for mode, frame in outputs.items():
        assert frame["coi_rate"].to_list() == [ieee] * 3, mode
        assert frame["coi_rate_lit"].to_list() == [ieee] * 3, mode
        assert frame["monthly_rate"].to_list() == [0.03 / 12, 0.06 / 12, 0.04 / 12]
        assert frame["face_units"].to_list() == ieee, mode
    assert outputs["debug"].equals(outputs["optimize"])
