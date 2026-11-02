# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The kit's content-grammar vectors are the producer's own bytes.

``conformance/content-identity.json`` publishes section 12.3's bytes for
frames described in plain JSON -- the datetime carrier above all: the zone in
the column's header, each value its microsecond and then its sub-microsecond
nanoseconds -- so a second implementation can check its encoder against the
same cases the core's unit tests pin. Both of this producer's encoders, the
native one and the Python reference, must write those bytes, and the kit's
standard-library reader must re-derive them and refuse a mutation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from gaspatchio._identity import (
    _content_bytes_of_reference,
    content_bytes_of,
    content_sha_of,
)

_ROOT = Path(__file__).resolve().parents[4]
_KIT = _ROOT / "bindings/python/gaspatchio/schemas/conformance"
_VECTORS = _KIT / "content-identity.json"
_READER = _ROOT / "spec/graph-artifact/conformance/content.py"
_CASES: list[dict[str, Any]] = json.loads(_VECTORS.read_text())["cases"]
_WRITTEN = [case for case in _CASES if "refusal" not in case]
_REFUSED = [case for case in _CASES if "refusal" in case]
# Each refusal code, in the words both of this producer's encoders refuse with.
_REFUSED_AS = {"datetime-microseconds-past-i64": "leaves the 64-bit whole number"}
_SIMPLE = {"i64": pl.Int64, "f64": pl.Float64, "bool": pl.Boolean, "str": pl.String}


def _instants(values: list[Any], unit: str, zone: str | None) -> pl.Series:
    series = pl.Series(values, dtype=pl.Int64).cast(pl.Datetime(unit))  # type: ignore[arg-type]
    if zone is None:
        return series
    return series.dt.replace_time_zone("UTC").dt.convert_time_zone(zone)


def _series(column: dict[str, Any]) -> pl.Series:
    dtype, values = column["dtype"], column["values"]
    if dtype == "datetime":
        series = _instants(values, column["unit"], column["zone"])
    elif dtype == "list[datetime]":
        # Each member is an instant in the column's unit and zone; rebuild
        # the rows around the flattened members, keeping a missing row.
        members = [member for row in values if row is not None for member in row]
        flat = _instants(members, column["unit"], column["zone"])
        rows: list[Any] = []
        at = 0
        for row in values:
            if row is None:
                rows.append(None)
                continue
            rows.append(flat[at : at + len(row)].to_list())
            at += len(row)
        series = pl.Series(rows, dtype=pl.List(flat.dtype))
    elif dtype == "date":
        series = pl.Series([date.fromisoformat(v) for v in values], dtype=pl.Date)
    else:
        series = pl.Series(values, dtype=_SIMPLE[dtype])
    return series.alias(column["name"])


def _frame(case: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame([_series(column) for column in case["columns"]])


@pytest.mark.parametrize("case", _WRITTEN, ids=[case["id"] for case in _WRITTEN])
def test_both_encoders_write_the_published_bytes(case: dict[str, Any]) -> None:
    frame = _frame(case)

    assert content_bytes_of(frame).hex() == case["bytes"]
    assert _content_bytes_of_reference(frame).hex() == case["bytes"]
    assert content_sha_of(frame) == case["digest"]


def test_one_instant_in_any_unit_shares_a_digest_and_a_zone_or_500_ns_parts_it() -> (
    None
):
    digest = {case["id"]: case["digest"] for case in _WRITTEN}
    naive = digest["datetime-naive-microseconds"]

    assert digest["datetime-same-instant-in-milliseconds"] == naive
    assert digest["datetime-same-instant-in-nanoseconds"] == naive
    assert digest["datetime-utc-digests-as-naive"] == naive
    assert digest["datetime-zone-in-the-header"] != naive
    two = next(
        c for c in _CASES if c["id"] == "datetime-sub-microsecond-instants-apart"
    )
    first, second = (
        content_sha_of(_frame({"columns": [{**two["columns"][0], "values": [v]}]}))
        for v in two["columns"][0]["values"]
    )
    assert first != second


def test_the_kit_publishes_the_wrapped_millisecond_as_a_refusal() -> None:
    """A ms count past i64 in microseconds is refused, both sides of zero (12.3)."""
    assert sorted(case["id"] for case in _REFUSED) == [
        "datetime-milliseconds-before-i64-refused",
        "datetime-milliseconds-past-i64-refused",
    ]
    assert {case["refusal"] for case in _REFUSED} <= set(_REFUSED_AS)


@pytest.mark.parametrize("case", _REFUSED, ids=[case["id"] for case in _REFUSED])
def test_the_python_reference_refuses_each_refusal_case_by_name(
    case: dict[str, Any],
) -> None:
    frame = _frame(case)

    with pytest.raises(ValueError, match=_REFUSED_AS[case["refusal"]]) as refused:
        _content_bytes_of_reference(frame)
    assert f"Column '{case['columns'][0]['name']}'" in str(refused.value)


@pytest.mark.parametrize("case", _REFUSED, ids=[case["id"] for case in _REFUSED])
def test_the_native_encoder_refuses_each_refusal_case_by_name(
    case: dict[str, Any],
) -> None:
    """Needs the core built with the refusal of a ms count past i64 (core/src/identity.rs)."""
    frame = _frame(case)

    for door in (content_bytes_of, content_sha_of):
        with pytest.raises(ValueError, match=_REFUSED_AS[case["refusal"]]):
            door(frame)


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed interpreter and local kit files
        [sys.executable, "-I", *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def test_the_kit_reader_re_derives_every_case() -> None:
    result = _run(str(_READER), str(_VECTORS))

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "algorithm": "gspv0-preview-3",
        "cases": len(_CASES),
        "failures": {},
    }


def test_the_packaged_reader_runs_outside_the_repository(tmp_path: Path) -> None:
    directory = shutil.copytree(_KIT, tmp_path / "conformance")
    result = _run(
        str(directory / "reader.pyz"),
        "--content",
        str(directory / "content-identity.json"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["cases"] == len(_CASES)


def test_the_kit_reader_refuses_a_moved_nanosecond(tmp_path: Path) -> None:
    document = json.loads(_VECTORS.read_text())
    case = next(
        c
        for c in document["cases"]
        if c["id"] == "datetime-nanosecond-before-the-epoch"
    )
    case["columns"][0]["values"] = [-2]  # 998 ns past microsecond -1
    source = tmp_path / "moved.json"
    source.write_text(json.dumps(document))

    result = _run(str(_READER), str(source))

    assert result.returncode == 1
    assert list(json.loads(result.stdout)["failures"]) == [case["id"]]


def test_the_kit_reader_names_a_refusal_it_did_not_meet(tmp_path: Path) -> None:
    document = json.loads(_VECTORS.read_text())
    case = next(c for c in document["cases"] if "refusal" in c)
    case["columns"][0]["values"] = [9_223_372_036_854_775]  # the edge: it fits
    source = tmp_path / "fits.json"
    source.write_text(json.dumps(document))

    result = _run(str(_READER), str(source))

    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert list(failures) == [case["id"]]
    assert failures[case["id"]][0].startswith("not refused")
