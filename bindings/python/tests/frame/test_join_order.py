# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: S603
"""A join keeps the calling frame's rows where they were, unless told otherwise.

A book's digest is taken over its rows in the order the book holds them, as a
result's ``inputs_digest`` is. A frame's join used to leave that order to
Polars, and under the streaming engine -- ``collect()``'s default -- a join
cut into morsels comes back in a different order from run to run. So a model
that joins its enrichment data in Phase 1 and rebuilds its frame from what the
join collected recorded a different book digest on every run over the same
file, and ``diff_artifacts`` reported the model points changed between two
runs that differed in nothing.

The join now keeps the frame's rows first and in their order by default --
``"left_right"`` for a left or inner join, which is a lookup keeping the rows
where they were, as VLOOKUP does, with a row's several matches in the order the
other table lists them; ``"left_right"`` for a full, right or cross join,
which also puts the other table's rows after the frame's in their own order;
``"left"`` for a semi or anti join, which only ever keeps some of the frame's
rows. An explicit ``maintain_order`` always wins, ``"none"`` included.

The stressor is ``POLARS_STREAMING_CHUNK_SIZE=1000``, which cuts the frame
into hundreds of morsels. Polars reads it once, at start-up, so it is set in
the environment of a fresh interpreter rather than of this one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from pathlib import Path

# The order each kind of join is given where the caller names none.
_DEFAULTS: dict[str, str] = {
    "left": "left_right",
    "inner": "left_right",
    "full": "left_right",
    "right": "left_right",
    "cross": "left_right",
    "semi": "left",
    "anti": "left",
}

_RUNS = 4

_SCRIPT = '''
"""Run each join the frame's way, several times, and say what came back."""

import hashlib
import json
import sys

import numpy as np
import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

runs, out = int(sys.argv[1]), sys.argv[2]
rng = np.random.default_rng(0)
n = 50_000
book = pl.DataFrame(
    {
        "policy_id": np.arange(n),
        "product": rng.choice(["term", "wl", "ul", "ann", "none"], n),
        "sum_assured": rng.uniform(1e4, 1e6, n),
    }
)
loads = pl.DataFrame(
    {
        "product": ["term", "wl", "ul", "ann", "orphan"],
        "load": [0.1, 0.2, 0.3, 0.4, 0.9],
    }
)
bands = pl.DataFrame({"band": ["a", "b", "c"]})
# Every product the book holds, listed three times over: a row of the book
# matches three of these, and "tier" says which of the three it is.
tiers = pl.DataFrame(
    {
        "product": ["term", "wl", "ul", "ann", "none"] * 3,
        "tier": [0] * 5 + [1] * 5 + [2] * 5,
    }
)


def rebuilt_book_digest() -> str:
    """Join in Phase 1, collect, rebuild the frame, export: the book it records."""
    # "none" is a product the loads do not list: a left join keeps it, null.
    af = ActuarialFrame(book).join(loads, on="product", on_missing="null")
    af = ActuarialFrame(af.collect())
    af.claims = af.sum_assured * af.load
    return json.loads(GraphExporter(af).export())["book"]["digest"]


def joined(how):
    """Return what the frame's join gives back for one kind, and its rows' ids."""
    if how == "cross":
        frame = ActuarialFrame(book.head(2_000)).join(bands, how="cross").collect()
    else:
        kept = "null" if how == "left" else "raise"
        frame = (
            ActuarialFrame(book)
            .join(loads, on="product", how=how, on_missing=kept)
            .collect()
        )
    rows = frame["policy_id"]
    kept = rows.drop_nulls()
    # The frame's rows first, in their order; anything else after them.
    first = len(kept) == 0 or rows[: len(kept)].null_count() == 0
    return hashlib.sha256(frame.write_ipc(None).getvalue()).hexdigest(), bool(
        first and kept.is_sorted()
    )


chunked = ActuarialFrame(book).join(loads, on="product", on_missing="null").collect()
result = {"n_chunks": chunked.n_chunks()}
result["book"] = len({rebuilt_book_digest() for _ in range(runs)})
for how in ("left", "inner", "full", "right", "cross", "semi", "anti"):
    seen = [joined(how) for _ in range(runs)]
    result[how] = {
        "distinct": len({one[0] for one in seen}),
        "in_order": all(one[1] for one in seen),
    }
for how in ("left", "inner"):
    outputs, in_tier_order = set(), True
    for _ in range(runs):
        frame = ActuarialFrame(book).join(tiers, on="product", how=how).collect()
        outputs.add(hashlib.sha256(frame.write_ipc(None).getvalue()).hexdigest())
        # Each policy's three matches, in the order they came back.
        tiers_seen = frame["tier"].to_numpy().reshape(-1, 3)
        in_tier_order = in_tier_order and bool((tiers_seen == [0, 1, 2]).all())
    result[f"{how}_repeated"] = {"distinct": len(outputs), "in_order": in_tier_order}
with open(out, "w") as written:
    json.dump(result, written)
'''


@pytest.fixture(scope="module")
def under_small_morsels(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Run the joins in a fresh interpreter that streams in 1000-row morsels."""
    where: Path = tmp_path_factory.mktemp("join_order")
    script = where / "join_order.py"
    script.write_text(_SCRIPT)
    out = where / "result.json"
    finished = subprocess.run(
        [sys.executable, str(script), str(_RUNS), str(out)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "POLARS_STREAMING_CHUNK_SIZE": "1000"},
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    result: dict[str, Any] = json.loads(out.read_text())
    # The stressor has to be live, or every assertion below passes for the
    # wrong reason: forced 1000-row morsels cut 50,000 rows into dozens of
    # chunks, where the default cutting gives one per core.
    assert result["n_chunks"] > 20, result
    return result


def test_a_book_joined_and_rebuilt_digests_alike_on_every_run(
    under_small_morsels: dict[str, Any],
) -> None:
    """The documented Phase 1: join, collect, rebuild -- one book, one digest."""
    assert under_small_morsels["book"] == 1


@pytest.mark.parametrize("how", list(_DEFAULTS))
def test_every_kind_of_join_keeps_the_frame_s_rows_first_and_in_order(
    how: str, under_small_morsels: dict[str, Any]
) -> None:
    """Deterministic from run to run, and the frame's rows where they were."""
    assert under_small_morsels[how] == {"distinct": 1, "in_order": True}


@pytest.mark.parametrize("how", ["left", "inner"])
def test_a_row_matched_more_than_once_gets_its_matches_in_the_other_table_s_order(
    how: str, under_small_morsels: dict[str, Any]
) -> None:
    """A lookup whose table repeats a key: one answer, and the table's order.

    ``"left"`` keeps the frame's rows where they were but not the order of a
    row's several matches, which the streaming engine hands back differently
    from run to run; ``"left_right"`` orders them as the other table lists them.
    """
    assert under_small_morsels[f"{how}_repeated"] == {"distinct": 1, "in_order": True}


@pytest.mark.parametrize(("how", "order"), list(_DEFAULTS.items()))
def test_each_kind_of_join_is_handed_its_order_where_none_is_named(
    how: str, order: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The setting Polars is given, kind by kind, where the caller names none."""
    asked: list[object] = []
    real = pl.LazyFrame.join

    def spy(self: pl.LazyFrame, *args: Any, **kwargs: Any) -> pl.LazyFrame:  # noqa: ANN401
        asked.append(kwargs.get("maintain_order"))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pl.LazyFrame, "join", spy)
    af = ActuarialFrame({"product": ["term", "wl"], "premium": [1.0, 2.0]})
    other = pl.DataFrame({"product": ["term", "wl"], "load": [0.1, 0.2]})
    if how == "cross":
        af.join(other.rename({"product": "code"}), how=how)
    else:
        af.join(other, on="product", how=how)

    assert asked == [order]


@pytest.mark.parametrize("named", ["none", "left", "right", "left_right", "right_left"])
def test_an_order_the_caller_names_is_passed_through_untouched(
    named: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``"none"`` is how a caller asks for Polars' faster unordered join."""
    asked: list[object] = []
    real = pl.LazyFrame.join

    def spy(self: pl.LazyFrame, *args: Any, **kwargs: Any) -> pl.LazyFrame:  # noqa: ANN401
        asked.append(kwargs.get("maintain_order"))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pl.LazyFrame, "join", spy)
    af = ActuarialFrame({"product": ["term", "wl"], "premium": [1.0, 2.0]})
    af.join(
        pl.DataFrame({"product": ["term", "wl"], "load": [0.1, 0.2]}),
        on="product",
        maintain_order=named,
    )

    assert asked == [named]
