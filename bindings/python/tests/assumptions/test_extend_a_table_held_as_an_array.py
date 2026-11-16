# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``Table.extend`` extends a table whatever storage it is held in.

The native append adds rows to a hash map, and refused a table held as a
dense array with a raw ``RuntimeError`` telling the reader to "use
StorageMode::Hash" -- a Rust enum no Python caller can name. ``"auto"``, the
default, picks array storage for an ordinary table, so ``extend`` failed on
the tables its own docstring examples build. An array-held table is now built
again whole from the extended frame, after the same moved-table check the
native append makes, and a slice repeating a key the table holds is refused
by name on either storage.
"""

from __future__ import annotations

import itertools
from typing import Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._internal import PyAssumptionTableRegistry
from gaspatchio.assumptions import Table

_NAMES = itertools.count()
Storage = Literal["auto", "array", "hash"]
_STORAGES: list[Storage] = ["auto", "array", "hash"]


def _table(storage: Storage, ages: list[int], rates: list[float]) -> Table:
    return Table(
        name=f"m1_extend_{storage}_{next(_NAMES)}",
        source=pl.DataFrame({"age": ages, "rate": rates}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode=storage,
    )


def _answers(table: Table, ages: list[int]) -> list[float]:
    frame = ActuarialFrame({"age": ages})
    frame.rate = table.lookup(age=frame.age)
    return list(frame.collect()["rate"].to_list())


def test_auto_picks_array_storage_for_an_ordinary_table() -> None:
    assert _table("auto", [30, 35, 40], [0.1, 0.2, 0.3]).storage_mode == "array"


@pytest.mark.parametrize("storage", _STORAGES)
def test_extend_appends_rows_a_lookup_then_answers(storage: Storage) -> None:
    table = _table(storage, [30, 35, 40], [0.1, 0.2, 0.3])
    table.extend(pl.DataFrame({"age": [45, 50], "rate": [0.4, 0.5]}))

    assert len(table.to_dataframe()) == 5
    assert _answers(table, [30, 45, 50]) == [0.1, 0.4, 0.5]


@pytest.mark.parametrize("storage", _STORAGES)
def test_an_extended_table_is_the_table_built_from_the_combined_source(
    storage: Storage,
) -> None:
    table = _table(storage, [30, 35, 40], [0.1, 0.2, 0.3])
    table.extend(pl.DataFrame({"age": [45], "rate": [0.4]}))
    whole = _table(storage, [30, 35, 40, 45], [0.1, 0.2, 0.3, 0.4])

    assert table.fingerprint() == whole.fingerprint()


@pytest.mark.parametrize("storage", _STORAGES)
def test_a_text_keyed_table_extends(storage: Storage) -> None:
    table = Table(
        name=f"m1_extend_text_{storage}_{next(_NAMES)}",
        source=pl.DataFrame({"band": ["a", "b"], "rate": [0.1, 0.2]}),
        dimensions={"band": "band"},
        value="rate",
        storage_mode=storage,
    )
    table.extend(pl.DataFrame({"band": ["c"], "rate": [0.3]}))
    frame = ActuarialFrame({"band": ["a", "c"]})
    frame.rate = table.lookup(band=frame.band)
    assert frame.collect()["rate"].to_list() == [0.1, 0.3]


@pytest.mark.parametrize("storage", _STORAGES)
def test_a_plan_built_before_the_extend_refuses_to_collect(storage: Storage) -> None:
    table = _table(storage, [0, 1, 2], [0.1, 0.2, 0.3])
    before = ActuarialFrame({"age": [1]})
    before.rate = table.lookup(age=before.age)

    table.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    with pytest.raises(pl.exceptions.ComputeError, match="no longer matches"):
        before.collect()


@pytest.mark.parametrize("storage", _STORAGES)
def test_a_stale_table_object_cannot_extend_over_its_replacement(
    storage: Storage,
) -> None:
    name = f"m1_extend_stale_{storage}_{next(_NAMES)}"
    source = pl.DataFrame({"age": [0, 1, 2], "rate": [0.1, 0.2, 0.3]})
    stale = Table(name, source, {"age": "age"}, "rate", storage_mode=storage)
    with pytest.warns(match="re-registered with different data"):
        current = Table(
            name,
            source.with_columns(pl.col("rate") * 10),
            {"age": "age"},
            "rate",
            storage_mode=storage,
        )

    with pytest.raises(RuntimeError, match="changed before it could be extended"):
        stale.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    assert _answers(current, [1]) == [2.0]


def _refusal_for(name: str) -> str:
    return (
        f"Assumption table '{name}' changed before it could be extended: another "
        "Table registered under this name since this one was built. Call "
        "extend() on the current Table instead."
    )


@pytest.mark.parametrize("storage", _STORAGES)
def test_every_storage_refuses_a_stale_extend_in_one_sentence(
    storage: Storage,
) -> None:
    name = f"m1_extend_one_refusal_{storage}_{next(_NAMES)}"
    source = pl.DataFrame({"age": [0, 1, 2], "rate": [0.1, 0.2, 0.3]})
    stale = Table(name, source, {"age": "age"}, "rate", storage_mode=storage)
    with pytest.warns(match="re-registered with different data"):
        Table(
            name,
            source.with_columns(pl.col("rate") * 10),
            {"age": "age"},
            "rate",
            storage_mode=storage,
        )

    with pytest.raises(RuntimeError) as refused:
        stale.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    assert str(refused.value) == _refusal_for(name)


@pytest.mark.parametrize("storage", _STORAGES)
def test_a_replacement_arriving_after_the_python_check_is_still_refused(
    storage: Storage,
) -> None:
    """The check and the swap are one step, so nothing can land between them.

    A table replaced straight in the registry is what another thread's
    replacement looks like from this object: nothing on the Python side
    moved, and only the registry knows.
    """
    name = f"m1_extend_unseen_{storage}_{next(_NAMES)}"
    source = pl.DataFrame({"age": [0, 1, 2], "rate": [0.1, 0.2, 0.3]})
    table = Table(name, source, {"age": "age"}, "rate", storage_mode=storage)
    PyAssumptionTableRegistry().register_or_replace_table(
        name=name,
        df=source.with_columns(pl.col("age").cast(pl.Float64), pl.col("rate") * 10),
        keys=["age"],
        value_column="rate",
        storage_mode=storage,
        fingerprint="sha256:someone-else",
    )

    with pytest.raises(RuntimeError) as refused:
        table.extend(pl.DataFrame({"age": [3], "rate": [0.4]}))

    assert str(refused.value) == _refusal_for(name)


@pytest.mark.parametrize("storage", _STORAGES)
@pytest.mark.parametrize(
    ("slice_ages", "named"),
    [([40, 45], "age=40.0"), ([45, 45], "age=45.0")],
    ids=["a key the table holds", "a key the slice repeats"],
)
def test_a_repeated_key_is_refused_by_name_and_the_table_is_untouched(
    storage: Storage, slice_ages: list[int], named: str
) -> None:
    table = _table(storage, [30, 35, 40], [0.1, 0.2, 0.3])
    before = table.fingerprint()

    with pytest.raises(ValueError, match=f"two rates at {named}") as refused:
        table.extend(pl.DataFrame({"age": slice_ages, "rate": [0.9, 0.8]}))

    assert "StorageMode" not in str(refused.value)
    assert table.fingerprint() == before
    assert _answers(table, [40]) == [0.3]
