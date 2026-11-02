# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A lazy lookup stays bound to the table identity that built its plan."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from typing import Literal, cast

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._internal import PyAssumptionTableRegistry
from gaspatchio.assumptions import Table, TableSupersededError

KeyShape = Literal["scalar", "list"]
StorageMode = Literal["hash", "array"]
RawMutation = Literal["replace", "append"]


def _table(
    name: str,
    rates: list[float],
    storage_mode: StorageMode = "array",
) -> Table:
    """Register one dense age table under ``name``."""
    return Table(
        name=name,
        source=pl.DataFrame({"age": [0, 1, 2], "rate": rates}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage_mode,
    )


def _lookup_plan(
    table: Table,
    shape: KeyShape = "scalar",
    *,
    on_missing: str | float = "raise",
) -> ActuarialFrame:
    """Build but do not collect a lookup against ``table``."""
    keys: list[int] | list[list[int]] = [1] if shape == "scalar" else [[0, 1]]
    frame = ActuarialFrame({"age": keys})
    frame.rate = table.lookup(age=frame.age, on_missing=on_missing)
    return frame


def _rates(frame: ActuarialFrame) -> list[float] | list[list[float]]:
    """Collect the lookup answer in its scalar or list shape."""
    return cast("list[float] | list[list[float]]", frame.collect()["rate"].to_list())


@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.25])
@pytest.mark.parametrize("storage_mode", ["hash", "array"])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_replacement_refuses_every_lookup_shape_storage_and_miss_policy(
    shape: KeyShape,
    storage_mode: StorageMode,
    on_missing: str | float,
) -> None:
    """A miss policy cannot turn an identity mismatch into replacement rates."""
    miss_name = str(on_missing).replace(".", "_")
    name = f"lifetime_replace_{shape}_{storage_mode}_{miss_name}"
    original = _table(name, [0.1, 0.2, 0.3], storage_mode)
    keys = [9] if shape == "scalar" else [[0, 9]]
    pending = ActuarialFrame({"age": keys})
    pending.rate = original.lookup(age=pending.age, on_missing=on_missing)

    _table(name, [0.7, 0.8, 0.9], storage_mode)

    with pytest.raises(pl.exceptions.ComputeError, match="no longer matches"):
        pending.collect()


@pytest.mark.parametrize("storage_mode", ["hash", "array"])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_identical_reregistration_keeps_existing_and_new_plans_valid(
    shape: KeyShape, storage_mode: StorageMode
) -> None:
    """Notebook re-execution with identical content preserves the identity."""
    name = f"lifetime_identical_{shape}_{storage_mode}"
    first = _table(name, [0.1, 0.2, 0.3], storage_mode)
    first_plan = _lookup_plan(first, shape)
    second = _table(name, [0.1, 0.2, 0.3], storage_mode)
    second_plan = _lookup_plan(second, shape)

    expected = [0.2] if shape == "scalar" else [[0.1, 0.2]]
    assert _rates(first_plan) == expected
    assert _rates(second_plan) == expected


def test_a_collected_plan_refuses_when_recollected_after_replacement() -> None:
    """A successful first collect does not detach the plan from its table."""
    original = _table("lifetime_recollect", [0.1, 0.2, 0.3])
    plan = _lookup_plan(original)
    assert _rates(plan) == [0.2]

    _table("lifetime_recollect", [0.7, 0.8, 0.9])

    with pytest.raises(pl.exceptions.ComputeError, match="no longer matches"):
        plan.collect()


def test_same_content_with_changed_column_roles_refuses() -> None:
    """Content identity cannot hide changed key and answer roles."""
    source = pl.DataFrame({"left": [0.0, 1.0, 2.0], "right": [10.0, 20.0, 30.0]})
    original = Table(
        name="lifetime_roles",
        source=source,
        dimensions={"left": "left"},
        value="right",
        storage_mode="hash",
    )
    frame = ActuarialFrame({"left": [1.0]})
    frame.answer = original.lookup(left=frame.left)

    Table(
        name="lifetime_roles",
        source=source,
        dimensions={"right": "right"},
        value="left",
        storage_mode="hash",
    )

    with pytest.raises(pl.exceptions.ComputeError, match="key/value schema"):
        frame.collect()


def test_typed_lookup_cannot_be_relowered_under_new_roles() -> None:
    """A re-keyed table supersedes an old typed lookup node; it never reinterprets it.

    A table's fingerprint is taken over its canonical form, value column last
    (spec section 12.3), so the same source read with another column as the
    answer is new content under the name: the current table answers, and the
    old node is refused as built over a superseded base.
    """
    source = pl.DataFrame(
        {"left": [1.0, 2.0], "right": [2.0, 3.0], "factor": [1.0, 1.0]}
    )
    original = Table(
        name="lifetime_typed_roles",
        source=source,
        dimensions={"left": "left", "factor": "factor"},
        value="right",
        storage_mode="hash",
    )
    frame = ActuarialFrame({"left": [2.0], "factor": [1.0], "one": [1.0]})
    old_proxy = original.lookup(left=frame.left, factor=frame.factor)

    current = Table(
        name="lifetime_typed_roles",
        source=source,
        dimensions={"right": "right", "factor": "factor"},
        value="left",
        storage_mode="hash",
    )

    assert current.fingerprint() != original.fingerprint()
    frame.current = current.lookup(right=frame.left, factor=frame.factor)

    # Meeting a frame proxy carries the old Call into a fresh BinOp lowering.
    # Both interpretations hit: the original meaning returns 3, while the
    # replacement meaning would silently return 1 if the roles moved.
    with pytest.raises(TableSupersededError, match="has been superseded"):
        frame.answer = old_proxy * frame.one


def test_extend_invalidates_an_old_plan_and_supports_a_new_one() -> None:
    """An in-place extension moves identity before another plan is built."""
    table = _table("lifetime_extend", [0.1, 0.2, 0.3], "hash")
    old_plan = _lookup_plan(table)

    table.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    with pytest.raises(pl.exceptions.ComputeError, match="no longer matches"):
        old_plan.collect()
    new_frame = ActuarialFrame({"age": [3]})
    new_frame.rate = table.lookup(age=new_frame.age)
    assert _rates(new_frame) == [0.4]


def test_stale_object_cannot_extend_over_a_replacement() -> None:
    """Compare-and-swap leaves the winning replacement untouched."""
    stale = _table("lifetime_stale_extend", [0.1, 0.2, 0.3], "hash")
    current = _table("lifetime_stale_extend", [0.7, 0.8, 0.9], "hash")

    with pytest.raises(RuntimeError, match="changed before it could be extended"):
        stale.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    assert _rates(_lookup_plan(current)) == [0.8]


@pytest.mark.parametrize("mutation", ["replace", "append"])
def test_raw_registry_mutation_invalidates_a_bound_plan(
    mutation: RawMutation,
) -> None:
    """A raw mutation carries no identity and cannot inherit the old one."""
    name = f"lifetime_raw_{mutation}"
    table = _table(name, [0.1, 0.2, 0.3], "hash")
    plan = _lookup_plan(table)
    registry = PyAssumptionTableRegistry()

    if mutation == "replace":
        registry.register_or_replace_table(
            name,
            pl.DataFrame({"age": [0.0, 1.0, 2.0], "rate": [0.7, 0.8, 0.9]}),
            ["age"],
            "rate",
            force_replace=True,
            storage_mode="hash",
        )
    else:
        registry.append_to_table(
            name,
            pl.DataFrame({"age": [3.0], "rate": [0.4]}),
            ["age"],
            "rate",
        )

    with pytest.raises(pl.exceptions.ComputeError, match="unbound registry"):
        plan.collect()


@pytest.mark.parametrize("storage_mode", ["hash", "array"])
def test_raw_force_replace_false_preserves_the_bound_identity(
    storage_mode: StorageMode,
) -> None:
    """A skipped registration leaves both data and identity unchanged."""
    name = f"lifetime_no_replace_{storage_mode}"
    table = _table(name, [0.1, 0.2, 0.3], storage_mode)
    plan = _lookup_plan(table)

    PyAssumptionTableRegistry().register_or_replace_table(
        name,
        pl.DataFrame({"age": [0.0, 1.0, 2.0], "rate": [0.7, 0.8, 0.9]}),
        ["age"],
        "rate",
        force_replace=False,
        storage_mode=storage_mode,
    )

    assert _rates(plan) == [0.2]


def test_raw_reset_invalidates_a_bound_plan_in_an_isolated_process() -> None:
    """Reset removes the named table rather than leaving an identity behind."""
    program = textwrap.dedent(
        """
        import polars as pl
        from gaspatchio import ActuarialFrame
        from gaspatchio._internal import PyAssumptionTableRegistry
        from gaspatchio.assumptions import Table

        table = Table(
            name="lifetime_reset_child",
            source=pl.DataFrame({"age": [0, 1], "rate": [0.1, 0.2]}),
            dimensions={"age": "age"},
            value="rate",
        )
        frame = ActuarialFrame({"age": [1]})
        frame.rate = table.lookup(age=frame.age)
        PyAssumptionTableRegistry().reset()
        try:
            frame.collect()
        except pl.exceptions.ComputeError as error:
            assert "not registered" in str(error)
        else:
            raise AssertionError("reset lookup unexpectedly collected")
        """
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and in-memory source
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
