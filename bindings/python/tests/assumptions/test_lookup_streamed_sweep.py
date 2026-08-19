# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-114: Table.lookup streamed-frame correctness sweep.

Commit 2eb556d fixed a Rust panic (``array_storage.rs:247``) for streamed
multi-policy list-column lookups; ``test_lookup_streamed_list.py`` pins that
specific shape. This sweep covers the remaining lookup paths — the bug class
("safe-indexing replacement broke an implicit offset invariant") is plausible
anywhere list offsets meet chunk boundaries.

**Inventory of lookup paths swept here** (each run at explicit input chunk
widths {1, 7, single-chunk} x engines {streaming, in-memory}, asserted
against closed-form expected values):

1.  all-scalar single key        -> scalar value per policy
2.  all-scalar two keys          -> scalar value per policy
3.  single list key              -> list value (the 2eb556d shape, larger)
4.  mixed scalar + list keys     -> list value (surrender-charge shape)
5.  two list keys                -> list value (age x duration shape)
6.  string scalar + list key     -> list value (mortality table_id/sex shape)
7.  MeltDimension wide table + list key -> list value (select/'Ult.' shape)
8.  jagged list keys (per-policy lengths) -> jagged list value
9.  on_missing=0.0 fill with list keys (miss-fill path under chunking)

Plus one at-scale case (25k policies x 12 periods) on paths 3 and 4 under
the default streaming collect, where the engine does its own morselling.

Chunked inputs are built by concatenating single-frame slices with
``rechunk=False`` so the plugin sees list offsets that do not start at 0 —
the exact invariant 2eb556d repaired. Results must equal the single-chunk
baseline exactly (lookups gather stored values; no arithmetic is involved).
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import MeltDimension, Table

N_POLICIES = 400
N_PERIODS = 12
CHUNK_WIDTHS = [1, 7]
ENGINES = ["streaming", "in-memory"]


def _rate(age: int, duration: int = 0) -> float:
    """Closed-form rate so every (policy, t) cell has one right answer."""
    return 0.001 + age * 0.0008 + duration * 0.013


def _chunked(df: pl.DataFrame, width: int) -> pl.DataFrame:
    slices = [df.slice(o, width) for o in range(0, df.height, width)]
    out = pl.concat(slices, rechunk=False)
    assert out.n_chunks() > 1
    return out


def _collect(df: pl.DataFrame, build, engine: str) -> pl.DataFrame:
    """Apply the lookup-building callback to a fresh frame and collect."""
    af = ActuarialFrame(df)
    build(af)
    return af.collect(engine=engine)


def _sweep(df: pl.DataFrame, build, check) -> None:
    """Run build+check on the baseline and on every chunking/engine combo."""
    baseline = _collect(df.rechunk(), build, "in-memory")
    check(baseline)
    for engine in ENGINES:
        for width in CHUNK_WIDTHS:
            result = _collect(_chunked(df, width), build, engine)
            check(result)
            for col in baseline.columns:
                assert result[col].to_list() == baseline[col].to_list(), (
                    f"column {col} diverged from baseline "
                    f"(engine={engine}, chunk width={width})"
                )


@pytest.fixture(scope="module")
def age_table() -> Table:
    ages = list(range(0, 200))
    return Table(
        name="sweep_age",
        source=pl.DataFrame(
            {"age": ages, "rate": [_rate(a) for a in ages]},
        ),
        dimensions={"age": "age"},
        value="rate",
    )


@pytest.fixture(scope="module")
def age_duration_table() -> Table:
    rows = [
        {"age": a, "duration": d, "rate": _rate(a, d)}
        for a in range(0, 200)
        for d in range(0, N_PERIODS + 1)
    ]
    return Table(
        name="sweep_age_duration",
        source=pl.DataFrame(rows),
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
    )


@pytest.fixture(scope="module")
def sex_age_table() -> Table:
    rows = [
        {"sex": s, "age": a, "rate": _rate(a) * (1.1 if s == "M" else 0.9)}
        for s in ("M", "F")
        for a in range(0, 200)
    ]
    return Table(
        name="sweep_sex_age",
        source=pl.DataFrame(rows),
        dimensions={"sex": "sex", "age": "age"},
        value="rate",
    )


def _base_frame() -> pl.DataFrame:
    issue_age = [20 + (i % 45) for i in range(N_POLICIES)]
    return pl.DataFrame(
        {
            "policy_id": list(range(N_POLICIES)),
            "issue_age": issue_age,
            "sex": ["M" if i % 2 == 0 else "F" for i in range(N_POLICIES)],
            "duration_scalar": [i % N_PERIODS for i in range(N_POLICIES)],
            "attained_age": [
                [a + t for t in range(N_PERIODS)] for a in issue_age
            ],
            "duration": [list(range(N_PERIODS)) for _ in range(N_POLICIES)],
        },
    )


class TestScalarKeyPaths:
    def test_all_scalar_single_key(self, age_table: Table) -> None:
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = age_table.lookup(age=af.issue_age)

        def check(result: pl.DataFrame) -> None:
            got = result["rate"].to_list()
            want = [_rate(a) for a in df["issue_age"].to_list()]
            assert got == pytest.approx(want, rel=1e-12)

        _sweep(df, build, check)

    def test_all_scalar_two_keys(self, age_duration_table: Table) -> None:
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = age_duration_table.lookup(
                age=af.issue_age, duration=af.duration_scalar
            )

        def check(result: pl.DataFrame) -> None:
            got = result["rate"].to_list()
            want = [
                _rate(a, d)
                for a, d in zip(
                    df["issue_age"].to_list(), df["duration_scalar"].to_list()
                )
            ]
            assert got == pytest.approx(want, rel=1e-12)

        _sweep(df, build, check)


class TestListKeyPaths:
    def test_single_list_key(self, age_table: Table) -> None:
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = age_table.lookup(age=af.attained_age)

        def check(result: pl.DataFrame) -> None:
            for ages, rates in zip(
                df["attained_age"].to_list(), result["rate"].to_list()
            ):
                assert rates == pytest.approx(
                    [_rate(a) for a in ages], rel=1e-12
                )

        _sweep(df, build, check)

    def test_mixed_scalar_and_list_keys(self, age_duration_table: Table) -> None:
        # Scalar duration + list age: the surrender-charge shape.
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = age_duration_table.lookup(
                age=af.attained_age, duration=af.duration_scalar
            )

        def check(result: pl.DataFrame) -> None:
            for ages, d, rates in zip(
                df["attained_age"].to_list(),
                df["duration_scalar"].to_list(),
                result["rate"].to_list(),
            ):
                assert rates == pytest.approx(
                    [_rate(a, d) for a in ages], rel=1e-12
                )

        _sweep(df, build, check)

    def test_two_list_keys(self, age_duration_table: Table) -> None:
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = age_duration_table.lookup(
                age=af.attained_age, duration=af.duration
            )

        def check(result: pl.DataFrame) -> None:
            for ages, durs, rates in zip(
                df["attained_age"].to_list(),
                df["duration"].to_list(),
                result["rate"].to_list(),
            ):
                assert rates == pytest.approx(
                    [_rate(a, d) for a, d in zip(ages, durs)], rel=1e-12
                )

        _sweep(df, build, check)

    def test_string_scalar_plus_list_key(self, sex_age_table: Table) -> None:
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = sex_age_table.lookup(sex=af.sex, age=af.attained_age)

        def check(result: pl.DataFrame) -> None:
            for sex, ages, rates in zip(
                df["sex"].to_list(),
                df["attained_age"].to_list(),
                result["rate"].to_list(),
            ):
                factor = 1.1 if sex == "M" else 0.9
                assert rates == pytest.approx(
                    [_rate(a) * factor for a in ages], rel=1e-12
                )

        _sweep(df, build, check)


class TestStructuredTablePaths:
    def test_melt_dimension_wide_table_with_list_key(self) -> None:
        # Wide select table: one column per select duration, melted to long.
        ages = list(range(0, 200))
        wide = pl.DataFrame(
            {
                "age": ages,
                **{
                    str(d): [_rate(a, d) for a in ages]
                    for d in range(N_PERIODS)
                },
            },
        )
        table = Table(
            name="sweep_select_wide",
            source=wide,
            dimensions={
                "age": "age",
                "duration": MeltDimension(
                    columns=[str(d) for d in range(N_PERIODS)],
                    name="duration",
                ),
            },
            value="rate",
        )
        df = _base_frame()

        def build(af: ActuarialFrame) -> None:
            af.rate = table.lookup(age=af.attained_age, duration=af.duration)

        def check(result: pl.DataFrame) -> None:
            for ages_, durs, rates in zip(
                df["attained_age"].to_list(),
                df["duration"].to_list(),
                result["rate"].to_list(),
            ):
                assert rates == pytest.approx(
                    [_rate(a, d) for a, d in zip(ages_, durs)], rel=1e-12
                )

        _sweep(df, build, check)

    def test_jagged_list_keys(self, age_table: Table) -> None:
        # Per-policy horizons 1..N_PERIODS: offsets vary row to row, so a
        # chunk boundary can land inside any run of unequal lengths.
        df = _base_frame().with_columns(
            pl.col("attained_age").list.head(
                pl.col("policy_id") % N_PERIODS + 1
            ),
        )

        def build(af: ActuarialFrame) -> None:
            af.rate = age_table.lookup(age=af.attained_age)

        def check(result: pl.DataFrame) -> None:
            for ages, rates in zip(
                df["attained_age"].to_list(), result["rate"].to_list()
            ):
                assert len(rates) == len(ages)
                assert rates == pytest.approx(
                    [_rate(a) for a in ages], rel=1e-12
                )

        _sweep(df, build, check)

    def test_on_missing_fill_with_list_keys(self, age_table: Table) -> None:
        # Ages past the table's last row exercise the miss-fill path; the
        # fill positions must survive chunking exactly like hits do.
        df = _base_frame().with_columns(
            (pl.col("attained_age").list.eval(pl.element() + 150)).alias(
                "attained_age_high"
            ),
        )

        def build(af: ActuarialFrame) -> None:
            af.rate = age_table.lookup(
                age=af.attained_age_high, on_missing=0.0
            )

        def check(result: pl.DataFrame) -> None:
            for ages, rates in zip(
                df["attained_age_high"].to_list(), result["rate"].to_list()
            ):
                want = [_rate(a) if a < 200 else 0.0 for a in ages]
                assert rates == pytest.approx(want, rel=1e-12)

        _sweep(df, build, check)


class TestAtScaleStreaming:
    """Sizes past the engine's own morsel width — the engine picks the chunks."""

    @pytest.mark.parametrize("n_policies", [25_000])
    def test_single_list_key_at_scale(
        self, age_table: Table, n_policies: int
    ) -> None:
        issue_age = [20 + (i % 45) for i in range(n_policies)]
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "issue_age": issue_age,
                    "attained_age": [
                        [a + t for t in range(N_PERIODS)] for a in issue_age
                    ],
                },
            ),
        )
        af.rate = age_table.lookup(age=af.attained_age)
        af.rate_x2 = af.rate * 2.0  # downstream consumer forces sub-graph split
        result = af.collect()

        rates = result["rate"].to_list()
        spot_rows = [0, 1, n_policies // 2, n_policies - 2, n_policies - 1]
        for i in spot_rows:
            assert rates[i] == pytest.approx(
                [_rate(issue_age[i] + t) for t in range(N_PERIODS)], rel=1e-12
            ), f"row {i} wrong at scale"
        # Full-book check without 300k approx calls: exact totals per row.
        for i, (a, row) in enumerate(zip(issue_age, rates)):
            want = sum(_rate(a + t) for t in range(N_PERIODS))
            assert sum(row) == pytest.approx(want, rel=1e-9), f"row {i}"

    @pytest.mark.parametrize("n_policies", [25_000])
    def test_mixed_keys_at_scale(
        self, age_duration_table: Table, n_policies: int
    ) -> None:
        issue_age = [20 + (i % 45) for i in range(n_policies)]
        dur = [i % N_PERIODS for i in range(n_policies)]
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "issue_age": issue_age,
                    "duration_scalar": dur,
                    "attained_age": [
                        [a + t for t in range(N_PERIODS)] for a in issue_age
                    ],
                },
            ),
        )
        af.rate = age_duration_table.lookup(
            age=af.attained_age, duration=af.duration_scalar
        )
        af.rate_x2 = af.rate * 2.0
        result = af.collect()

        rates = result["rate"].to_list()
        for i, (a, d, row) in enumerate(zip(issue_age, dur, rates)):
            want = sum(_rate(a + t, d) for t in range(N_PERIODS))
            assert sum(row) == pytest.approx(want, rel=1e-9), f"row {i}"
