# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tier 2: Execute the model-building skill's example claims.

The 2026-08-20 validation fleet found four reference examples that crashed
verbatim: par-rate tenors that violated the constraint stated two lines
below them, a Svensson fit one knot short of identifiable, a scalar
``multiplier=`` that the accumulate kernel rejects, and a select-ultimate
snippet calling a class it never imported. These tests execute the fenced
code straight out of the markdown so the examples cannot silently rot
again. When one goes red the fix is to update the skill — a future kernel
that accepts scalar ``multiplier`` makes the documented caveat fiction, and
this suite is the only thing that would tell us.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import re
from pathlib import Path

import polars as pl
import pytest
from gaspatchio import ActuarialFrame, Curve, when
from gaspatchio.assumptions import Table

REPO_ROOT = Path(__file__).parent.parent.parent
REFERENCES = REPO_ROOT / "skills" / "gaspatchio-model-building" / "references"

CURVES_MD = REFERENCES / "curves-and-scheduling.md"
RECURSIVE_MD = REFERENCES / "recursive-patterns.md"
MISTAKES_MD = REFERENCES / "common-mistakes.md"
AGGREGATE_MD = REFERENCES / "aggregate-patterns.md"
MORTALITY_MD = REFERENCES / "mortality-tables.md"
CONDITIONALS_MD = REFERENCES / "conditionals-and-lists.md"
ASSUMPTIONS_MD = REFERENCES / "assumptions.md"
TIMING_MD = REFERENCES / "timing-and-dates.md"
SCALE_MD = REFERENCES / "running-at-scale.md"
BUILDING_SKILL_MD = REPO_ROOT / "skills" / "gaspatchio-model-building" / "SKILL.md"
EXTENDING = REPO_ROOT / "skills" / "gaspatchio-extending"
ACCESSOR_MD = EXTENDING / "references" / "accessor-template.md"
ANTI_PATTERNS_MD = EXTENDING / "references" / "anti-patterns.md"


# Same fence grammar as evals/oracles/base.py::_FENCE (case-insensitive tag,
# tolerant of trailing whitespace and CRLF) — keep the two in sync.
_FENCE = re.compile(r"```[ \t]*python[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _fence_containing(md_path: Path, marker: str) -> str:
    """Return the single ```python fence in *md_path* whose body has *marker*."""
    fences = _FENCE.findall(md_path.read_text())
    matches = [fence for fence in fences if marker in fence]
    assert len(matches) == 1, (
        f"Expected exactly one fence containing {marker!r} in {md_path.name}; "
        f"found {len(matches)} — the anchor this test executes has moved"
    )
    return matches[0]


def _execute(
    fence: str, source: Path, namespace: dict[str, object]
) -> dict[str, object]:
    """Execute a fence with *namespace* pre-seeded, returning the namespace."""
    exec(compile(fence, str(source), "exec"), namespace)  # noqa: S102 — executing the doc's own example is the test
    return namespace


class TestCurveExamples:
    """The two curve-construction examples run as printed."""

    def test_par_rates_example_executes(self) -> None:
        """The bootstrap example satisfies its own stated tenor constraint."""
        fence = _fence_containing(CURVES_MD, "from_par_rates(")
        namespace = _execute(fence, CURVES_MD, {"Curve": Curve})
        assert isinstance(namespace["par_curve"], Curve)

    def test_fit_svensson_example_executes(self) -> None:
        """The parametric fence (from_svensson, fit_svensson, smith-wilson) runs."""
        fence = _fence_containing(CURVES_MD, "fit_svensson(")
        namespace = _execute(fence, CURVES_MD, {"Curve": Curve})
        for name in ("nss", "nss_fit", "sw"):
            assert isinstance(namespace[name], Curve), f"{name} did not build"


class TestAccumulateMultiplierShape:
    """The running-balance idiom is list-shaped, and the docs say so truthfully."""

    def test_cash_balance_fence_executes(self) -> None:
        """recursive-patterns' cash-balance example runs and sums correctly."""
        af = ActuarialFrame(
            {
                "opening_cash": [100.0],
                "inflows": [[10.0, 20.0, 30.0]],
                "outflows": [[5.0, 5.0, 5.0]],
            },
        )
        fence = _fence_containing(RECURSIVE_MD, "cash_balance")
        namespace = _execute(fence, RECURSIVE_MD, {"af": af})
        result = namespace["af"].collect()["cash_balance"].to_list()  # type: ignore[attr-defined]
        assert result == [[105.0, 120.0, 145.0]]

    def test_cum_sum_table_row_executes(self) -> None:
        """common-mistakes #22's cum_sum idiom applies within the list."""
        row = re.search(
            r"`pl\.col\(\"x\"\)\.cum_sum\(\)`\s*\|\s*`(af\.x\.cum_sum\(\))`",
            MISTAKES_MD.read_text(),
        )
        assert row, "The cum_sum table row's idiom has moved or vanished"
        af = ActuarialFrame({"x": [[1.0, 2.0, 3.0]]})
        namespace = _execute(f"result = {row.group(1)}", MISTAKES_MD, {"af": af})
        af.run = namespace["result"]
        assert af.collect()["run"].to_list() == [[1.0, 3.0, 6.0]]

    def test_scalar_multiplier_broadcasts(self) -> None:
        """The references' updated premise holds: a scalar multiplier broadcasts.

        Until PR #155 the kernel rejected a scalar multiplier and the
        references warned about it; the warnings now state the broadcast.
        If this fails, the constraint is back and the references are fiction
        again — update both together.
        """
        af = ActuarialFrame({"x": [[1.0, 2.0, 3.0]]})
        af.run = af.x.projection.accumulate(initial=0, multiplier=1.0, addend=af.x)
        assert af.collect()["run"].to_list() == [[1.0, 3.0, 6.0]]

    def test_identity_multiplier_not_documented(self) -> None:
        """No skill teaches ``multiplier=1`` — the closed form is the idiom.

        Since PR #155 a scalar multiplier broadcasts, so this is a style guard,
        not a crash guard: a growth-free balance is
        ``initial + flow.cum_sum()``, and the references must keep steering
        there rather than at a degenerate recursion. The regex matches the
        identity factor in all three spellings across every skill markdown.
        """
        scalar_multiplier = re.compile(
            r"multiplier\s*=\s*(pl\.lit\(\s*)?1(\.0)?\s*[,)\s]"
        )
        skills_root = REPO_ROOT / "skills"
        offending = [
            f"{md_path.relative_to(skills_root)}: {line.strip()}"
            for md_path in sorted(skills_root.rglob("*.md"))
            for line in md_path.read_text().splitlines()
            if scalar_multiplier.search(line)
        ]
        assert not offending, f"Scalar multiplier documented again: {offending}"


class TestSelectUltimateExample:
    """mortality-tables' select-ultimate snippet runs as printed."""

    def test_select_ultimate_fence_executes(self) -> None:
        """The fence imports what it calls and the lookup produces rates."""
        af = ActuarialFrame(
            {
                "attained_age": [[30, 31, 32]],
                "duration": [[1, 2, 30]],  # 30 exercises the clamp to select_period
            },
        )
        fence = _fence_containing(MORTALITY_MD, "vbt_2021_alu")
        namespace = _execute(fence, MORTALITY_MD, {"af": af})
        rates = namespace["af"].collect()["qx"].to_list()  # type: ignore[attr-defined]
        expected = [
            0.001 * 30 * 1.05,  # duration 1 select rate
            0.001 * 31 * 1.10,  # duration 2 select rate
            0.001 * 32 * 1.25,  # duration 30 clamps to select_period 5
        ]
        assert rates[0] == pytest.approx(expected, abs=1e-6)


def _refused_then_right(fence: str) -> tuple[list[str], str]:
    """Split a ``# REFUSED`` / ``# RIGHT`` fence into its refused lines and its right block."""
    refused_part, _, right_part = fence.partition("\n# RIGHT")
    refused = [
        line
        for line in refused_part.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return refused, right_part.partition("\n")[2]


def _core_only(af: ActuarialFrame) -> None:
    """Every line the fence wrote is recorded as a core operation."""
    tiers = af.graph.tiers()
    assert tiers.engine_native == (), f"engine_native lines: {tiers.engine_native}"
    assert tiers.opaque == (), f"opaque lines: {tiers.opaque}"


class TestRecursivePatternRecipes:
    """recursive-patterns' reverse, multi-state and floored recipes run and are right."""

    def test_reverse_rollback_fence(self) -> None:
        """Pattern 5 rolls back from each policy's own last period, as stated."""
        af = ActuarialFrame(
            {"cf": [[1.0, 2.0, 3.0], [10.0]], "v": [[0.9, 0.9, 0.9], [0.5]]}
        )
        namespace = _execute(
            _fence_containing(RECURSIVE_MD, "reverse=True,\n"), RECURSIVE_MD, {"af": af}
        )
        out = namespace["af"].collect()  # type: ignore[attr-defined]
        assert out["reserve"].to_list()[0] == pytest.approx([5.23, 4.7, 3.0])
        assert out["reserve"].to_list()[1] == [10.0]
        assert out["cf_rev"].to_list() == [[3.0, 2.0, 1.0], [10.0]]
        _core_only(namespace["af"])  # type: ignore[arg-type]

    def test_forward_position_is_the_state_after_the_step(self) -> None:
        """The stated alignment: position t of a forward accumulate is after step t."""
        af = ActuarialFrame({"cf": [[1.0, 2.0, 3.0]], "v": [[0.9, 0.9, 0.9]]})
        af.after = af.cf.projection.accumulate(
            initial=10.0, multiplier=af.v, addend=af.cf
        )
        af.opened = af.after.projection.previous_period(fill_value=10.0)
        out = af.collect()
        assert out["after"].to_list()[0] == pytest.approx([10.0, 11.0, 12.9])
        assert out["opened"].to_list()[0] == pytest.approx([10.0, 10.0, 11.0])
        text = RECURSIVE_MD.read_text()
        assert "Position `t` of a forward `accumulate` is the state *after*" in text

    def test_multi_state_fence_is_an_euler_loop(self) -> None:
        """Pattern 6 (no recovery) is bit-equal to a plain Euler loop, and core."""
        fence = _fence_containing(RECURSIVE_MD, "healthy reads no other state")
        namespace = _execute(
            fence, RECURSIVE_MD, {"ActuarialFrame": ActuarialFrame, "pl": pl}
        )
        out = namespace["af"].collect()  # type: ignore[attr-defined]
        step_h, n_steps = 0.1, 200
        for row, x in enumerate((40.0, 55.0)):
            p0, p1 = [1.0], [0.0]
            for k in range(n_steps):
                age = x + k * step_h
                m01 = 0.0004 * math.exp(0.08 * age)
                m02 = 0.0002 * math.exp(0.09 * age)
                m12 = 0.0010 * math.exp(0.08 * age)
                p0.append(p0[-1] * (1 - step_h * (m01 + m02)))
                p1.append(p1[-1] * (1 - step_h * m12) + step_h * m01 * p0[-2])
            assert out["p0"].to_list()[row] == pytest.approx(p0, rel=1e-14, abs=0)
            assert out["p1"].to_list()[row] == pytest.approx(p1, rel=1e-14, abs=0)
        _core_only(namespace["af"])  # type: ignore[arg-type]

    def test_recovery_sweeps_converge_as_stated(self) -> None:
        """Sweep k is exact at least through step k; ten sweeps reach every step here."""
        step_h, n_steps = 0.1, 50
        m01, m02, m10, m12 = 0.05, 0.01, 0.30, 0.20
        p0, p1 = [1.0], [0.0]
        for _ in range(n_steps):
            healthy, sick = p0[-1], p1[-1]
            p0.append(healthy * (1 - step_h * (m01 + m02)) + step_h * m10 * sick)
            p1.append(sick * (1 - step_h * (m10 + m12)) + step_h * m01 * healthy)
        fence = _fence_containing(RECURSIVE_MD, "first guess: nobody sick")
        results = {}
        for sweeps in (5, 10, 11):
            namespace = _execute(
                fence,
                RECURSIVE_MD,
                {"ActuarialFrame": ActuarialFrame, "pl": pl, "SWEEPS": sweeps},
            )
            results[sweeps] = namespace["af"].collect()["p0"].to_list()[0]  # type: ignore[attr-defined]
        assert results[5][:6] == p0[:6]
        assert results[10] == pytest.approx(p0, rel=1e-14, abs=0)
        assert results[11] == results[10], (
            "the sweep after convergence must change nothing"
        )

    def test_floored_backward_scan_matches_a_loop(self) -> None:
        """Pattern 7's doubling scan floors where a loop does and agrees to its stated precision."""
        rng = random.Random(3)
        n_periods = 600
        a = [rng.uniform(-40.0, 38.0) for _ in range(n_periods)]
        b = [0.995 * (1 - rng.uniform(0.0, 0.02)) for _ in range(n_periods)]
        fence = _fence_containing(RECURSIVE_MD, "af.c_next")
        for floor in (0.0, 25.0):
            value, loop = 0.0, [0.0] * n_periods
            for t in range(n_periods - 1, -1, -1):
                value = max(floor, a[t] + b[t] * value)
                loop[t] = value
            af = ActuarialFrame(
                {"a": [a, a[:60]], "b": [b, b[:60]], "floor": [floor, floor]}
            )
            namespace = _execute(fence, RECURSIVE_MD, {"af": af, "when": when})
            got = namespace["af"].collect()["V"].to_list()  # type: ignore[attr-defined]
            assert got[0] == pytest.approx(loop, rel=1e-13, abs=1e-9)
            assert [g == floor for g in got[0]] == [w == floor for w in loop]
            short = [0.0] * 60
            value = 0.0
            for t in range(59, -1, -1):
                value = max(floor, a[t] + b[t] * value)
                short[t] = value
            assert got[1] == pytest.approx(short, rel=1e-13, abs=1e-9), (
                "a shorter policy rolls back from its own end"
            )
            _core_only(namespace["af"])  # type: ignore[arg-type]


class TestRefusalCatalogue:
    """common-mistakes #25-#29: each refused line is refused, each right block runs."""

    def _frame(self) -> ActuarialFrame:
        return ActuarialFrame(
            pl.DataFrame(
                {
                    "age": [40, 41],
                    "x": [float("nan"), 2.0],
                    "status": ["IF", "LA"],
                    "issue_date": [dt.date(2020, 3, 15), dt.date(2021, 6, 1)],
                    "smoker": [True, False],
                }
            )
        )

    def _check(self, marker: str, namespace: dict[str, object]) -> dict[str, object]:
        refused, right = _refused_then_right(_fence_containing(MISTAKES_MD, marker))
        assert refused, f"no refused lines under {marker!r}"
        for line in refused:
            with pytest.raises((TypeError, ValueError, AttributeError)):
                _execute(line, MISTAKES_MD, namespace)
        return _execute(right, MISTAKES_MD, namespace)

    def test_kind_refusals(self) -> None:
        """#25: two kinds on one line are refused; the right block runs and is core."""
        namespace = self._check(
            "af.x2 = af.x.fill_null(",
            {"af": self._frame(), "when": when, "date": dt.date},
        )
        out = namespace["af"].collect()  # type: ignore[attr-defined]
        assert out["code"].to_list() == ["INFORCE", "LA"]
        assert out["smoker_load"].to_list() == [100.0, 0.0]
        _core_only(namespace["af"])  # type: ignore[arg-type]

    def test_row_guards(self) -> None:
        """#26: reading down the policies is refused on a timeline frame; the right block runs."""
        af = ActuarialFrame(
            pl.DataFrame(
                {"policy_id": ["A", "B"], "age": [40, 50], "sum_assured": [1.0, 2.0]}
            )
        )
        af = af.projection.set(
            start_date=dt.date(2025, 1, 31), n_periods=2, frequency="annual"
        )
        namespace = self._check("af.sa_prev = af.sum_assured", {"af": af, "pl": pl})
        out = namespace["af"].collect()  # type: ignore[attr-defined]
        assert out["sa_prev"].to_list() == [[0.0, 1.0, 1.0], [0.0, 2.0, 2.0]]

    def test_table_read_inside_an_expression(self) -> None:
        """#27: a read inside the escape is refused; both moves run and the escape is named."""
        mort = Table(
            name="w4a_claims_mort",
            source=pl.DataFrame({"age": [40, 41], "qx": [0.001, 0.002]}),
            dimensions={"age": "age"},
            value="qx",
        )
        namespace = self._check(
            "af.q_read = mort.lookup", {"af": self._frame(), "mort": mort}
        )
        af = namespace["af"]
        assert af.graph.tiers().engine_native == ("q@1",)  # type: ignore[attr-defined]
        af.q40_read = mort.lookup(age=40)  # type: ignore[attr-defined]
        af.q40 = af.q40_read.fill_nan(0.0)  # type: ignore[attr-defined]
        assert af.collect()["q40"].to_list() == [0.001, 0.001]  # type: ignore[attr-defined]
        with pytest.raises(ValueError, match="Store the read as its own column first"):
            af.q2 = mort.lookup(age=40).fill_nan(0.0)  # type: ignore[attr-defined]

    def test_previous_period_fill_opens_a_product(self) -> None:
        """#29: the default fill zeroes the product; fill_value=1.0 opens it."""
        af = ActuarialFrame({"p": [[0.99, 0.98, 0.97]]})
        fence = _fence_containing(
            MISTAKES_MD, "previous_period(fill_value=1.0).cum_prod()"
        )
        wrong, _, right = fence.partition("# RIGHT")
        namespace = _execute(wrong, MISTAKES_MD, {"af": af})
        assert namespace["af"].collect()["surv"].to_list()[0] == [0.0, 0.0, 0.0]  # type: ignore[attr-defined]
        namespace = _execute(right.partition("\n")[2], MISTAKES_MD, {"af": af})
        opened = namespace["af"].collect()["surv"].to_list()[0]  # type: ignore[attr-defined]
        assert opened == pytest.approx([1.0, 0.99, 0.9702])


class TestBuildingFences:
    """The other fences this wave added or changed run as printed."""

    def test_stored_conditions_combine(self) -> None:
        """conditionals-and-lists: stored 0/1 conditions combine with & | ~, and are core."""
        af = ActuarialFrame(
            {"age": [30, 50, 70], "term": [10, 20, 5], "benefit": [100.0, 100.0, 100.0]}
        )
        namespace = _execute(
            _fence_containing(CONDITIONALS_MD, "af.both = af.old & af.long"),
            CONDITIONALS_MD,
            {"af": af, "when": when},
        )
        out = namespace["af"].collect()  # type: ignore[attr-defined]
        assert out["pay"].to_list() == [0.0, 0.0, 0.0]
        assert out["either"].to_list() == [1.0, 1.0, 1.0]
        assert out["young"].to_list() == [1.0, 1.0, 0.0]
        _core_only(namespace["af"])  # type: ignore[arg-type]
        bad = ActuarialFrame({"half": [0.5, 1.0], "x": [1.0, 2.0]})
        bad.y = when(bad.half).then(bad.x).otherwise(0.0)
        with pytest.raises(Exception, match="neither 0.0 nor 1.0"):
            bad.collect()

    def test_table_handed_the_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """assumptions.md: the basic pattern hands Table the file path and records it."""
        (tmp_path / "assumptions").mkdir()
        pl.DataFrame(
            {"age": [40, 41], "duration": [1, 1], "rate": [0.001, 0.002]}
        ).write_parquet(tmp_path / "assumptions" / "mortality.parquet")
        monkeypatch.chdir(tmp_path)
        af = ActuarialFrame({"attained_age": [40, 41], "duration": [1, 1]})
        namespace = _execute(
            _fence_containing(ASSUMPTIONS_MD, "the file path, not a frame"),
            ASSUMPTIONS_MD,
            {"af": af},
        )
        assert namespace["af"].collect()["mort_rate"].to_list() == [0.001, 0.002]  # type: ignore[attr-defined]

    def test_closed_form_discount_is_core(self) -> None:
        """timing-and-dates: (1 + r) ** (-month) is a core operation."""
        af = ActuarialFrame(
            pl.DataFrame({"policy_id": ["A"], "disc_rate_mth": [0.004]})
        )
        af = af.projection.set(
            start_date=dt.date(2025, 1, 31), n_periods=3, frequency="monthly"
        )
        namespace = _execute(
            _fence_containing(TIMING_MD, "** (-af.month)"), TIMING_MD, {"af": af}
        )
        got = namespace["af"].collect()["disc_factors"].to_list()[0]  # type: ignore[attr-defined]
        assert got == pytest.approx([1.004**-k for k in range(4)])
        _core_only(namespace["af"])  # type: ignore[arg-type]

    def test_space_parameters_arrive_as_columns(self) -> None:
        """SKILL.md: the cross join keeps each parameter a model-point column."""
        mp = pl.DataFrame({"policy_id": ["A", "B"]})
        space_params = pl.DataFrame(
            {
                "space": ["GMXB", "X"],
                "expense_acq": [50.0, 1.0],
                "expense_maint": [5.0, 1.0],
            }
        )
        namespace = _execute(
            _fence_containing(BUILDING_SKILL_MD, 'how="cross"'),
            BUILDING_SKILL_MD,
            {"mp": mp, "space_params": space_params, "pl": pl},
        )
        out = namespace["mp"]
        assert out["expense_acq"].to_list() == [50.0, 50.0]  # type: ignore[index]
        assert ".item()" not in _fence_containing(BUILDING_SKILL_MD, 'how="cross"')

    def test_period_aggregators_hold_one_value_per_boundary(self) -> None:
        """running-at-scale: a Period* aggregator holds n_periods + 1 values."""
        from gaspatchio import run_aggregated
        from gaspatchio.scenarios import PeriodSum, Sum

        def model_fn(af: ActuarialFrame) -> ActuarialFrame:
            af = af.projection.set(
                start_date=dt.date(2025, 1, 31), n_periods=4, frequency="annual"
            )
            af.net_cf = af.premium + af.month * 0.0
            af.pv_net_cf = af.net_cf.projection.prospective_value(discount_rate=0.03)
            af.pv0 = af.pv_net_cf.list.get(0)
            return af

        mp = pl.DataFrame({"policy_id": ["A", "B"], "premium": [1.0, 2.0]})
        res = run_aggregated(
            model_fn, mp, [PeriodSum("net_cf").alias("net_cf"), Sum("pv0").alias("pv0")]
        )
        assert len(res.net_cf) == 5
        assert "one value per projection boundary" in SCALE_MD.read_text()
        with pytest.raises(ValueError, match="PeriodSum"):
            run_aggregated(model_fn, mp, [Sum("pv_net_cf").alias("pv")])

    def test_the_skeleton_pays_n_claims_at_monthly_rates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SKILL.md's skeleton against a hand loop: 12 claims for 12 months.

        It once summed claims over all n + 1 points of the ``month`` axis, the
        maturity boundary included (+6.8% PV on a 12-month term), and applied
        the table's annual rate, and an annual discount rate, once a month.
        """
        (tmp_path / "assumptions").mkdir()
        q_annual = 0.012
        pl.DataFrame({"age": list(range(121)), "rate": [q_annual] * 121}).write_parquet(
            tmp_path / "assumptions" / "mortality.parquet"
        )
        monkeypatch.chdir(tmp_path)
        namespace = _execute(
            _fence_containing(BUILDING_SKILL_MD, "def load_assumptions"),
            BUILDING_SKILL_MD,
            {"__name__": "w5fa_skeleton"},
        )
        mp = pl.DataFrame(
            {
                "point_id": [1],
                "Issue Age": [40],
                "sum_assured": [100_000.0],
                "remaining_term_months": [12],
            }
        )

        out = namespace["main"](ActuarialFrame(mp)).collect()  # type: ignore[operator]

        q = 1 - (1 - q_annual) ** (1 / 12)
        v = 1 / 1.03 ** (1 / 12)
        hand = [100_000.0 * q * (1 - q) ** t for t in range(12)]
        assert out["claims"][0].to_list() == pytest.approx([*hand, 0.0], rel=1e-12)
        assert out["pv_claims"][0][0] == pytest.approx(
            sum(claim * v ** (t + 1) for t, claim in enumerate(hand)), rel=1e-12
        )

    def test_agents_md_names_a_column_spelling_that_works(self) -> None:
        """AGENTS.md: ``af["product"]`` reads the column; ``af.product`` is refused."""
        bullet = next(
            line
            for line in (REPO_ROOT / "AGENTS.md").read_text().splitlines()
            if "A bare string is a dimension VALUE" in line
        )
        assert "`af.product` /" not in bullet
        assert 'Reference a **column** with `af["product"]`' in bullet
        table = Table(
            name="w5fa_product",
            source=pl.DataFrame(
                {"product": ["annuity", "term"], "age": [40, 40], "rate": [0.01, 0.02]}
            ),
            dimensions={"product": "product", "age": "age"},
            value="rate",
        )
        af = ActuarialFrame(pl.DataFrame({"product": ["term"], "age": [40]}))
        af.r = table.lookup(product=af["product"], age=af.age)
        assert af.collect()["r"].to_list() == [0.02]
        with pytest.raises(AttributeError, match="product"):
            table.lookup(product=af.product, age=af.age)

    def test_model_phases_says_where_each_form_starts(self) -> None:
        """model-phases: a policy-anchored start is the date given; a fixed grid snaps."""
        text = (REFERENCES / "model-phases.md").read_text()
        assert "gives `projection_start_date` 2025-06-15" in text
        mp = pl.DataFrame({"policy_id": ["A"], "term_m": [2]})
        anchored = ActuarialFrame(mp).projection.set(
            valuation_date=dt.date(2025, 6, 15),
            until="term_months",
            until_value="term_m",
            frequency="monthly",
        )
        anchored.d = anchored.projection.period_dates()
        grid = ActuarialFrame(mp).projection.set(
            start_date=dt.date(2025, 1, 15), n_periods=2, frequency="monthly"
        )
        grid.d = grid.projection.period_dates()
        assert anchored.collect()["d"][0].to_list() == [
            dt.date(2025, 6, 15),
            dt.date(2025, 7, 15),
            dt.date(2025, 8, 15),
        ]
        assert grid.collect()["d"][0].to_list() == [
            dt.date(2025, 1, 31),
            dt.date(2025, 2, 28),
            dt.date(2025, 3, 31),
        ]

    def test_assumptions_md_says_strategies_act_at_build_not_lookup(self) -> None:
        """assumptions.md: an extended table still refuses a key it does not hold."""
        from gaspatchio.assumptions import ExtendOverflow, MeltDimension

        text = ASSUMPTIONS_MD.read_text()
        assert "control what happens when a lookup key falls outside" not in text
        assert "A lookup key the built table does not hold is still a miss" in text
        table = Table(
            name="w5fa_extended",
            source=pl.DataFrame({"band": ["A"], "1": [0.1], "Ult.": [0.2]}),
            dimensions={
                "band": "band",
                "duration": MeltDimension(
                    ["1", "Ult."], overflow=ExtendOverflow("Ult.", to_value=5)
                ),
            },
            value="value",
        )
        af = ActuarialFrame(pl.DataFrame({"band": ["A", "A"], "d": [5, 6]}))
        af.r = table.lookup(band=af.band, duration=af.d)
        with pytest.raises(Exception, match="missing keys"):
            af.collect()
        af = ActuarialFrame(pl.DataFrame({"band": ["A"], "d": [5]}))
        af.r = table.lookup(band=af.band, duration=af.d)
        assert af.collect()["r"].to_list() == [0.2]


class TestExtendingClaims:
    """The extending skill's accessor, reserve and shock spellings run and mean what they say."""

    def test_declared_accessor_body_is_core(self) -> None:
        """accessor-template: a body composed of the proxy's operations is core, on a read too."""
        _execute(
            _fence_containing(ACCESSOR_MD, '@register_accessor("gompertz"'),
            ACCESSOR_MD,
            {"__name__": "w4a_gompertz"},
        )
        mort = Table(
            name="w4a_claims_gompertz",
            source=pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]}),
            dimensions={"age": "age"},
            value="qx",
        )
        af = ActuarialFrame({"age": [30, 40], "ages": [[30.0, 31.0], [40.0, 41.0]]})
        af.h = af.age.gompertz.hazard(a=0.0001, b=0.08)  # type: ignore[attr-defined]
        af.h_list = af.ages.gompertz.hazard(a=0.0001, b=0.08)  # type: ignore[attr-defined]
        af.h_read = mort.lookup(age=af.age).gompertz.hazard(a=1.0, b=1.0)  # type: ignore[attr-defined]
        out = af.collect()
        assert out["h"].to_list() == pytest.approx(
            [0.0001 * math.exp(0.08 * a) for a in (30, 40)]
        )
        assert out["h_list"].to_list()[1] == pytest.approx(
            [0.0001 * math.exp(0.08 * a) for a in (40.0, 41.0)]
        )
        _core_only(af)

    def test_backward_reserve_runs_backward(self) -> None:
        """anti-patterns #1: the reserve recursion is accumulate(reverse=True) and matches the loop."""
        qx, v, benefit, maturity = [0.01, 0.02, 0.03, 0.04], 1 / 1.03, 1000.0, 500.0
        reserves = [0.0] * 5
        reserves[-1] = maturity
        for t in range(3, -1, -1):
            reserves[t] = v * (qx[t] * benefit + (1 - qx[t]) * reserves[t + 1])
        af = ActuarialFrame(
            {"qx": [qx], "v": [v], "benefit": [benefit], "maturity_benefit": [maturity]}
        )
        fence = _fence_containing(ANTI_PATTERNS_MD, "reverse=True,")
        namespace = _execute(fence, ANTI_PATTERNS_MD, {"af": af})
        got = namespace["af"].collect()["reserve"].to_list()[0]  # type: ignore[attr-defined]
        assert got == pytest.approx(reserves[:4], rel=1e-14)

    def test_shock_spellings_construct_what_they_say(self) -> None:
        """No skill spells ClipShock with a positional bound or PipelineShock with positional shocks."""
        from gaspatchio.scenarios import ClipShock, MultiplicativeShock, PipelineShock

        positional = re.compile(r"ClipShock\(\s*-?[0-9]|PipelineShock\(\s*\[?\s*[A-Z]")
        offending = [
            f"{md.relative_to(REPO_ROOT)}: {line.strip()}"
            for md in sorted((REPO_ROOT / "skills").rglob("*.md"))
            for line in md.read_text().splitlines()
            if positional.search(line)
        ]
        assert not offending, f"positional shock spellings: {offending}"
        row = re.search(
            r"`(PipelineShock\(shocks=\(.*?\), column=\"lapse_rate\"\))`",
            (EXTENDING / "SKILL.md").read_text(),
        )
        assert row, "the lapse-up stress spelling has moved"
        shock = eval(
            row.group(1),
            {
                "PipelineShock": PipelineShock,
                "MultiplicativeShock": MultiplicativeShock,
                "ClipShock": ClipShock,
            },
        )
        assert shock.column == "lapse_rate"
        assert shock.table is None
        assert shock.shocks[1].max_value == 1.0
        assert shock.shocks[1].min_value is None
