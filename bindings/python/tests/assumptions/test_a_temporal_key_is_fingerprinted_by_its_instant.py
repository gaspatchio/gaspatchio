# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table's date or timestamp key is fingerprinted as the date or instant it is.

The lookup kernel holds a date-like key as the whole number of its unit, and
the table's fingerprint used to be taken over that bare count: one instant
kept in milliseconds, microseconds and nanoseconds gave three fingerprints,
while five milliseconds, five microseconds, five nanoseconds, day five, the
integer five and any zone all shared one. ``gspio verify`` then said every
check agreed over a run whose claims differed, because swapping a table
keyed in milliseconds for one keyed in microseconds with the same counts
moved neither the table's fingerprint nor the graph's.

A key is now hashed through the content grammar's own carrier, as the book
digest hashes a column (section 12.3, which writes one instant in any unit one
way): an instant as its microseconds and the nanoseconds past them, with its
zone; a date as a date.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio._identity import content_sha_of
from gaspatchio.assumptions import Table
from gaspatchio.assumptions._processing import content_fingerprint_of
from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.validate import payload_frame
from gaspatchio.scenarios import MultiplicativeShock

if TYPE_CHECKING:
    from pathlib import Path

_COUNT = iter(range(10_000))
# A millisecond count whose microseconds an i64 does not hold (section 12.3).
_PAST_I64_MICROSECONDS = 9_223_372_036_854_776


def _counts(values: list[int], dtype: pl.DataType) -> pl.Series:
    """Return the counts ``values`` read as ``dtype``, in that type's own unit."""
    physical = pl.Int32 if dtype == pl.Date else pl.Int64
    return pl.Series("ts", values, dtype=physical).cast(dtype)


def _table(keys: pl.Series, **options: Any) -> Table:  # noqa: ANN401
    return Table(
        name=f"k1_instant_{next(_COUNT)}",
        source=pl.DataFrame({"ts": keys, "v": [0.01, 0.02]}),
        dimensions={"ts": "ts"},
        value="v",
        **options,
    )


# One instant, 5 ms past the epoch, in each unit and in UTC.
_ONE_INSTANT = {
    "ms": _counts([0, 5], pl.Datetime("ms")),
    "us": _counts([0, 5_000], pl.Datetime("us")),
    "ns": _counts([0, 5_000_000], pl.Datetime("ns")),
    "ms UTC": _counts([0, 5], pl.Datetime("ms", "UTC")),
}

# The same counts, [0, 5], as six different things.
_ONE_COUNT = {
    "5 ms": _counts([0, 5], pl.Datetime("ms")),
    "5 us": _counts([0, 5], pl.Datetime("us")),
    "5 ns": _counts([0, 5], pl.Datetime("ns")),
    "5 ms Auckland": _counts([0, 5], pl.Datetime("ms", "Pacific/Auckland")),
    "day 5": _counts([0, 5], pl.Date()),
    "the integer 5": pl.Series("ts", [0, 5]),
}


def test_one_instant_kept_in_any_unit_has_one_fingerprint() -> None:
    fingerprints = {
        unit: _table(keys).fingerprint() for unit, keys in _ONE_INSTANT.items()
    }

    assert len(set(fingerprints.values())) == 1, fingerprints


def test_the_same_count_of_different_things_never_shares_a_fingerprint() -> None:
    fingerprints = {
        what: _table(keys).fingerprint() for what, keys in _ONE_COUNT.items()
    }

    assert len(set(fingerprints.values())) == len(fingerprints), fingerprints


@pytest.mark.parametrize(
    "what", [*_ONE_INSTANT, *(what for what in _ONE_COUNT if what != "the integer 5")]
)
def test_the_fingerprint_is_the_content_grammar_over_the_key_in_its_kind(
    what: str,
) -> None:
    """The bytes are the book digest's: the carrier over the column as it is."""
    keys = {**_ONE_INSTANT, **_ONE_COUNT}[what]
    frame = pl.DataFrame({"ts": keys, "v": [0.01, 0.02]})

    assert _table(keys).fingerprint() == content_sha_of(frame)


@pytest.mark.parametrize("unit", list(_ONE_INSTANT))
def test_a_file_reread_reaches_the_table_s_fingerprint(unit: str) -> None:
    keys = _ONE_INSTANT[unit]
    source = pl.DataFrame({"ts": keys.reverse(), "v": [0.02, 0.01]})

    assert (
        content_fingerprint_of(source, {"ts": "ts"}, "v") == _table(keys).fingerprint()
    )


def test_a_shocked_or_copied_table_keeps_its_key_s_kind() -> None:
    ms, us = _table(_ONE_COUNT["5 ms"]), _table(_ONE_COUNT["5 us"])
    shock = MultiplicativeShock(factor=1.1)

    assert ms.with_shock(shock).fingerprint() != us.with_shock(shock).fingerprint()
    shocked_again = _table(_ONE_INSTANT["us"]).with_shock(shock)
    assert ms.with_shock(shock).fingerprint() == shocked_again.fingerprint()
    copy = Table.from_shocks(ms, {"base": []}, value_column="v")["base"]
    assert copy.fingerprint() == ms.fingerprint()


@pytest.mark.parametrize(
    "past",
    [_PAST_I64_MICROSECONDS, _PAST_I64_MICROSECONDS + 1, -_PAST_I64_MICROSECONDS],
)
def test_a_millisecond_key_past_i64_microseconds_is_refused_by_name(past: int) -> None:
    """The Table door refuses the instant every other door refuses (section 12.3).

    It answered before, hashing the bare millisecond count; now the key goes
    through the carrier, which names the column and the count.
    """
    keys = _counts([0, past], pl.Datetime("ms"))
    source = pl.DataFrame({"ts": keys, "v": [1.0, 2.0]})

    with pytest.raises(ValueError, match="leaves the 64-bit whole number"):
        _table(keys)
    with pytest.raises(ValueError, match="leaves the 64-bit whole number"):
        content_fingerprint_of(source, {"ts": "ts"}, "v")


def test_an_extension_in_another_unit_is_appended_as_the_same_instant() -> None:
    table = _table(_ONE_COUNT["5 ms"], storage_mode="hash")
    table.extend(pl.DataFrame({"ts": _counts([9_000], pl.Datetime("us")), "v": [0.03]}))
    whole = pl.DataFrame(
        {"ts": _counts([0, 5, 9], pl.Datetime("ms")), "v": [0.01, 0.02, 0.03]}
    )

    af = ActuarialFrame(pl.DataFrame({"q": _counts([9], pl.Datetime("ms"))}))
    af.r = table.lookup(ts=af.q)
    assert af.collect()["r"].to_list() == [0.03]
    assert table.fingerprint() == content_fingerprint_of(whole, {"ts": "ts"}, "v")


@pytest.mark.parametrize(
    "slice_keys",
    [
        _counts([9], pl.Date()),
        pl.Series("ts", [9]),
        _counts([9], pl.Datetime("ms", "UTC")),
    ],
)
def test_an_extension_of_another_kind_is_refused_by_kind(slice_keys: pl.Series) -> None:
    table = _table(_ONE_COUNT["5 ms"], storage_mode="hash")

    with pytest.raises(TypeError, match="another kind"):
        table.extend(pl.DataFrame({"ts": slice_keys, "v": [0.03]}))


def _audit_entry(table: Table, keys: pl.Series) -> dict[str, Any]:
    af = ActuarialFrame(pl.DataFrame({"pid": [1], "q": keys[:1]}))
    af.r = table.lookup(ts=af.q)
    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )
    document = json.loads(exported) if isinstance(exported, str) else exported
    (entry,) = document["assumptions"]
    return entry


@pytest.mark.parametrize("what", ["5 ms", "5 ns", "day 5"])
def test_the_audit_payload_carries_the_key_in_its_kind_and_rehashes(what: str) -> None:
    """Section 13: the payload is the frame the fingerprint was taken over."""
    table = _table(_ONE_COUNT[what])

    entry = _audit_entry(table, _ONE_COUNT[what])

    assert entry["fingerprint"] == table.fingerprint()
    declared = {
        column["name"]: column["dtype"] for column in entry["payload"]["columns"]
    }
    assert declared["ts"] == ("date" if what == "day 5" else "datetime")
    rebuilt, unreadable = payload_frame(entry["payload"])
    assert unreadable is None
    assert rebuilt is not None
    assert content_sha_of(rebuilt) == table.fingerprint()


def test_a_zoned_key_s_values_are_stated_unavailable_not_rewritten() -> None:
    """A payload names no zone, so values written without it would re-hash elsewhere."""
    table = _table(_ONE_COUNT["5 ms Auckland"])

    entry = _audit_entry(table, _ONE_COUNT["5 ms Auckland"])

    assert entry["fingerprint"] == table.fingerprint()
    assert entry["payload"]["omitted"] == "unavailable"


def _gspio(*arguments: str) -> int:
    return CliRunner().invoke(app, list(arguments), env={"COLUMNS": "200"}).exit_code


_MODEL = """\
from pathlib import Path
import polars as pl
from gaspatchio.assumptions import Table
HERE = Path(__file__).parent
def main(af, params=None):
    rates = Table(name="rates", source=pl.read_parquet(HERE / "rates.parquet"),
                  dimensions={"ts": "ts"}, value="v")
    af.r = rates.lookup(ts=af.q)
    af.claim = af.r * 1000.0
    return af
"""


def test_verify_does_not_agree_over_a_table_keyed_in_another_unit(
    tmp_path: Path,
) -> None:
    """The audit's false check: claims 10 and 20 under one table and graph fingerprint.

    One book holds a key of 5,000 ns. Against a table keyed [0, 5] in ms it
    reads key 0 (0.01, a claim of 10); against the same counts in us it reads
    key 5 (0.02, a claim of 20). The run over the ms file must not verify
    against the us file.
    """
    (tmp_path / "model.py").write_text(_MODEL)
    pl.DataFrame(
        {"pid": [1, 2], "q": _counts([5_000, 0], pl.Datetime("ns"))}
    ).write_parquet(tmp_path / "book.parquet")
    rates = tmp_path / "rates.parquet"
    model, book, audit = (
        str(tmp_path / name) for name in ("model.py", "book.parquet", "a.json")
    )
    pl.DataFrame(
        {"ts": _counts([0, 5], pl.Datetime("ms")), "v": [0.01, 0.02]}
    ).write_parquet(rates)
    assert _gspio("calc-graph", model, book, "-o", audit, "--profile", "audit") == 0
    pl.DataFrame(
        {"ts": _counts([0, 5], pl.Datetime("us")), "v": [0.01, 0.02]}
    ).write_parquet(rates)

    status = _gspio(
        "verify",
        audit,
        "--model",
        model,
        "--model-points",
        book,
        "--assumptions",
        str(rates),
    )

    assert status == 1
