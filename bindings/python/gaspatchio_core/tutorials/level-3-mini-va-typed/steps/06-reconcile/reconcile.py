# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Typed Input Parity Check: level-3-mini-va-typed vs level-3-mini-va.

Verifies that swapping from raw Table lookups and scalar constants to
typed inputs (MortalityTable, Curve, Schedule) does not alter present-value
outputs. Two checks are performed:

  1. typed/base vs untyped/base  — flat-curve Curve + aggregate MortalityTable
  2. typed/02-select-mort vs untyped/02-select-mort — select/ultimate MortalityTable

Both checks compare pv_net_cf, pv_claims, pv_premiums, pv_expenses,
pv_commissions, pv_inv_income, and pv_av_change for all 4 model points.
Relative tolerance: 1e-9 (comfortably above f64 machine epsilon of ~2.2e-16).

Usage:
    uv run python tutorial/level-3-mini-va-typed/steps/06-reconcile/reconcile.py

Exit code 0 if all checks pass, 1 if any fail.
"""

import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

import polars as pl
from gaspatchio_core import ActuarialFrame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

THIS_DIR = Path(__file__).resolve().parent
TUTORIAL_DIR = THIS_DIR.parent.parent.parent  # .../tutorials/

TYPED_BASE_DIR = TUTORIAL_DIR / "level-3-mini-va-typed" / "base"
UNTYPED_BASE_DIR = TUTORIAL_DIR / "level-3-mini-va" / "base"

TYPED_STEP02_DIR = TUTORIAL_DIR / "level-3-mini-va-typed" / "steps" / "02-select-mort"
UNTYPED_STEP02_DIR = TUTORIAL_DIR / "level-3-mini-va" / "steps" / "02-select-mort"

# ---------------------------------------------------------------------------
# PV columns to compare
# ---------------------------------------------------------------------------

PV_COLUMNS = [
    "pv_net_cf",
    "pv_claims",
    "pv_premiums",
    "pv_expenses",
    "pv_commissions",
    "pv_inv_income",
    "pv_av_change",
]

# Relative tolerance: 1e-9 allows for sub-nanosecond floating-point path
# differences while catching any semantically meaningful divergence.
REL_TOLERANCE = 1e-9


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------


def _load_model(model_dir: Path) -> object:
    """Import model.py from model_dir as a fresh module."""
    model_path = model_dir / "model.py"
    spec = importlib.util.spec_from_file_location(
        f"model_{model_dir.name}", model_path
    )
    if spec is None or spec.loader is None:
        msg = f"Cannot load spec from {model_path}"
        raise ImportError(msg)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run_model(model_dir: Path) -> pl.DataFrame:
    """Import model from model_dir, run main(af) and return collected PVs."""
    mod = _load_model(model_dir)

    # Both base models use inline MODEL_POINTS dict; step-02 models load from
    # parquet. The model's __main__ block shows which constructor to use.
    # We replicate: af = ActuarialFrame(MODEL_POINTS) for inline models,
    # or read_parquet for file-based ones.
    mp_path = model_dir / "data" / "model_points.parquet"
    if mp_path.exists():
        mp = pl.read_parquet(mp_path)
        af = ActuarialFrame(mp)
    else:
        # Inline model — MODEL_POINTS is a dict on the module
        af = ActuarialFrame(mod.MODEL_POINTS)  # type: ignore[attr-defined]

    result_af = mod.main(af)  # type: ignore[attr-defined]
    result = result_af.collect()

    # Return only the PV columns that exist, plus point_id for alignment
    available = ["point_id"] + [c for c in PV_COLUMNS if c in result.columns]
    return result.select(available)


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------


class DiffRow(NamedTuple):
    point_id: int
    column: str
    typed_val: float
    untyped_val: float
    rel_diff: float


def compute_diffs(typed_df: pl.DataFrame, untyped_df: pl.DataFrame) -> list[DiffRow]:
    """Return list of DiffRow for any column exceeding REL_TOLERANCE."""
    diffs: list[DiffRow] = []
    # Align on point_id in case row order differs
    typed_sorted = typed_df.sort("point_id")
    untyped_sorted = untyped_df.sort("point_id")

    for col in PV_COLUMNS:
        if col not in typed_df.columns or col not in untyped_df.columns:
            continue
        for t_row, u_row in zip(
            typed_sorted.iter_rows(named=True), untyped_sorted.iter_rows(named=True)
        ):
            t_val: float = t_row[col]
            u_val: float = u_row[col]
            denom = max(abs(u_val), 1e-10)
            rel_diff = abs(t_val - u_val) / denom
            if rel_diff > REL_TOLERANCE:
                diffs.append(
                    DiffRow(
                        point_id=t_row["point_id"],
                        column=col,
                        typed_val=t_val,
                        untyped_val=u_val,
                        rel_diff=rel_diff,
                    )
                )
    return diffs


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _run_check(label: str, typed_dir: Path, untyped_dir: Path) -> bool:
    """Run a single parity check. Returns True if all values match."""
    print(f"\nRunning: {label}")
    print(f"  typed:   {typed_dir.relative_to(TUTORIAL_DIR.parent)}")
    print(f"  untyped: {untyped_dir.relative_to(TUTORIAL_DIR.parent)}")

    typed_df = run_model(typed_dir)
    untyped_df = run_model(untyped_dir)

    diffs = compute_diffs(typed_df, untyped_df)

    if diffs:
        print(f"  FAIL — {len(diffs)} value(s) exceed rel tolerance {REL_TOLERANCE:.0e}:")
        print(
            f"    {'point_id':<10} {'column':<22} {'typed':>18} {'untyped':>18} {'rel_diff':>12}"
        )
        print("    " + "-" * 84)
        for d in diffs:
            print(
                f"    {d.point_id:<10} {d.column:<22} {d.typed_val:>18.6f} "
                f"{d.untyped_val:>18.6f} {d.rel_diff:>12.2e}"
            )
        return False

    print("  PASS")
    return True


def reconcile_base() -> bool:
    """Check: typed/base parity vs untyped/base."""
    return _run_check(
        label="typed/base  vs  untyped/base",
        typed_dir=TYPED_BASE_DIR,
        untyped_dir=UNTYPED_BASE_DIR,
    )


def reconcile_step_02() -> bool:
    """Check: typed/02-select-mort parity vs untyped/02-select-mort."""
    return _run_check(
        label="typed/02-select-mort  vs  untyped/02-select-mort",
        typed_dir=TYPED_STEP02_DIR,
        untyped_dir=UNTYPED_STEP02_DIR,
    )


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

_HEADER_WIDTH = 68


def print_summary(results: dict[str, bool]) -> None:
    """Print a formatted summary table."""
    print()
    print("=" * _HEADER_WIDTH)
    print(f"{'Check':<44} {'Tolerance':<12} {'Result'}")
    print("-" * _HEADER_WIDTH)
    for label, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{label:<44} {'1e-9 rel':<12} {status}")
    print("-" * _HEADER_WIDTH)

    if all(results.values()):
        print("RESULT: ALL CHECKS PASS")
    else:
        failed = [lbl for lbl, ok in results.items() if not ok]
        print(f"RESULT: {len(failed)} CHECK(S) FAILED")
        print()
        print("A failure means the typed-input layer introduced a numerical")
        print("difference. Check: MortalityTable.at() clamp semantics,")
        print("Curve.discount_factor() precision, or Schedule year_fraction")
        print("accumulation against the original Table.lookup() / scalar path.")
    print("=" * _HEADER_WIDTH)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all parity checks. Return 0 on full pass, 1 on any failure."""
    print("=" * _HEADER_WIDTH)
    print("L3-TYPED STEP 06: Parity check — typed inputs vs untyped inputs")
    print("=" * _HEADER_WIDTH)

    results: dict[str, bool] = {
        "typed/base  vs  untyped/base": reconcile_base(),
        "typed/02-select-mort  vs  untyped/02": reconcile_step_02(),
    }

    print_summary(results)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
