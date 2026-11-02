# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table's identity is its content, whatever order the source was laid out in.

The record carries the canonical, column-order-invariant content hash of
spec section 12.3, and one public ``Table.fingerprint()`` returns it. These
tests hold every reader of that hash to it -- the Table, the record's
``assumptions`` entry, the lookup node's ``table_fingerprint``, the graph
fingerprint, the validator's re-hash of the inline payload, the conformance
kit's independent re-hash, and the change report -- so that a reordered
column, a reordered row or a re-encoded file moves none of them, and a
changed rate moves every one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import DataDimension, Table
from gaspatchio.frame.graph import GraphExporter, diff_artifacts, validate_artifact

_KIT = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"

_RATES = pl.DataFrame(
    {
        "age": [40, 40, 41, 41],
        "duration": [1, 2, 1, 2],
        "rate": [0.0010, 0.0011, 0.0012, 0.0013],
    }
)


def _table(source: pl.DataFrame | Path, name: str = "canonical_mortality") -> Table:
    return Table(
        name=name,
        source=source,
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
    )


def _record(table: Table) -> dict[str, Any]:
    """Return the executable record of a one-line model reading ``table``."""
    af = ActuarialFrame({"age": [40, 41], "duration": [2, 1]})
    af.q = table.lookup(age=af.age, duration=af.duration)
    document = GraphExporter(af).export(profile="executable", include_tables="all")
    return json.loads(document)


def _stamps(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return the entry fingerprint, the node's table_fingerprint, the graph's."""
    (entry,) = [e for e in record["assumptions"] if e["kind"] == "table"]
    (node,) = [n for n in record["nodes"] if n.get("column") == "q"]
    return (
        entry["fingerprint"],
        node["expr"]["attrs"]["table_fingerprint"],
        record["graph_fingerprint"],
    )


def _kit_identity(payload: dict[str, Any]) -> str:
    """Re-hash ``payload`` with the conformance kit's own standard-library reader."""
    program = (
        "import json, sys; sys.path.insert(0, '.');"
        "from reader.tables import table_identity;"
        "print(table_identity(json.load(sys.stdin)))"
    )
    done = subprocess.run(  # noqa: S603 -- this interpreter, the repository's kit
        [sys.executable, "-I", "-c", program],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=_KIT,
        check=True,
    )
    return done.stdout.strip()


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    (entry,) = [e for e in record["assumptions"] if e["kind"] == "table"]
    payload: dict[str, Any] = entry["payload"]
    return payload


def test_a_column_reorder_moves_nothing() -> None:
    """The repro: the same rates, columns listed differently."""
    published = _table(_RATES)
    record = _record(published)
    reordered = _table(_RATES.select("rate", "duration", "age"))
    record_again = _record(reordered)

    assert published.fingerprint() == reordered.fingerprint()
    assert _stamps(record) == _stamps(record_again)
    assert _stamps(record)[0] == published.fingerprint()
    assert not diff_artifacts(record, record_again).drift


def test_a_column_reorder_is_not_a_reregistration() -> None:
    """The registry's 'different data' warning stays quiet for a pure reorder."""
    _table(_RATES, name="canonical_reorder_warning")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _table(
            _RATES.select("duration", "rate", "age"), name="canonical_reorder_warning"
        )


def test_a_row_reorder_moves_nothing() -> None:
    published = _table(_RATES)
    shuffled = _table(_RATES.reverse())

    assert published.fingerprint() == shuffled.fingerprint()
    assert _stamps(_record(published)) == _stamps(_record(shuffled))


def test_a_reencoded_file_moves_nothing(tmp_path: Path) -> None:
    parquet = tmp_path / "rates.parquet"
    csv = tmp_path / "rates.csv"
    _RATES.write_parquet(parquet, compression="zstd")
    _RATES.select("rate", "age", "duration").reverse().write_csv(csv)

    from_frame = _table(_RATES)
    from_parquet = _table(parquet)
    from_csv = _table(csv)

    assert from_frame.fingerprint() == from_parquet.fingerprint()
    assert from_frame.fingerprint() == from_csv.fingerprint()
    assert _stamps(_record(from_parquet)) == _stamps(_record(from_csv))


def test_a_changed_rate_moves_every_reader() -> None:
    published = _table(_RATES)
    before = _record(published)
    moved = _table(
        _RATES.with_columns(
            pl.when(pl.col("age") == 41)
            .then(pl.col("rate") * 1.1)
            .otherwise(pl.col("rate"))
            .alias("rate")
        )
    )
    after = _record(moved)

    assert published.fingerprint() != moved.fingerprint()
    assert published.source_sha() != moved.source_sha()
    was, now = _stamps(before), _stamps(after)
    assert all(a != b for a, b in zip(was, now, strict=True))
    assert now[0] == now[1] == moved.fingerprint()
    report = diff_artifacts(before, after)
    assert report.drift
    assert any(
        "canonical_mortality" in json.dumps(item.to_dict()) for item in report.data
    )


def test_every_reader_rehashes_the_payload_to_the_fingerprint() -> None:
    """The validator and the kit's independent reader agree with the producer."""
    table = _table(_RATES.select("rate", "duration", "age"))
    record = _record(table)
    payload = _payload(record)

    assert [column["name"] for column in payload["columns"]] == [
        "age",
        "duration",
        "rate",
    ]
    assert validate_artifact(record, deep=True).ok
    assert _kit_identity(payload) == table.fingerprint()


def test_canonical_form_carries_the_fingerprint_for_a_renamed_dimension() -> None:
    """A dimension renamed on the way in no longer breaks the recipe.

    ``canonical_form`` used to select the dimension *names* from the processed
    frame, which holds the *processed* column names, so a
    ``DataDimension(rename_to=...)`` table raised ``ColumnNotFoundError`` from
    ``source_sha()``.
    """
    table = Table(
        name="canonical_renamed",
        source=pl.DataFrame({"Age": [40, 41], "rate": [0.001, 0.002]}),
        dimensions={"age": DataDimension(column="Age", rename_to="attained_age")},
        value="rate",
    )

    assert table.canonical_form()["content_sha"] == table.fingerprint()
    assert table.source_sha().startswith("sha256:")


def test_key_order_in_the_declaration_moves_nothing() -> None:
    """Dimensions declared in another order bind and stamp the same way."""
    one = _table(_RATES)
    other = Table(
        name="canonical_mortality",
        source=_RATES.select("duration", "age", "rate"),
        dimensions={"duration": "duration", "age": "age"},
        value="rate",
    )

    assert one.fingerprint() == other.fingerprint()
    assert _stamps(_record(one)) == _stamps(_record(other))


def test_an_extension_slice_in_another_column_order_appends() -> None:
    """``extend`` canonicalises the slice, and lands where a one-shot build does."""
    base = Table(
        name="canonical_extend",
        source=_RATES.filter(pl.col("age") == 40),
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
        storage_mode="hash",
    )
    base.extend(_RATES.filter(pl.col("age") == 41).select("rate", "duration", "age"))
    whole = _table(_RATES, name="canonical_extend_whole")

    assert base.fingerprint() == whole.fingerprint()


@pytest.mark.parametrize("value_first", [True, False])
def test_the_value_column_is_last_whatever_the_source(value_first: bool) -> None:  # noqa: FBT001
    order = ["rate", "age", "duration"] if value_first else ["age", "rate", "duration"]
    table = _table(_RATES.select(order))

    assert table.to_dataframe().columns == ["age", "duration", "rate"]
