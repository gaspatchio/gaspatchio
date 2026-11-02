# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A batch's checks come back as a count and a first cell each, and nothing moves.

Every check a compiled program carries is a mask over its batch's cells,
and a finding needs two numbers from it: how many cells it caught, and the
first of them in row-major order, off which the book's policy and period are
read. So the program counts where it computed the mask and hands back those
two numbers for every check, in one array; a coarse check's mask and operands
come back besides, and are read only where its count is above nought, for the
host's exact judgement. The counts, the first positions, their sentences, the
refusal groups and the merge across batches may not move -- only where the
counting happens. Four things hold that here:

* **The reduction itself** (:func:`gaspatchio_jax.checks.tallied`), as the
  program computes it -- on the device, every mask in one array -- against
  NumPy's own reading of the same masks, ``np.flatnonzero``, which is what the
  host scan used: masks of one cell a policy and of policies by periods, with
  nothing caught, one cell, the last cell, every cell, and cells at random.
* **Every finding, side by side** with what the same region pass gives when
  every mask is handed back whole and scanned on the host (:func:`_before`)
  -- the reading completion made before the card counted, done with today's region pass
  and today's scan -- on levels 4 and 5 with a domain check, a lookup miss
  and a coarse overflow put into their books, in several batches, one batch
  at a time and one ahead. It shares the region pass and the scan with the
  engine, so it shows that counting on the card moves nothing, and not that
  either of those is right.
* **The findings themselves, written out**, for level 4's injected book:
  what the engine found there while it still scanned every mask on the host,
  as literals, so that a defect the side-by-side shares with the engine -- a
  first cell read a period late, a mask not held to its horizon -- still fails.
* **The coarse checks' judgement**, which is the host's as it always was: a
  batch whose caught cells are all inside i64 finds nothing, a batch with one
  outside finds exactly it, and a batch whose program caught nothing reads
  nothing of the check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

import jax
import jax.numpy as jnp
import numpy as np
import polars as pl
import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.checks import Carried, FlagBook, tallied
from gaspatchio_jax.plan import ExecutionPlan, _axes_in
from gaspatchio_jax.preflight import Finding, findings_of, merged_findings
from tests.conftest import PROJECT, invocation
from tests.helpers import streamed

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio_jax.checks import Flagged
    from gaspatchio_jax.plan import Prepared
    from gaspatchio_jax.vectors import Invocation

# The two depths the engine runs at: one batch at a time, and one ahead.
DEPTHS: Final = (0, 1)

# ---------------------------------------------------------------------------
# The reduction, against NumPy's reading of the same masks
# ---------------------------------------------------------------------------

# One cell a policy; policies by periods; and a per-policy value spread along
# one period, which is how a check over an operand of each shape stands --
# from a single cell to a batch's width. A row's count is held in a byte up to
# 255 periods and in a wider integer past it, so both sides of that line are
# here; and a mask of one cell and one of three axes, which no check raises
# today, are read the same way.
SHAPES: Final = (
    (),
    (1,),
    (5,),
    (64,),
    (1, 1),
    (7, 1),
    (3, 12),
    (64, 84),
    (37, 120),
    (2, 255),
    (2, 256),
    (3, 1200),
    (2, 3, 4),
)
KINDS: Final = ("none caught", "one cell", "the last cell", "every cell", "at random")

# How densely a random mask is caught: a rare defect, a common one, and half.
DENSITIES: Final = (0.001, 0.05, 0.5)

# Masks of each shape and kind per test: enough that a random kind is many.
REPEATS: Final = 25

SEED: Final = 67

# The reduction as a program computes it: compiled, on the device.
_ON_THE_CARD = jax.jit(tallied)


def _mask(shape: tuple[int, ...], kind: str, rng: np.random.Generator) -> np.ndarray:
    """Return one mask of this shape, caught as the kind says."""
    size = int(np.prod(shape))
    caught = np.zeros(size, dtype=bool)
    if kind == "one cell":
        caught[int(rng.integers(size))] = True
    elif kind == "the last cell":
        caught[-1] = True
    elif kind == "every cell":
        caught[:] = True
    elif kind == "at random":
        caught = rng.random(size) < rng.choice(DENSITIES)
    return caught.reshape(shape)


def _as_numpy_reads_it(mask: np.ndarray) -> tuple[int, int | None]:
    """Return the count and the first caught cell, as the host scan read them."""
    caught = np.flatnonzero(mask)
    return int(caught.size), (int(caught[0]) if caught.size else None)


def _held(tallies: jax.Array, masks: Sequence[np.ndarray]) -> None:
    """Hold what the card counted to what NumPy reads off the same masks."""
    assert tallies.dtype == jnp.int64
    assert tallies.shape == (2, len(masks))
    counts, firsts = np.asarray(tallies)
    for at, mask in enumerate(masks):
        count, first = _as_numpy_reads_it(mask)
        assert int(counts[at]) == count, (at, mask.shape)
        # Nought where nothing was caught, which is also where a first caught
        # cell at the start points: the count is what tells the two apart.
        assert int(firsts[at]) == (0 if first is None else first), (at, mask.shape)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES, ids=str)
def test_the_card_counts_a_mask_as_numpy_reads_it(
    shape: tuple[int, ...], kind: str
) -> None:
    """The count and the first caught cell of every mask, exactly as NumPy has them."""
    rng = np.random.default_rng([SEED, *shape, KINDS.index(kind)])
    masks = [_mask(shape, kind, rng) for _ in range(REPEATS)]
    _held(_ON_THE_CARD([jnp.asarray(one) for one in masks]), masks)


def test_every_check_of_a_program_is_counted_in_one_array() -> None:
    """Every shape and kind at once, as one program counts all its checks.

    With the masks of a book of no policies -- one cell a policy and
    policies by periods, which the conformance kit's empty portfolios raise
    -- and one whose cells are numbers rather than truths, where a cell is
    caught if it is not nought. And a program with no checks at all hands
    back an array of no columns.
    """
    rng = np.random.default_rng(SEED)
    masks = [_mask(shape, kind, rng) for shape in SHAPES for kind in KINDS]
    masks += [
        np.zeros((0,), dtype=bool),
        np.zeros((0, 1), dtype=bool),
        np.zeros((0, 12), dtype=bool),
        np.asarray([[0, 2, 0], [1, 0, 3]], dtype=np.int8),
    ]
    _held(_ON_THE_CARD([jnp.asarray(one) for one in masks]), masks)
    assert _ON_THE_CARD([]).shape == (2, 0)


# ---------------------------------------------------------------------------
# Every finding, side by side with every mask read whole
# ---------------------------------------------------------------------------

MODELS: Final = PROJECT / "tests/models"

# Batches small enough that each book is nine of them.
BATCH: Final = 128

# A policy term whose maturity month, twelve times it, has left i64 and wraps
# to 1,208 months: the wrapped term is positive, so the policy keeps an
# ordinary timeline and stands in its own batch rather than in a group of the
# policies with none.
_WRAPS: Final = 2**64 // 12 + 101

# What is put into each shipped book, by policy -- each kind of finding the
# checks report, in batches of their own.
INJECTED: Final[dict[str, dict[int, int]]] = {
    "age_at_entry": {
        # A lookup miss: an entry age the select table has no row for, on a
        # key the model calculates (the attained age).
        7: 150,
        301: 150,
        650: 150,
        # A domain check: the attained age, entry age plus duration, is a
        # whole-number sum that leaves i64 (11.1.25), an exact check.
        120: 2**63 - 5,
        777: 2**63 - 5,
    },
    "policy_term": {
        # The coarse check: the maturity month is the term times twelve, a
        # product the in-trace test catches over 2^62 and the host judges.
        # These two have left i64 ...
        44: _WRAPS,
        530: _WRAPS,
        # ... and these two are caught and have not: six times 10^18.
        260: 5 * 10**17,
        900: 5 * 10**17,
    },
}

# The findings each of those makes, and the nodes they are about: every one
# must be found, in two batches or more.
EXPECTED: Final = (
    ("lookup.miss_raise", "base_mort_rate@1"),
    ("i64.range", "age@1"),
    ("i64.range", "maturity_month@1"),
)


@dataclass
class Injected:
    """One shipped model over its book with failures put in, prepared once.

    Attributes:
        plan: The plan, which keeps the programs its batches compiled.
        prepared: The book, settled on the host.
        before: Per batch, by its rows, the findings every mask read whole
            gave -- kept, because one batch at a time and one ahead run the
            same batches.

    """

    plan: ExecutionPlan
    prepared: Prepared
    before: dict[tuple[int, ...], tuple[Finding, ...]] = field(default_factory=dict)


@pytest.fixture(scope="module", params=("level-4", "level-5"))
def injected(request: pytest.FixtureRequest) -> Injected:
    """Return a shipped model's book with a domain check, a miss and an overflow."""
    model = request.param
    artifact = json.loads((MODELS / f"{model}.artifact.json").read_text("utf-8"))
    book = pl.read_parquet(MODELS / f"{model}.book.parquet")
    for column, cells in INJECTED.items():
        values = book[column].to_list()
        for policy, value in cells.items():
            values[policy] = value
        book = book.with_columns(pl.Series(column, values, dtype=pl.Int64))
    plan = ExecutionPlan.stage_inspect(artifact)
    return Injected(plan, plan.stage_prepare(plan.stage_validate_inputs(book)))


def _before(
    plan: ExecutionPlan, prepared: Prepared, rows: np.ndarray
) -> tuple[Finding, ...]:
    """Return one batch's findings from every mask, handed back whole and scanned.

    The batch is settled again and its region pass traced again -- the
    program's own (``_traced``) -- to hand back every check's mask as its
    node's horizon held it, with every coarse check's operands; the host scan
    (:func:`findings_of`) then reads them with the settlement's own flags in
    front. That is the reading completion made of every batch before the card counted,
    but done with today's region pass and today's scan rather than the
    engine of that day, so it holds where the counting happens and nothing
    else: the region pass and the scan are the engine's own on both sides,
    and the findings written out below are what holds those.
    """
    settled = plan.stage_settle(prepared, rows)
    raised: list[Flagged] = []

    def every_mask(
        arrays: tuple[jax.Array, ...], counts: tuple[jax.Array, ...]
    ) -> list[tuple[jax.Array, tuple[jax.Array, ...]]]:
        _axes, computed = plan._traced(settled, arrays, counts)  # noqa: SLF001 -- the region pass itself
        raised[:] = computed.flags.entries
        return [(entry.mask, entry.operands) for entry in raised]

    handed = jax.jit(every_mask)(
        tuple(value.array for value in settled.values.values()),
        tuple(axis.t for axis in _axes_in(settled.values)),
    )
    book = FlagBook(
        [
            *settled.flags.entries,
            *(
                replace(entry, mask=mask, operands=tuple(operands))
                for entry, (mask, operands) in zip(raised, handed, strict=True)
            ),
        ]
    )
    return findings_of(book, rows)


@pytest.fixture
def judged(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Return every coarse judgement the host makes, as the check and what survived."""
    made: list[tuple[str, int]] = []
    judging = Carried.judged

    def recorded(
        self: Carried, mask: jax.Array, operands: Sequence[jax.Array]
    ) -> list[int]:
        positions = judging(self, mask, operands)
        made.append((self.where, len(positions)))
        return positions

    monkeypatch.setattr(Carried, "judged", recorded)
    return made


@pytest.mark.parametrize("depth", DEPTHS, ids=["one at a time", "one ahead"])
def test_every_finding_is_the_one_every_mask_read_whole_gave(
    injected: Injected, depth: int, judged: list[tuple[str, int]]
) -> None:
    """Batch by batch and merged: the same checks, counts, first cells and notes.

    Each of the three kinds is found in more than one batch -- a domain check
    (two, one exact integer sum and one comparison), a lookup miss, and a
    coarse overflow -- beside the note every batch of these books reports
    (the empty surrender-charge cell, whose null key is a miss). The coarse
    check is judged on the host in exactly the four batches its in-trace
    test caught a cell of: two with an overflow, and two whose caught cells
    are all inside i64, which find nothing.
    """
    plan, prepared = injected.plan, injected.prepared
    found: list[Finding] = []
    before: list[Finding] = []
    batches: dict[tuple[str, str], set[int]] = {}
    for at, batched in enumerate(
        plan.stage_batches(prepared, batch=BATCH, depth=depth)
    ):
        rows = tuple(int(one) for one in batched.rows)
        if rows not in injected.before:
            injected.before[rows] = _before(plan, prepared, batched.rows)
        assert batched.findings == injected.before[rows], rows[:3]
        found.extend(batched.findings)
        before.extend(injected.before[rows])
        for one in batched.findings:
            batches.setdefault((one.name, one.where), set()).add(at)
    host = findings_of(prepared.flags)
    merged = merged_findings([*host, *found])
    assert merged == merged_findings([*host, *before])
    assert all(len(batches.get(expected, ())) >= 2 for expected in EXPECTED), batches
    assert any(not one.refuses for one in merged)
    assert sorted(judged) == [("maturity_month@1", count) for count in (0, 0, 1, 1)]


# What the engine found in level 4's injected book while it still scanned every
# mask whole on the host, in batches of BATCH, written out rather than
# recomputed, and the same one batch at a time and one ahead. Merged over the
# book, the host stage's own finding in front, as completion reads them.
_BLANK_ARRIVING_NOTE: Final = (
    "rows of this join match a right-side row whose 'surr_charge_id' is not "
    "there; the column is null for them, and a read keyed on it is a miss"
)
PINNED: Final = (
    Finding("i64.range", "term_months_left@1", 2, "row 44", (44, 0)),
    Finding(
        "join.blank_arriving",
        "surr_charge_id@1",
        491,
        "row 1",
        (1, 0),
        _BLANK_ARRIVING_NOTE,
    ),
    Finding("i64.range", "age@1", 145, "policy 120, period 0", (120, 0)),
    Finding("lookup.miss_raise", "base_mort_rate@1", 415, "policy 7, period 0", (7, 0)),
    Finding("i64.range", "maturity_month@1", 2, "row 44", (44, 0)),
)

# And the seventh batch's own (policies 768 to 895), where a first caught cell
# is at a period other than the first: policy 777's attained age leaves i64 at
# its twenty-first period.
PINNED_AT_768: Final = (
    Finding(
        "join.blank_arriving",
        "surr_charge_id@1",
        56,
        "row 769",
        (769, 0),
        _BLANK_ARRIVING_NOTE,
    ),
    Finding("i64.range", "age@1", 62, "policy 777, period 21", (777, 21)),
    Finding(
        "lookup.miss_raise", "base_mort_rate@1", 83, "policy 777, period 0", (777, 0)
    ),
)


@pytest.mark.parametrize("injected", ["level-4"], indirect=True)
@pytest.mark.parametrize("depth", DEPTHS, ids=["one at a time", "one ahead"])
def test_level_4_s_injected_book_finds_what_the_host_scan_found(
    injected: Injected, depth: int
) -> None:
    """Written out rather than recomputed, so a defect the scan shares still fails.

    The side-by-side above reads every mask through the engine's own region
    pass and scan, so a first cell read a period late there, or a mask not
    held to its horizon, would move both of its sides and pass. These are the
    findings the engine made of this book while it scanned every mask on the
    host: merged over the book, and one batch's own.
    """
    plan, prepared = injected.plan, injected.prepared
    batches = [
        (int(batched.rows[0]), batched.findings)
        for batched in plan.stage_batches(prepared, batch=BATCH, depth=depth)
    ]
    found = [one for _first, findings in batches for one in findings]
    assert merged_findings([*findings_of(prepared.flags), *found]) == PINNED
    assert dict(batches)[768] == PINNED_AT_768


# ---------------------------------------------------------------------------
# The coarse checks, judged on the host exactly as ever
# ---------------------------------------------------------------------------

# Four batches of three: nothing near the range; caught and inside; one
# outside beside one caught and inside; and INT64_MIN, which is exactly
# inside, beside one outside.
PRODUCTS: Final = (
    (3, 5),
    (7, 11),
    (13, 17),
    (1, 2),
    (2**61 + 1, 3),
    (5, 5),
    (1, 1),
    (2**62, 2),
    (2**61 + 1, 3),
    (4, 4),
    (-(2**62), 2),
    (2**62, -3),
)


def _a_product(pairs: Sequence[tuple[int, int]]) -> Invocation:
    """Return whole numbers multiplied, one per policy: 11.1.25's coarse check."""
    return invocation(
        {
            "op": "binop",
            "kind": "mul",
            "left": {"op": "col", "name": "a"},
            "right": {"op": "col", "name": "b"},
        },
        {
            "a": {"dtype": "i64", "values": [left for left, _right in pairs]},
            "b": {"dtype": "i64", "values": [right for _left, right in pairs]},
        },
        "i64",
    )


@pytest.mark.parametrize("depth", DEPTHS, ids=["one at a time", "one ahead"])
def test_a_coarse_check_is_judged_only_where_the_card_caught_a_cell(
    depth: int, judged: list[tuple[str, int]]
) -> None:
    """The first batch reads nothing; the second finds nothing; the last two, one each.

    The card counts the cells the in-trace test caught, which over-reaches:
    ``3 * (2^61 + 1)`` is past 2^62 and inside i64, and ``-2^62 * 2`` is
    INT64_MIN exactly. The host judges those batches' cells as it always
    did, and a batch whose program caught nothing is not judged at all.
    """
    one = _a_product(PRODUCTS)
    plan = ExecutionPlan.stage_inspect(one.document)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(one.inputs))
    found = [
        [(finding.name, finding.count, finding.first) for finding in batched.findings]
        for batched in plan.stage_batches(prepared, batch=3, depth=depth)
    ]
    assert found == [
        [],
        [],
        [("i64.range", 1, "row 7")],
        [("i64.range", 1, "row 11")],
    ]
    assert [count for _where, count in judged] == [0, 1, 1]
    with pytest.raises(EngineRefusal) as refused:
        streamed(one, FrameSink(), batch=3, depth=depth)
    (refusal,) = refused.value.report.refusals
    assert refusal.count == 2
    assert "first at row 7" in refusal.what


def test_a_book_whose_caught_cells_are_all_inside_publishes_them_exactly() -> None:
    """Caught by the in-trace test in every batch, and not one of them wrong."""
    pairs = [(2**61 + 1, 3), (-(2**62), 2)] * 3
    result = streamed(_a_product(pairs), FrameSink(), batch=2)
    assert result.columns["answer"].to_list() == [left * right for left, right in pairs]


def test_a_batch_hands_back_two_numbers_a_check_and_a_coarse_check_s_cells() -> None:
    """Level 4's 81 checks as one array of two rows, and its one coarse check's cells.

    A batch used to hand back every check's mask, a cell of the batch
    each: on level 4, 4.1 KB a policy. Now it hands back two numbers a check
    for the whole batch, and one coarse check's mask and operands.

    The count is the tree's, so it moves when the tree does. It was 142 while
    the account value's accumulate mixed a whole-number opening balance into
    float arithmetic unrecorded, and while the capped durations came out of
    their conditionals as floats: the mix carried a 2**53 check, and each of
    the four lookups keyed on a float duration carried a 2**53 check and a
    key-range check of its own. The tree now records the conversion as
    ``to_float`` and keeps the capped durations whole numbers, so the engine
    checks the one conversion it is told about -- ``to_float.exact`` -- and
    a whole-number key is read as one with nothing to check. It was 134 while
    a per-period comparison of two whole numbers carried a 2**53 check on each
    operand; such a comparison is exact over the whole of i64 (11.1.26), so
    it carries none. It was 88 while each of the seven comparisons of two
    doubles carried a check refusing a NaN or an infinity in every cell; a
    NaN now has the comparison's answer (11.1.26), so they carry none.
    """
    artifact = json.loads((MODELS / "level-4.artifact.json").read_text("utf-8"))
    book = pl.read_parquet(MODELS / "level-4.book.parquet")
    plan = ExecutionPlan.stage_inspect(artifact)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
    settled = plan.stage_settle(prepared, np.arange(64))
    program, _outcome = plan.compile_for(settled)
    dispatched = plan.stage_dispatch(settled, program)
    coarse = [one for one in program.flags if one.judgement is not None]
    assert len(program.flags) == 81
    assert dispatched.tallies.shape == (2, 81)
    named = {(one.name, one.where) for one in program.flags}
    assert ("to_float.exact", "av_pp_bef_fee@1") in named
    assert ("mixed.2p53", "av_pp_bef_fee@1") not in named
    assert not any(name == "lookup.key_range" for name, _where in named)
    assert [one.where for one in coarse] == ["maturity_month@1"]
    assert [tuple(mask.shape) for mask in dispatched.coarse_masks] == [(64,)]
    assert [len(operands) for operands in dispatched.coarse_operands] == [2]
    whole = sum(int(np.prod(one.shape)) for one in program.flags)
    assert whole // 64 == 1575
