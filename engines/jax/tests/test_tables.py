# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which storage a basis takes, why, and where a query lands in it.

The decision is the Rust kernel's, restated: a dense grid addressed by
arithmetic unless the key space overflows a flat index, would not fit in a
hundred mebibytes, or is so sparse that most of the grid is holes. Every one
of those sends the basis to the exact sorted-rows search instead, which costs
what a search costs and answers the same numbers.
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest

from gaspatchio_jax import tables
from gaspatchio_jax.interning import ABSENT, Dictionary
from gaspatchio_jax.tables import Grid, SortedTuples, build, positions_of
from gaspatchio_jax.typed import JNP_OF, DomainRefused, Value
from tests.fixtures import make_tables


def _built(name: str) -> tuple[tables.Storage, str | None]:
    """Return the storage one named fixture takes, and the note beside it."""
    return build(make_tables.PAYLOADS[name](), interning=Dictionary())


def _key(values: list[float | int], carrier: str = "i64") -> Value:
    """Return one query key column, as a lowering hands it over."""
    return Value(
        jnp.asarray(values, dtype=JNP_OF[carrier]),  # type: ignore[index]
        carrier,  # type: ignore[arg-type]
        "scalar",
        carrier,
    )


def test_a_fully_crossed_basis_is_a_dense_grid_with_no_note() -> None:
    storage, note = _built("dense")
    assert isinstance(storage, Grid)
    assert note is None
    assert storage.values.shape == (6,)
    assert bool(jnp.all(storage.present))


def test_a_one_percent_payload_takes_the_fallback() -> None:
    """The density condition on its own: the key space is small and mostly holes."""
    storage, note = _built("sparse_1pct")
    assert isinstance(storage, SortedTuples)
    assert note is not None
    assert "density" in note
    assert "10" in note


def test_a_two_hundredths_of_a_percent_payload_takes_the_same_fallback() -> None:
    storage, note = _built("sparse_002pct")
    assert isinstance(storage, SortedTuples)
    assert note is not None
    assert "density" in note


def test_a_key_space_wider_than_a_flat_index_falls_back_without_packing() -> None:
    storage, note = _built("overflow")
    assert isinstance(storage, SortedTuples)
    assert storage.packed is None
    assert note is not None
    assert "flat index" in note


def test_a_grid_over_a_hundred_mebibytes_falls_back_and_the_note_names_the_size() -> (
    None
):
    storage, note = _built("oversize")
    assert isinstance(storage, SortedTuples)
    assert storage.packed is not None
    assert note is not None
    assert "115678088" in note.replace(",", "")
    assert "104857600" in note.replace(",", "")


def test_the_size_condition_decides_on_its_own_when_the_basis_is_dense() -> None:
    """A basis both oversize and dense is two million rows, so it is judged here.

    The three conditions are independent, and a payload that meets two says
    both; this is the one witness that the size condition needs neither of
    the others to fire, taken on the numbers rather than on two million rows
    of fixture nobody would read.
    """
    met = tables.conditions_met(rows=2_000_000, sizes=(4000, 4000))
    assert len(met) == 1
    assert "mebibyte" in met[0] or "104857600" in met[0].replace(",", "")


def test_a_key_column_with_a_fractional_cell_refuses_by_name() -> None:
    with pytest.raises(DomainRefused) as refused:
        _built("fractional_key")
    assert "0.5" in refused.value.what
    assert "whole" in refused.value.what


def test_one_key_tuple_twice_refuses_even_where_the_answers_agree() -> None:
    with pytest.raises(DomainRefused) as refused:
        _built("duplicate_tuple")
    assert "45" in refused.value.what
    assert refused.value.clause == "11.1.24"


def test_a_query_that_lands_on_a_row_is_a_hit_and_one_that_does_not_is_a_miss() -> None:
    storage, _note = _built("dense")
    landing = positions_of(storage, (_key([45, 45, 30], "f64"), _key([1, 9, 1])))
    assert landing.hit.tolist() == [True, False, False]
    answer = tables.answer_at(storage, landing.position, landing.hit, missing=jnp.nan)
    assert answer.tolist()[0] == pytest.approx(0.01)


def test_a_cell_the_basis_has_no_row_for_is_a_miss() -> None:
    """Inside the span and outside the rows: the grid holds the hole."""
    storage, _note = _built("blank_answer")
    landing = positions_of(storage, (_key([46.0], "f64"), _key([1.0], "f64")))
    assert landing.hit.tolist() == [False]
    assert landing.position.shape == (1,)


def test_an_answer_cell_that_is_not_there_is_a_miss_at_the_key_that_reaches_it() -> (
    None
):
    """The answer column is judged where a query lands, not over the table."""
    storage, _note = _built("blank_answer")
    landing = positions_of(
        storage, (_key([45.0, 45.0], "f64"), _key([1.0, 2.0], "f64"))
    )
    assert landing.hit.tolist() == [True, False]


def test_a_null_key_is_a_miss_rather_than_a_row_it_selects() -> None:
    """A null key's absent code selects nothing, on either carrier."""
    storage, _note = _built("text_keyed")
    landing = positions_of(storage, (_key([ABSENT, 0], "code"), _key([1, 1], "i64")))
    assert landing.hit.tolist() == [False, True]
    assert int(landing.position[1]) >= 0


def test_the_two_keys_a_packing_would_collide_resolve_to_their_own_rows() -> None:
    """The colliding pair, and the two tuples a span-wide radix packs onto them."""
    storage, _note = _built("overflow")
    ages = _key([0, 2**32, 1, 0])
    durations = _key([2**32, 0, 0, 0])
    landing = positions_of(storage, (ages, durations))
    answer = tables.answer_at(storage, landing.position, landing.hit, missing=jnp.nan)
    assert landing.hit.tolist() == [True, True, False, False]
    assert answer.tolist()[0] == pytest.approx(0.01)
    assert answer.tolist()[1] == pytest.approx(0.02)


def test_the_fallback_answers_what_the_grid_answers_over_the_same_basis() -> None:
    """Both paths are exact, which is the only reason the fallback is allowed."""
    payload = make_tables.sparse_1pct()
    fallback, note = build(payload, interning=Dictionary())
    assert note is not None
    keys = (_key([0.0, 10.0, 990.0, 5.0], "f64"), _key([0.0, 1.0, 9.0, 5.0], "f64"))
    landing = positions_of(fallback, keys)
    answer = tables.answer_at(fallback, landing.position, landing.hit, missing=jnp.nan)
    assert landing.hit.tolist() == [True, True, True, False]
    assert answer.tolist()[:3] == pytest.approx([0.0, 0.01, 0.99])


def test_a_basis_with_no_rows_at_all_refuses() -> None:
    """11.1.24: an empty processed table has no portable value semantics."""
    payload = make_tables.dense()
    payload["rows"] = []
    with pytest.raises(DomainRefused) as refused:
        build(payload, interning=Dictionary())
    assert "no rows" in refused.value.what


def test_a_key_carried_as_a_date_is_outside_the_key_domain() -> None:
    payload = make_tables.dense()
    payload["columns"][0]["dtype"] = "date"
    payload["rows"] = [["2024-01-31", 1.0, 0.01]]
    with pytest.raises(DomainRefused) as refused:
        build(payload, interning=Dictionary())
    assert "date" in refused.value.what


def test_a_text_axis_answers_the_same_equality_the_dictionary_does() -> None:
    interning = Dictionary()
    storage, note = build(make_tables.text_keyed(), interning=interning)
    assert isinstance(storage, Grid)
    assert note is None
    codes = _key([interning.code_for("B"), interning.code_for("A")], "code")
    landing = positions_of(storage, (codes, _key([2, 2])))
    answer = tables.answer_at(storage, landing.position, landing.hit, missing=jnp.nan)
    assert landing.hit.tolist() == [True, True]
    assert answer.tolist() == pytest.approx([0.04, 0.02])


def test_a_text_key_the_basis_never_carried_is_a_miss_rather_than_an_error() -> None:
    interning = Dictionary()
    storage, _note = build(make_tables.text_keyed(), interning=interning)
    minted = interning.code_for("Z")
    landing = positions_of(storage, (_key([minted], "code"), _key([1])))
    assert landing.hit.tolist() == [False]
