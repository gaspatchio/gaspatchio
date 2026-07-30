# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Collect-time errors must name the offending column.

Regression test for #39. A lazy chain failing at collect() surfaced a raw
Polars error ("list lengths differed at index 0: 6 != 3") that never said
WHICH assigned column produced it — a long hunt in a 50-column model.
Assign-time errors were already attributed; collect-time ones were not.

The fallback contract matters as much as the feature: if attribution is
ambiguous the ORIGINAL error must pass through untouched. A wrong column name
costs more than no column name.
"""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode — earlier suites leak AF_ERROR_MODE.

    ``set_error_mode()`` writes the environment variable process-wide, and
    several pre-existing error-handling suites (which sort before this file)
    leave it at ``basic``/``off``. These tests exercise the default
    ``enhanced`` behaviour, so they pin it; the opt-out test overrides it
    per-test.
    """
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def _ragged_frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
                "three": [[1.0, 2.0, 3.0]],
            }
        )
    )


def test_shape_error_names_the_offending_column() -> None:
    """The reported case: a ragged list op fails without naming its column."""
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()
    assert "mismatched" in str(excinfo.value)


def test_attribution_picks_the_right_column_in_a_chain() -> None:
    """Only the broken column is named — never its healthy neighbours."""
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af.fine_two = af.three + 1.0
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
    assert "fine_two" not in message


def test_unattributable_error_passes_through_unchanged() -> None:
    """The fallback contract: no recorded assignment, no decoration.

    The broken operation is baked into the input plan before the
    ActuarialFrame ever sees it, so nothing was recorded and replay has
    nothing to name. The original Polars error must arrive untouched —
    a wrong column name costs more than no column name.
    """
    lf = pl.LazyFrame(
        {
            "policy_id": [1],
            "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
            "three": [[1.0, 2.0, 3.0]],
        }
    ).with_columns((pl.col("six") * pl.col("three")).alias("baked_in"))
    af = ActuarialFrame(lf)
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_misspelled_column_keeps_friendly_formatting() -> None:
    """The most common user error must keep its did-you-mean panel.

    Always-on recording made the graph truthy on every frame, which routed
    ordinary missing-column errors into the enhanced compilation path; its
    builder crashed on the bare tuples and re-raised the RAW Polars error —
    losing the available-columns panel for a simple misspelling.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "premium": [100.0]}))
    af.doubled = af["premum"] * 2.0
    with pytest.raises(Exception, match="premum") as excinfo:
        af.collect()
    assert "Available columns" in str(excinfo.value)


def test_traced_graph_survives_structural_ops_but_attribution_refuses() -> None:
    """After tracing, a structural op preserves the graph and poisons replay.

    Two contracts at once: calc-graph export needs the TracedOperation
    records even after the trace decorator switched tracing off, and
    attribution must refuse a graph whose baseline no longer matches the
    live plan — replaying it names the wrong column with full confidence.
    """
    af = _ragged_frame()
    af._tracing = True  # noqa: SLF001 — simulating the trace decorator's lifecycle
    af.fine = af.six * 2.0
    af._tracing = False  # noqa: SLF001
    af = af.filter(pl.col("policy_id") == 1)
    graph = af._computation_graph  # noqa: SLF001 — asserting the preserved record
    assert any(not isinstance(op, tuple) for op in graph)
    assert af._attribution_unsound is True  # noqa: SLF001

    af.broken = af.six - af.three
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_multi_expression_batch_never_blames_a_healthy_sibling() -> None:
    """A with_columns batch is ONE step live but would replay sequentially.

    Every expression in a batch sees the pre-batch frame, so ``y`` below
    reads the OLD 3-element ``x`` and is healthy. Sequential replay would
    feed it the NEW 6-element ``x``, reproduce a ShapeError, and blame it.
    The batch restarts the window instead; the genuinely broken column
    assigned afterwards is still attributed.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0] * 6],
                "three": [[1.0] * 3],
                "x": [[9.0] * 3],
            }
        )
    )
    af = af.with_columns(
        pl.col("six").alias("x"),
        (pl.col("x") - pl.col("three")).alias("y"),
    )
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "Failing column: 'broken'" in message
    assert "'y'" not in message


def test_valid_self_referential_dtype_change_is_not_blamed() -> None:
    """Replay must never re-apply an op already present in the good prefix.

    ``a`` narrows itself List(f64) -> f64 — valid exactly once. The exact
    scan used to start one op EARLY on a frame that already contained it,
    double-applying the narrowing, which raises the same class as the real
    bug and got ``a`` blamed for ``bad``'s error.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "a": [[7.0, 8.0]],
                "c": [1.5],
            }
        )
    )
    af["a"] = pl.col("a").list.get(0)
    af["bad"] = pl.col("c").list.get(0)
    with pytest.raises(Exception, match="get") as excinfo:
        af.collect()
    message = str(excinfo.value)
    if "Failing column" in message:
        assert "Failing column: 'bad'" in message
        assert "Failing column: 'a'" not in message


def test_window_clears_after_successful_collect() -> None:
    """A successful collect closes the window — no unbounded graph growth."""
    af = _ragged_frame()
    af.fine = af.six * 2.0
    af.collect()
    assert af._computation_graph == []  # noqa: SLF001 — the property under test


def test_error_mode_optout_disables_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AF_ERROR_MODE=off is an opt-out a debug-mode frame must not override."""
    monkeypatch.setenv("AF_ERROR_MODE", "off")
    af = _ragged_frame()
    af._mode = "debug"  # noqa: SLF001 — the mode/env combination under test
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_attribution_appears_exactly_once() -> None:
    """No double decoration when control re-enters the handler."""
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()
    assert str(excinfo.value).count("Failing column") == 1


def test_run_to_parquet_names_the_offending_column(tmp_path: Path) -> None:
    """The at-scale batched path was the reported pain case — cover it."""
    from gaspatchio_core.scenarios._spill import run_to_parquet

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.mismatched = af.six * af.three
        return af

    points = pl.DataFrame({"policy_id": [1], "six": [[1.0] * 6], "three": [[1.0] * 3]})
    with pytest.raises(Exception, match="mismatched"):
        run_to_parquet(
            model,
            points,
            tmp_path,
            batch_size=1,
            mounts_text="/dev/disk1 / ext4 rw 0 0\n",
        )


def test_structural_mutation_resets_attribution_rather_than_misattributing() -> None:
    """After an unrecorded plan change, attribution restarts cleanly.

    filter() mutates the plan without being recorded, so earlier
    assignments are no longer sound to replay. The next assignment opens a
    fresh window against the post-filter baseline — the broken column
    assigned AFTER the filter is still attributed correctly.
    """
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af = af.filter(pl.col("policy_id") == 1)
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
