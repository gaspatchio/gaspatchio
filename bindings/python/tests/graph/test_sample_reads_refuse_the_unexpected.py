# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sample read absorbs only the failure it expects: a frame with no rows.

Anything else that goes wrong while reading a sample, or while asking Polars'
meta API about an expression, is a fault in the reader, and it is raised
rather than written into the document as a sample that was not there.
"""

from __future__ import annotations

from typing import cast

import polars as pl
import pytest

from gaspatchio.frame.graph.expr_analyzer import analyze_expression_tree
from gaspatchio.frame.graph.value_extractor import SampleValueExtractor


def test_a_frame_with_no_rows_has_no_sample() -> None:
    empty = pl.DataFrame({"premium": pl.Series([], dtype=pl.Float64)})
    extractor = SampleValueExtractor(empty)

    assert extractor.extract("premium") is None
    assert extractor.extract_whole("premium") is None


@pytest.mark.parametrize("read", ["extract", "extract_whole"])
def test_a_fault_in_the_reader_is_raised_not_written_as_no_sample(
    monkeypatch: pytest.MonkeyPatch, read: str
) -> None:
    frame = pl.DataFrame({"premium": [100.0]})
    extractor = SampleValueExtractor(frame)

    def broken(column_name: str) -> object:
        msg = f"a reader fault reading {column_name}"
        raise RuntimeError(msg)

    monkeypatch.setattr(extractor, "_get_raw_value", broken)

    with pytest.raises(RuntimeError, match="a reader fault reading premium"):
        getattr(extractor, read)("premium")


def test_every_field_of_an_expression_analysis_is_read_off_polars() -> None:
    found = analyze_expression_tree((pl.col("premium") * 2).alias("doubled"))

    assert found == {
        "dependencies": ["premium"],
        "is_literal": False,
        "output_name": "doubled",
        "has_multiple_outputs": False,
    }


def test_a_meta_api_that_raises_is_not_read_as_a_missing_field() -> None:
    class _Meta:
        def root_names(self) -> list[str]:
            return ["premium"]

        def is_literal(self) -> bool:
            msg = "is_literal cannot be read"
            raise ValueError(msg)

    class _Expr:
        meta = _Meta()

    with pytest.raises(ValueError, match="is_literal cannot be read"):
        analyze_expression_tree(cast("pl.Expr", _Expr()))
