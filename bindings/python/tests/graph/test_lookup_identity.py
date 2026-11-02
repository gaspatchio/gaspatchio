# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A saved lookup cannot silently acquire a different table or miss policy."""

from __future__ import annotations

import math
import pickle
import re
from dataclasses import replace

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import AttrValue, Call, Col
from gaspatchio.assumptions import Table, TableSupersededError
from gaspatchio.frame.lowering.artefacts import (
    register_table,
    table_named,
    table_schema,
)
from gaspatchio.frame.lowering.polars import lower_polars


def _table(name: str, rate: float) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [40], "rate": [rate]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _call(table: Table) -> Call:
    return Call(
        "lookup",
        (Col("age"),),
        (
            ("table", table.name),
            ("table_fingerprint", register_table(table)),
            ("on_missing", "raise"),
            ("fill_value", None),
        ),
    )


def _kernel_call(payload: dict[str, object]) -> pl.Expr:
    """Call the lookup kernel with a payload of this test's choosing.

    ``lower_polars`` always writes a whole payload, so varying one is the
    only way to read what the kernel does with a partial one.
    """
    from polars.plugins import register_plugin_function

    from gaspatchio.frame.lowering._polars.plugins import _get_lib

    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="lookup_by_table_and_hash",
        args=[pl.col("age")],
        kwargs=payload,
        is_elementwise=True,
    )


def test_a_lookup_payload_is_written_and_read_back_by_the_same_installation() -> None:
    """The kernel reads every identity field the lowering writes.

    The payload travels inside the expression object, from the lowering that
    built it to the library file the plan names by path -- it is never
    written down and never read by another build. So the identity fields
    take no default: a payload short of one is a payload built wrong in this
    process, and the kernel says which field is missing rather than reading
    an empty fingerprint and failing the identity check later on.
    """
    table = _table("lookup_payload_whole", 0.1)
    fingerprint = register_table(table)
    key_columns, value_column = table_schema(table.name, fingerprint)
    payload: dict[str, object] = {
        "table_name": table.name,
        "table_fingerprint": fingerprint,
        "key_columns": key_columns,
        "value_column": value_column,
        "on_missing": "raise",
        "fill_value": None,
    }
    frame = pl.DataFrame({"age": [40]})

    assert frame.select(_kernel_call(payload)).to_series().to_list() == [0.1]

    for field in ("table_name", "table_fingerprint", "key_columns", "value_column"):
        short = {k: v for k, v in payload.items() if k != field}
        with pytest.raises(
            pl.exceptions.ComputeError, match=f"missing field `{field}`"
        ):
            frame.select(_kernel_call(short))

    for field in ("on_missing", "fill_value"):
        without = {k: v for k, v in payload.items() if k != field}
        assert frame.select(_kernel_call(without)).to_series().to_list() == [0.1], (
            f"{field} states the miss policy and has a default; a payload "
            f"without it should still read the rate"
        )


def test_a_lookup_payload_survives_a_pickle_inside_one_installation() -> None:
    """The payload crosses a pickle whole, and only within one installation.

    A plan is written down in two quite different senses. The published
    vector in ``schemas/vectors/lookup.json`` keeps a lookup node on disk and
    is re-run every release; it survives because it carries the graph's own
    attributes and ``_lower_lookup`` mints the key and value roles fresh each
    time. The payload below is the other sense -- Polars carries it inside
    the expression, so a frame pickled mid-model (as a worker would receive
    it) carries every field verbatim. Within one installation that round
    trip runs and gives the rate. A payload short of a field, which is what a
    plan from another build would look like, is refused by the field's name
    instead of defaulting to an empty one.
    """
    table = _table("lookup_payload_pickle", 0.1)
    af = ActuarialFrame(pl.DataFrame({"age": [40]}))
    af.rate = table.lookup(age=af.age)

    blob = pickle.dumps(af)
    for field in (b"table_name", b"table_fingerprint", b"key_columns", b"value_column"):
        assert field in blob, f"the pickle should carry {field.decode()!r} verbatim"

    carried: ActuarialFrame = pickle.loads(blob)  # noqa: S301 -- our own bytes
    assert carried.collect()["rate"].to_list() == [0.1]

    fingerprint = register_table(table)
    key_columns, _value_column = table_schema(table.name, fingerprint)
    short: dict[str, object] = {
        "table_name": table.name,
        "table_fingerprint": fingerprint,
        "key_columns": key_columns,
        "on_missing": "raise",
        "fill_value": None,
    }
    crossed = pickle.loads(  # noqa: S301 -- our own bytes
        pickle.dumps(pl.DataFrame({"age": [40]}).lazy().select(_kernel_call(short))),
    )
    with pytest.raises(
        pl.exceptions.ComputeError,
        match="missing field `value_column`",
    ):
        crossed.collect()


def test_replayed_lookup_checks_content_even_when_the_name_exists() -> None:
    table = _table("lookup_replay_identity", 0.1)
    node = _call(table)
    original = dict(node.attrs)
    wrong = {**original, "table_fingerprint": f"sha256:{'0' * 64}"}

    with pytest.raises(TableSupersededError, match="has been superseded"):
        lower_polars(replace(node, attrs=tuple(wrong.items())))

    result = pl.DataFrame({"age": [40]}).select(lower_polars(node))
    assert result.to_series().to_list() == [0.1]


def test_unread_replacement_cannot_hide_behind_a_matching_old_directory_entry() -> None:
    old = _table("lookup_replay_unread_replacement", 0.1)
    node = _call(old)
    fingerprint = register_table(old)
    replacement = _table(old.name, 0.9)  # registered by Table, not filed by a read

    with pytest.raises(TableSupersededError, match="has been superseded"):
        table_named(old.name, fingerprint)
    with pytest.raises(TableSupersededError, match="has been superseded"):
        lower_polars(node)

    # Reading the current table files it and makes the new formula executable.
    result = pl.DataFrame({"age": [40]}).select(lower_polars(_call(replacement)))
    assert result.to_series().to_list() == [0.9]


def test_identical_content_under_another_name_is_not_a_fallback() -> None:
    table = _table("lookup_replay_known_identity", 0.2)
    node = _call(table)
    attrs = {**dict(node.attrs), "table": "lookup_replay_absent_name"}
    with pytest.raises(KeyError, match="does not exist in this process"):
        lower_polars(replace(node, attrs=tuple(attrs.items())))


# Every refusal below names the defect it met, so every case asserts the
# sentence its own defect earns: the attribute that never arrived, the one
# written twice, the one lookup does not carry, the miss-policy pairing that
# came in, the operand count against the table's key columns. Swap any case's
# defect for its neighbour's and that case fails, which is what these
# assertions are for -- they used to share one sentence per check, and a node
# wrong in one way passed the case written for another. `re.escape`
# throughout: the sentences quote names and values, so a bare pattern would
# read those quotes, brackets and dots as syntax.


@pytest.mark.parametrize(
    "key", ["table", "table_fingerprint", "on_missing", "fill_value"]
)
def test_missing_lookup_attributes_are_not_defaulted(key: str) -> None:
    node = _call(_table("lookup_replay_signature", 0.1))
    attrs = tuple(item for item in node.attrs if item[0] != key)
    with pytest.raises(
        TypeError, match=re.escape(f"lookup is missing the attribute {key!r}")
    ):
        lower_polars(replace(node, attrs=attrs))


def test_several_missing_lookup_attributes_are_named_in_one_refusal() -> None:
    """Two attributes short is one refusal naming both, not a second attempt."""
    node = _call(_table("lookup_replay_signature", 0.1))
    kept = {"table", "on_missing"}
    attrs = tuple(item for item in node.attrs if item[0] in kept)
    with pytest.raises(
        TypeError,
        match=re.escape(
            "lookup is missing the attributes 'table_fingerprint' and 'fill_value'"
        ),
    ):
        lower_polars(replace(node, attrs=attrs))


@pytest.mark.parametrize(
    ("extra", "refusal"),
    [
        (("table", "duplicate"), "lookup carries 'table' more than once"),
        (
            ("ignored", True),
            (
                "lookup does not carry the attribute 'ignored', which arrived "
                "here as True"
            ),
        ),
    ],
    ids=["duplicate_table", "unknown_attribute"],
)
def test_duplicate_and_unknown_lookup_attributes_refuse(
    extra: tuple[str, AttrValue],
    refusal: str,
) -> None:
    node = _call(_table("lookup_replay_signature", 0.1))
    with pytest.raises(TypeError, match=re.escape(refusal)):
        lower_polars(replace(node, attrs=(*node.attrs, extra)))


@pytest.mark.parametrize(
    ("key", "value", "refusal"),
    [
        ("table", "", "lookup's table attribute is empty text"),
        ("table", 1, "lookup's table attribute is not text: it arrived as int"),
        (
            "table_fingerprint",
            "",
            "lookup's table_fingerprint attribute is empty text",
        ),
        (
            "table_fingerprint",
            False,
            "lookup's table_fingerprint attribute is not text: it arrived as bool",
        ),
        ("on_missing", "ignore", "on_missing='ignore' beside fill_value=None"),
        ("on_missing", "fill", "on_missing='fill' beside fill_value=None"),
        ("fill_value", 0.0, "on_missing='raise' beside fill_value=0.0"),
    ],
)
def test_malformed_lookup_identity_and_miss_policy_refuse(
    key: str,
    value: AttrValue,
    refusal: str,
) -> None:
    node = _call(_table("lookup_replay_signature", 0.1))
    attrs = {**dict(node.attrs), key: value}
    with pytest.raises(TypeError, match=re.escape(refusal)):
        lower_polars(replace(node, attrs=tuple(attrs.items())))


@pytest.mark.parametrize("value", [True, 1, "0", math.nan, math.inf, -math.inf])
def test_fill_value_is_a_finite_decimal(value: AttrValue) -> None:
    node = _call(_table("lookup_replay_signature", 0.1))
    attrs = {**dict(node.attrs), "on_missing": "fill", "fill_value": value}
    pairing = re.escape(f"on_missing='fill' beside fill_value={value!r}")
    with pytest.raises(TypeError, match=f"{pairing}.*finite decimal"):
        lower_polars(replace(node, attrs=tuple(attrs.items())))


@pytest.mark.parametrize(("arity", "spelled"), [(0, "no operands"), (2, "2 operands")])
def test_key_arity_is_checked_against_processed_columns(
    arity: int, spelled: str
) -> None:
    node = _call(_table("lookup_replay_signature", 0.1))
    with pytest.raises(
        TypeError,
        match=re.escape(
            f"lookup carries {spelled} and the processed table "
            "'lookup_replay_signature' has one key column ('age')"
        ),
    ):
        lower_polars(replace(node, args=(Col("age"),) * arity))
