# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tier 2: Execute the model-building skill's example claims.

The 2026-08-20 validation fleet found four reference examples that crashed
verbatim: par-rate tenors that violated the constraint stated two lines
below them, a Svensson fit one knot short of identifiable, a scalar
``multiply=`` that the accumulate kernel rejects, and a select-ultimate
snippet calling a class it never imported. These tests execute the fenced
code straight out of the markdown so the examples cannot silently rot
again. When one goes red the fix is to update the skill — a future kernel
that accepts scalar ``multiply`` makes the documented caveat fiction, and
this suite is the only thing that would tell us.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gaspatchio import ActuarialFrame, Curve

REPO_ROOT = Path(__file__).parent.parent.parent
REFERENCES = REPO_ROOT / "skills" / "gaspatchio-model-building" / "references"

CURVES_MD = REFERENCES / "curves-and-scheduling.md"
RECURSIVE_MD = REFERENCES / "recursive-patterns.md"
MISTAKES_MD = REFERENCES / "common-mistakes.md"
AGGREGATE_MD = REFERENCES / "aggregate-patterns.md"
MORTALITY_MD = REFERENCES / "mortality-tables.md"


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


class TestAccumulateMultiplyShape:
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

    def test_scalar_multiply_broadcasts(self) -> None:
        """The references' updated premise holds: a scalar multiply broadcasts.

        Until PR #155 the kernel rejected a scalar multiply and the
        references warned about it; the warnings now state the broadcast.
        If this fails, the constraint is back and the references are fiction
        again — update both together.
        """
        af = ActuarialFrame({"x": [[1.0, 2.0, 3.0]]})
        af.run = af.x.projection.accumulate(initial=0, multiply=1.0, add=af.x)
        assert af.collect()["run"].to_list() == [[1.0, 3.0, 6.0]]

    def test_identity_multiply_not_documented(self) -> None:
        """No skill teaches ``multiply=1`` — the closed form is the idiom.

        Since PR #155 a scalar multiply broadcasts, so this is a style guard,
        not a crash guard: a growth-free balance is
        ``initial + flow.cum_sum()``, and the references must keep steering
        there rather than at a degenerate recursion. The regex matches the
        identity factor in all three spellings across every skill markdown.
        """
        scalar_multiply = re.compile(r"multiply\s*=\s*(pl\.lit\(\s*)?1(\.0)?\s*[,)\s]")
        skills_root = REPO_ROOT / "skills"
        offending = [
            f"{md_path.relative_to(skills_root)}: {line.strip()}"
            for md_path in sorted(skills_root.rglob("*.md"))
            for line in md_path.read_text().splitlines()
            if scalar_multiply.search(line)
        ]
        assert not offending, f"Scalar multiply documented again: {offending}"


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
