# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test the Aggregator Protocol shape and _Partitioned wrapper."""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio_core.scenarios._metric import Aggregator, _Partitioned


def test_aggregator_protocol_runtime_checkable() -> None:
    """Aggregator is a runtime-checkable Protocol."""

    class Toy:
        def within_expr(self) -> None: ...
        def create_accumulator(self) -> None: ...
        def add_input(self, s: object, v: object) -> None: ...
        def merge_accumulators(self, a: object, b: object) -> None: ...
        def extract_output(self, s: object) -> None: ...
        def canonical_form(self) -> None: ...

    assert isinstance(Toy(), Aggregator)


def test_partitioned_is_not_part_of_public_protocol() -> None:
    """_Partitioned wraps an Aggregator + a partition tuple."""

    class Toy:
        def within_expr(self) -> None:
            return None

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: int) -> int:
            return s + v

        def merge_accumulators(self, a: int, b: int) -> int:
            return a + b

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "toy"}

    p = _Partitioned(by=("lob",), inner=Toy(), alias="x")
    assert isinstance(p, Aggregator)
    assert p.by == ("lob",)


def test_partitioned_add_input_matches_protocol_signature() -> None:
    """``add_input(state, value)`` — value is ``(partition_key, inner_value)``."""

    class Toy:
        def within_expr(self) -> None:
            return None

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: int) -> int:
            return s + v

        def merge_accumulators(self, a: int, b: int) -> int:
            return a + b

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "toy"}

    p = _Partitioned(by=("lob",), inner=Toy(), alias="x")
    state = p.create_accumulator()
    state = p.add_input(state, (("motor",), 10))
    state = p.add_input(state, (("annuity",), 20))
    state = p.add_input(state, (("motor",), 5))
    result = p.extract_output(state)
    rows = result.to_dicts()
    assert {"lob": "motor", "x": 15} in rows
    assert {"lob": "annuity", "x": 20} in rows


def test_partitioned_extract_output_null_safe_sort() -> None:
    """Mixed-type and None partition keys sort deterministically without TypeError."""

    class Toy:
        def within_expr(self) -> None:
            return None

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: int) -> int:
            return s + v

        def merge_accumulators(self, a: int, b: int) -> int:
            return a + b

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "toy"}

    p = _Partitioned(by=("lob",), inner=Toy(), alias="x")
    state = p.create_accumulator()
    state = p.add_input(state, (("motor",), 10))
    state = p.add_input(state, ((None,), 5))
    state = p.add_input(state, (("annuity",), 20))
    result = p.extract_output(state)
    # No TypeError. None ends up at the end.
    last_row = result.row(-1, named=True)
    assert last_row["lob"] is None


def test_partitioned_extract_output_empty_state_has_schema() -> None:
    """Zero-row result still has named columns for downstream schema work."""

    class Toy:
        def within_expr(self) -> None:
            return None

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: int) -> int:
            return s + v

        def merge_accumulators(self, a: int, b: int) -> int:
            return a + b

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "toy"}

    p = _Partitioned(by=("lob", "peril"), inner=Toy(), alias="value")
    result = p.extract_output(p.create_accumulator())
    assert result.height == 0
    assert set(result.columns) == {"lob", "peril", "value"}


def test_partitioned_validates_construction() -> None:
    """__post_init__ rejects non-Aggregator inner, empty by, empty alias."""

    class NotAnAgg:
        pass

    class Toy:
        def within_expr(self) -> None:
            return None

        def create_accumulator(self) -> int:
            return 0

        def add_input(self, s: int, v: int) -> int:
            return s + v

        def merge_accumulators(self, a: int, b: int) -> int:
            return a + b

        def extract_output(self, s: int) -> int:
            return s

        def canonical_form(self) -> dict[str, Any]:
            return {"kind": "toy"}

    with pytest.raises(TypeError, match="Aggregator Protocol"):
        _Partitioned(by=("lob",), inner=NotAnAgg(), alias="x")
    with pytest.raises(ValueError, match="at least one partition column"):
        _Partitioned(by=(), inner=Toy(), alias="x")
    with pytest.raises(ValueError, match="non-empty alias"):
        _Partitioned(by=("lob",), inner=Toy(), alias="")


def test_partitioned_merge_does_not_alias_input_accumulators() -> None:
    """`_Partitioned.merge_accumulators` must not let the result alias `a`.

    Sketch-backed inner aggregators (Quantile / Median / CTE / QuantileRank)
    hold a SignedSketch with mutable internal state. A shallow `dict(a)` in
    the merge path would let a later `add_input` on the merged state corrupt
    the original `a` accumulator. Pin the no-aliasing contract explicitly.
    """
    from gaspatchio_core.scenarios import CTE
    from gaspatchio_core.scenarios._metric import _Partitioned

    cte = CTE("loss", level=0.05, direction="upper").alias("scr")
    part = _Partitioned(by=("lob",), inner=cte, alias="scr_by_lob")

    a = part.create_accumulator()
    b = part.create_accumulator()
    a = part.add_input(a, value=(("home",), 1000.0))
    a = part.add_input(a, value=(("home",), 2000.0))
    b = part.add_input(b, value=(("motor",), 500.0))

    merged = part.merge_accumulators(a, b)

    # Snapshot the original 'a' accumulator's CTE output.
    a_home_cte_before = part.inner.extract_output(a[("home",)])

    # Mutate the merged accumulator's 'home' slot by streaming more values.
    merged = part.add_input(merged, value=(("home",), 9_999_999.0))

    # The original 'a' must still produce the same CTE output as before.
    a_home_cte_after = part.inner.extract_output(a[("home",)])

    assert a_home_cte_after == a_home_cte_before, (
        "merge_accumulators leaked aliasing into the result: mutating the "
        "merged state for partition 'home' changed the input accumulator 'a'."
    )
