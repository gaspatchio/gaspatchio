# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A refused method form names the forms that are declared, not Polars' signature.

``af.x.fill_nan(None)`` was refused citing ``fill_nan(value: object | None)``
as "the gaspatchio form", and ``af.status.replace("IF", "INFORCE")`` citing
``replace(old: object, new: object | None = None, ...)`` -- signatures that
admit the very call refused. The refusal now names the declared forms, and
says what to write instead of ``fill_nan(None)``. And ``replace(old, new)``
with one value on each side is the one-entry mapping it means: accepted, and
recorded as the mapping is.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "status": ["IF", "LA", "IF"],
                "x": [float("nan"), 1.0, None],
                "code": [1, 2, 1],
            }
        )
    )


def _refused(write: object) -> str:
    af = _frame()
    with pytest.raises(TypeError) as refused:
        write(af)  # type: ignore[operator]
    return str(refused.value)


def test_fill_nan_none_names_the_declared_fill_and_what_to_write_instead() -> None:
    message = _refused(lambda af: af.x.fill_nan(None))

    assert "object | None" not in message
    assert "fill_nan() is declared as fill_nan(value), the value a number" in message
    assert "fill_nan(None) would turn a NaN into a missing value" in message
    assert "af.<column>.polars_native().fill_nan(None)" in message
    assert "engine_native" in message


def test_fill_nan_none_by_keyword_is_said_the_same_way() -> None:
    message = _refused(lambda af: af.x.fill_nan(value=None))

    assert "fill_nan(None) would turn a NaN into a missing value" in message


def test_what_the_fill_nan_refusal_names_instead_runs() -> None:
    af = _frame()
    af.zeroed = af.x.fill_nan(0.0)
    af.nulled = af.x.polars_native().fill_nan(None)

    out = af.collect()
    assert out["zeroed"].to_list() == [0.0, 1.0, None]
    assert out["nulled"].to_list() == [None, 1.0, None]
    assert af.graph.tiers().engine_native == ("nulled@1",)


def test_fill_nan_none_on_a_per_period_column_names_its_working_escape() -> None:
    """The plain escape fails at collect on a list column; the advice is per shape.

    ``af.x.polars_native().fill_nan(None)`` is Polars' ``fill_nan`` over the
    column, which on a column holding one list per policy fails inside
    Polars ("is_not_nan ... not supported for dtype list[f64]"). There the
    refusal names the per-period form, which evaluates it inside each list.
    """
    af = ActuarialFrame({"x": [[float("nan"), 2.0], [3.0]]})
    with pytest.raises(TypeError) as refused:
        af.x.fill_nan(None)
    message = str(refused.value)
    escape = "af.<column>.polars_native().list.eval(pl.element().fill_nan(None))"
    assert escape in message
    assert "write af.<column>.polars_native().fill_nan(None)" not in message

    af.nulled = af.x.polars_native().list.eval(pl.element().fill_nan(None))
    assert af.collect()["nulled"].to_list() == [[None, 2.0], [3.0]]
    assert af.graph.tiers().engine_native == ("nulled@1",)


def test_the_plain_escape_is_what_fails_on_a_per_period_column() -> None:
    af = ActuarialFrame({"x": [[float("nan"), 2.0], [3.0]]})
    af.nulled = af.x.polars_native().fill_nan(None)
    with pytest.raises(pl.exceptions.InvalidOperationError, match="is_not_nan"):
        af.collect()


def test_a_replace_form_polars_owns_names_the_declared_forms() -> None:
    message = _refused(lambda af: af.status.replace({"IF": "INFORCE"}, default="?"))

    assert "return_dtype" not in message
    assert "replace({old: new, ...}), replace([old, ...], [new, ...])" in message
    assert "replace(old, new)" in message
    assert "af.<column>.polars_native().replace(...)" in message


@pytest.mark.parametrize(
    "written",
    [
        lambda af: af.status.replace("IF", "INFORCE"),
        lambda af: af.status.replace(old="IF", new="INFORCE"),
    ],
    ids=["positional", "keyword"],
)
def test_one_value_and_its_replacement_is_the_one_entry_mapping(
    written: object,
) -> None:
    pair = _frame()
    pair.r = written(pair)  # type: ignore[operator]
    mapping = _frame()
    mapping.r = mapping.status.replace({"IF": "INFORCE"})

    assert pair.collect()["r"].to_list() == ["INFORCE", "LA", "INFORCE"]
    assert pair.graph.tiers().engine_native == ()
    assert pair.graph.fingerprint() == mapping.graph.fingerprint()
    pair_doc = json.loads(GraphExporter(pair).export())
    mapping_doc = json.loads(GraphExporter(mapping).export())
    assert pair_doc["graph_fingerprint"] == mapping_doc["graph_fingerprint"]


def test_a_scalar_pair_of_another_kind_is_refused_as_its_mapping_is() -> None:
    """The kind rule reads the pair as it reads the mapping it is."""
    af = _frame()
    with pytest.raises(TypeError, match="its replacement -- 1 -- is a whole number"):
        af.r = af.status.replace("IF", 1)


def test_a_whole_number_pair_replaces_as_its_mapping_does() -> None:
    af = _frame()
    af.r = af.code.replace(1, 9)

    assert af.collect()["r"].to_list() == [9, 2, 9]


def test_a_round_mode_polars_owns_names_the_two_declared_modes() -> None:
    message = _refused(lambda af: af.x.round(2, mode="half_up"))

    assert (
        "round() is declared as round(decimals), the decimals a whole number, "
        "with mode='half_to_even' (the default) or mode='half_away_from_zero', "
        "and the arguments supplied do not match any of these forms. For a "
        "Polars-specific form, write af.<column>.polars_native().round(...). "
        "A line written through .polars_native() records as engine_native"
    ) in message
