# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book's wide column is named in the record by its values, from either door.

A ``UInt64``, ``Int128`` or ``UInt128`` column whose every value fits ``i64``
is read as ``Int64`` where a DataFrame enters the frame, so the record names
it ``i64``. Handed over as a LazyFrame, with no value in hand, the same
column kept its width in the plan, and an export with no results read
nothing: the input leaf was refused on its width alone -- ``Column 'pid' has
type UInt64, which the calculation graph has no name for`` -- so the one book
exported from one door and not the other. The export now reads such a
column off the book as it arrived, as the book's digest already does, and
names it on its numbers: ``i64`` where every value fits, the same document
from both doors, and refused naming the value where one does not.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.graph import GraphExporter

_WIDE = [pl.UInt64, pl.Int128, pl.UInt128]


def _document(book: pl.DataFrame | pl.LazyFrame, *, reads_pid: bool) -> str:
    af = ActuarialFrame(book)
    if reads_pid:
        af.r = af.pid + 1
    else:
        af.r = af.x * 2
    return GraphExporter(af).export(profile="executable", versions="withheld")


def _leaf_dtype(document: str, name: str) -> str:
    nodes = json.loads(document)["nodes"]
    return next(node["dtype"] for node in nodes if node["id"] == name)


def _unstamped(document: str) -> dict[str, object]:
    """Return the document without the moment it was written or the seal over it.

    Two exports a second boundary apart differ in ``created_at``, and so in the
    ``document_digest`` that seals it; everything else is the export's own.
    """
    parsed: dict[str, object] = json.loads(document)
    parsed.pop("created_at", None)
    parsed.pop("document_digest", None)
    return parsed


def _fits(width: type[pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame({"pid": pl.Series([7, 8], dtype=width), "x": [1.0, 2.0]})


@pytest.mark.parametrize("reads_pid", [False, True], ids=["passenger", "read"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_lazily_handed_wide_column_that_fits_exports_as_i64(
    width: type[pl.DataType], *, reads_pid: bool
) -> None:
    document = _document(_fits(width).lazy(), reads_pid=reads_pid)
    assert _leaf_dtype(document, "pid") == "i64"


@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_the_two_doors_export_one_document(width: type[pl.DataType]) -> None:
    eager = _unstamped(_document(_fits(width), reads_pid=True))
    lazy = _unstamped(_document(_fits(width).lazy(), reads_pid=True))
    assert lazy == eager


def test_a_list_of_a_wide_width_that_fits_exports_from_the_lazy_door() -> None:
    book = pl.DataFrame(
        {
            "pid": pl.Series([[7, 8], [9, 10]], dtype=pl.List(pl.UInt64)),
            "x": [1.0, 2.0],
        }
    )
    assert _leaf_dtype(_document(book.lazy(), reads_pid=False), "pid") == "list[i64]"


@pytest.mark.parametrize("lazy", [False, True], ids=["dataframe", "lazyframe"])
def test_a_value_past_i64_is_refused_by_name_from_either_door(*, lazy: bool) -> None:
    past = pl.DataFrame(
        {"pid": pl.Series([7, 2**64 - 1], dtype=pl.UInt64), "x": [1.0, 2.0]}
    )
    with pytest.raises(UnmappedDtypeError, match="holds 18446744073709551615"):
        _document(past.lazy() if lazy else past, reads_pid=False)
