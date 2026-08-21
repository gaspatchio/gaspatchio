# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Aggregator Protocol (Beam-style CombineFn 5-tuple) + _Partitioned wrapper.
# ABOUTME: Aggregators are partition-blind; partition lives in the driver.

"""Aggregator Protocol and partition wrapper for GSP-101.

The Aggregator contract (5-tuple) is a Beam-style CombineFn:

* ``within_expr()``        - within-scenario reduction (polars Expr today)
* ``create_accumulator()`` - fresh state
* ``add_input(state, v)``  - fold one per-scenario value
* ``merge_accumulators``   - associative + commutative state combine
* ``extract_output(s)``    - produce the final value

Plus ``canonical_form()`` for the audit chain.

Partition lives in the driver via ``_Partitioned``, never inside the
aggregator.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import polars as pl


def _null_safe_sort_key(
    item: tuple[tuple[Any, ...], Any],
) -> tuple[tuple[int, str, Any], ...]:
    """Sort partition tuples deterministically.

    None sorts last; otherwise group by type so values compare naturally
    within their type (int 9 < int 10), without cross-type comparisons
    (which would raise TypeError on str vs int).
    """
    return tuple(
        (1, "", None) if v is None else (0, type(v).__name__, v)
        for v in item[0]
    )


@runtime_checkable
class Aggregator(Protocol):
    """Beam-style CombineFn contract for scenario aggregation.

    Optional class attribute: ``requires_scenario_id: ClassVar[bool] = False``.
    Aggregators that need to record the scenario identity (e.g. ArgMin/ArgMax)
    override this to True; the loop will then pack ``(scenario_id, value)``
    tuples into ``add_input`` rather than bare values. The attribute is not
    enforced by ``@runtime_checkable`` (Python Protocols pre-3.13 cannot
    express class attributes natively); the driver reads it via ``getattr``
    with a False default.
    """

    def within_expr(self) -> pl.Expr: ...
    def create_accumulator(self) -> Any: ...  # noqa: ANN401
    def add_input(self, state: Any, value: Any) -> Any: ...  # noqa: ANN401
    def merge_accumulators(self, a: Any, b: Any) -> Any: ...  # noqa: ANN401
    def extract_output(self, state: Any) -> Any: ...  # noqa: ANN401
    def canonical_form(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _Partitioned:
    """Internal driver wrapper. Not exposed in the public surface.

    Holds ``dict[partition_tuple, inner_accumulator]`` state and routes
    ``add_input`` calls to the right slot. The wrapped aggregator is
    partition-blind.
    """

    by: tuple[str, ...]
    inner: Aggregator
    alias: str

    def __post_init__(self) -> None:
        if not isinstance(self.inner, Aggregator):
            msg = (
                "inner must implement the Aggregator Protocol; "
                f"got {type(self.inner).__name__}"
            )
            raise TypeError(msg)
        if not self.by:
            msg = "_Partitioned requires at least one partition column in `by`"
            raise ValueError(msg)
        if not self.alias:
            msg = "_Partitioned requires a non-empty alias"
            raise ValueError(msg)

    # The Aggregator-shaped methods the loop will call:
    def within_expr(self) -> pl.Expr:
        return self.inner.within_expr()

    def create_accumulator(self) -> dict[tuple[Any, ...], Any]:
        return {}

    def add_input(
        self,
        state: dict[tuple[Any, ...], Any],
        value: tuple[tuple[Any, ...], Any],
    ) -> dict[tuple[Any, ...], Any]:
        """Fold one input into the partitioned accumulator state.

        ``value`` is a 2-tuple ``(partition_key, inner_value)``.
        ``partition_key`` is itself a tuple (one element per ``by`` column).
        """
        partition_key, inner_value = value
        if partition_key not in state:
            state[partition_key] = self.inner.create_accumulator()
        state[partition_key] = self.inner.add_input(state[partition_key], inner_value)
        return state

    def merge_accumulators(
        self,
        a: dict[tuple[Any, ...], Any],
        b: dict[tuple[Any, ...], Any],
    ) -> dict[tuple[Any, ...], Any]:
        # Deep-copy entries carried over from ``a`` so the merged state does
        # not alias the input. Sketch-backed inner aggregators (Quantile,
        # Median, CTE, QuantileRank) hold a SignedSketch whose ``add`` mutates
        # state in place; a shallow ``dict(a)`` would let a later ``add_input``
        # on the merged state silently corrupt ``a``.
        out: dict[tuple[Any, ...], Any] = {k: copy.deepcopy(v) for k, v in a.items()}
        for k, v in b.items():
            out[k] = self.inner.merge_accumulators(out[k], v) if k in out else v
        return out

    def extract_output(self, state: dict[tuple[Any, ...], Any]) -> pl.DataFrame:
        import polars as pl

        if not state:
            schema: dict[str, Any] = dict.fromkeys(self.by, pl.Object)
            schema[self.alias] = pl.Object
            return pl.DataFrame(schema=schema)

        rows = []
        for partition_tuple, acc in sorted(state.items(), key=_null_safe_sort_key):
            row = dict(zip(self.by, partition_tuple, strict=True))
            row[self.alias] = self.inner.extract_output(acc)
            rows.append(row)
        return pl.DataFrame(rows)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "_Partitioned",
            "by": list(self.by),
            "inner": self.inner.canonical_form(),
        }


__all__ = ["Aggregator", "_Partitioned"]
