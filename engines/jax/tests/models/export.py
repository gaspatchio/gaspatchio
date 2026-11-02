# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Export the two shipped models this engine is measured on.

Run from ``bindings/python`` with the **core** venv, which is where the
producer lives::

    .venv/bin/python ../../engines/jax/tests/models/export.py

What it writes, beside this file: each model's executable artifact and the
thousand-policy book it reads. Both are committed, because what the engine
reads is the artifact and a landing that changed the artifact should show in
a diff rather than in a number. The committed artifacts withhold the library
versions (``--no-versions``): those name one machine's build, and a diff
should show the model moving, not the machine that exported it.

**The reference is not written here.** The suite takes it fresh, with
``gspio run-model --every-node``, from the live tutorial model -- every
value-bearing node's column keyed by node id, with the result manifest in the
file's own metadata. Two reasons. The frozen exports under ``viewer/fixtures``
are deliberately not regenerated and are not a reference for anything; and a
thousand policies over eighty-three periods is forty megabytes of doubles,
which is a great deal of repository for a file one command reproduces in three
seconds. If the tutorial moves under the committed artifact, the fresh
reference's graph fingerprint stops matching it and the comparison refuses the
pair by name, which is the guard committing it would have bought.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TUTORIALS = Path("gaspatchio/tutorials")

# The two models, and where each one's own model points stand.
MODELS: dict[str, str] = {
    "level-4": "level-4-lifelib",
    "level-5": "level-5-scenarios",
}

# A thousand policies, as both measurements of this engine used.
BOOK = "model_points_1k.parquet"

# The rollforward tutorial, which ``gspio tutorial init rollforward-patterns``
# writes out and which the tree carries under ``patterns/``. Two of its three
# files are inside section 16.1's executable subset and are this engine's
# acceptance for the scan: the single-state fund is grow, charge and floor on
# one balance, and the multi-state ratchet is a growth on one balance and a
# gated lift of a second to the first's within-period close, which is the
# cross-state read the whole operation exists for. The third, the lapse stop,
# is deliberately outside the subset -- ``lapse_when_all_non_positive`` is a
# stopping condition 16.1 excludes by name -- and is not exported.
PATTERNS: dict[str, tuple[str, str]] = {
    "fund": ("01_single_state_fund.py", "01_model_points.parquet"),
    "ratchet": ("02_multistate_ratchet.py", "02_model_points.parquet"),
}
PATTERNS_FOLDER = "patterns/rollforward-patterns"

# The jagged book: a term book whose policies do not share one timeline, which
# is what a real one looks like and what neither shipped model is. Written
# where the caller asks rather than committed: it is one command's output, and
# a committed copy would agree with a tutorial that had moved out from under
# it.
JAGGED_POLICIES = 10_000

# **Seven terms, in years, and four widths.** The terms are one to seven and
# not the five to forty a term book usually carries, for the model's own
# reason rather than a choice: the level-4 tutorial's investment-return and
# mortality bases are published over its own eighty-two-month horizon, and a
# policy projected past them reaches a key the basis does not carry and
# refuses by name -- which is the engine reading a lookup miss correctly.
#
# Seven terms are not seven widths. Each policy's horizon is its term less the
# months it has already run at the valuation date, so the seven terms spread
# into boundary counts from 1 to 46 cells; the bucket grid rounds those up to
# **12, 24, 36 and 48**, which is four widths, four horizon groups and four
# compiled programs. `tests/test_models.py` pins all four on a miniature of
# this book.
JAGGED_TERMS_YEARS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
JAGGED_WIDTHS: tuple[int, ...] = (12, 24, 36, 48)


def jagged(destination: Path, policies: int = JAGGED_POLICIES) -> tuple[Path, Path]:
    """Write the jagged term book and its artifact, and return where they went.

    The level-4 model over a book that is not one timeline. The tutorial's
    own thousand policies, tiled with fresh identities, with each policy given
    one of the seven terms in :data:`JAGGED_TERMS_YEARS` -- so the projection
    axis is that policy's own, and the book stands in the four widths
    :data:`JAGGED_WIDTHS` names.

    Returns:
        The artifact and the book, in that order.

    """
    import polars as pl

    destination.mkdir(parents=True, exist_ok=True)
    base = TUTORIALS / MODELS["level-4"] / "base"
    written = pl.read_parquet(base / BOOK)
    tiles = -(-policies // written.height)
    tiled = pl.concat([written] * tiles, how="vertical").head(policies)
    terms = [
        JAGGED_TERMS_YEARS[row % len(JAGGED_TERMS_YEARS)] for row in range(policies)
    ]
    book = tiled.with_columns(
        pl.int_range(1, policies + 1, dtype=pl.Int64).alias("point_id"),
        pl.Series("policy_term", terms, dtype=pl.Int64),
    )
    at = destination / "book.parquet"
    book.write_parquet(at)
    artifact = destination / "jagged.artifact.json"
    subprocess.run(  # noqa: S603 -- this project's own venv and tutorials
        [
            str(Path(sys.executable).with_name("gspio")),
            "calc-graph",
            str(base / "model.py"),
            str(at),
            "--profile",
            "executable",
            "--policies",
            ":1",
            "-o",
            str(artifact),
        ],
        check=True,
    )
    return artifact, at


def _exported(gspio: Path, model: Path, book: Path, artifact: Path) -> None:
    """Write one model's executable artifact where the caller asks."""
    artifact.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 -- this project's own venv and tutorials
        [
            str(gspio),
            "calc-graph",
            str(model),
            str(book),
            "--profile",
            "executable",
            "--policies",
            ":1",
            "--no-versions",
            "-o",
            str(artifact),
        ],
        check=True,
    )


def patterns() -> int:
    """Write the rollforward tutorial's two in-subset patterns beside this file."""
    gspio = Path(sys.executable).with_name("gspio")
    where = HERE / "patterns"
    for name, (source, points) in PATTERNS.items():
        model = TUTORIALS / PATTERNS_FOLDER / source
        book = TUTORIALS / PATTERNS_FOLDER / points
        if not model.exists():
            print(f"run this from bindings/python: {model} is not there")  # noqa: T201 -- a script
            return 2
        _exported(gspio, model, book, where / f"{name}.artifact.json")
        (where / f"{name}.book.parquet").write_bytes(book.read_bytes())
        print(f"{name}: artifact and book written")  # noqa: T201 -- a script
    return 0


def main() -> int:
    """Write each model's executable artifact and its book, beside this file."""
    gspio = Path(sys.executable).with_name("gspio")
    for name, folder in MODELS.items():
        model = TUTORIALS / folder / "base/model.py"
        book = TUTORIALS / folder / "base" / BOOK
        if not model.exists():
            print(f"run this from bindings/python: {model} is not there")  # noqa: T201 -- a script
            return 2
        subprocess.run(  # noqa: S603 -- this project's own venv and tutorials
            [
                str(gspio),
                "calc-graph",
                str(model),
                str(book),
                "--profile",
                "executable",
                "--policies",
                ":1",
                "--no-versions",
                "-o",
                str(HERE / f"{name}.artifact.json"),
            ],
            check=True,
        )
        (HERE / f"{name}.book.parquet").write_bytes(book.read_bytes())
        print(f"{name}: artifact and book written")  # noqa: T201 -- a script
    return patterns()


if __name__ == "__main__":
    raise SystemExit(main())
