# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A walk-through reads the same wherever the package is installed.

Polars renders a compiled plugin call with the path of the library holding
it -- rooted for a checkout, and relative to the interpreter's prefix where
the library sits inside it, which is every wheel installed into a virtual
environment. The cleaning a walk-through's first line and the
``gaspatchio_lowered`` facet go through read the rooted shape alone, so one
tree reached a reader as ``duration_conditional(1, sum_assured, 0)`` from a
checkout and as ``duration.lib_conditional(1, sum_assured, 0)`` from a wheel
(and from both, now, as the ``.when(...)`` the model wrote),
and a division as ``(1) / (itm)`` or ``(1.lib) / (itm)``. These tests render
one model from two installs and hold the text to one answer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest
from polars.plugins import register_plugin_function

import gaspatchio
from gaspatchio.frame.graph.graph_utils import clean_expression_string
from gaspatchio.frame.graph.trace_generator import _minimal_clean
from gaspatchio.frame.lowering._polars.plugins import list_pow
from gaspatchio.frame.lowering._polars.rendering import without_plugin_library_paths
from gaspatchio.frame.lowering.ingress import native_node

# The package this suite imports, and the extension inside it.
_PACKAGE = Path(gaspatchio.__file__).resolve().parent
_EXTENSION = next(_PACKAGE.glob("_internal*.so"), None) or next(
    _PACKAGE.glob("_internal*.pyd"), None
)

# The model exported from each install: a conditional over a per-period
# column, which lowers to the ``list_conditional`` plugin, and a division,
# which lowers to the ``ieee_div`` kernel.
_EXPORT = """
import datetime
import json
import sys

prefix = sys.argv[1]
if prefix:
    sys.prefix = prefix
    sys.path.insert(0, sys.argv[2])

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph.calc_graph import GraphExporter

af = ActuarialFrame(
    pl.DataFrame({"policy_id": [1], "sum_assured": [100_000.0], "itm": [12.0]})
)
af = af.projection.set(
    valuation_date=datetime.date(2025, 1, 1),
    until="term_months",
    until_value=6,
    frequency="monthly",
)
af.duration = af.month + 1
af.flag = when(af.duration > 1).then(af.sum_assured).otherwise(0.0)
af.rate = 1 / af.itm
document = json.loads(GraphExporter(af).export(af.collect(), include_lowered=True))
import gaspatchio
print(json.dumps({
    "package": gaspatchio.__file__,
    "nodes": {
        node["id"]: [
            node["trace"][0]["expr"],
            node["facets"]["gaspatchio_lowered"]["text"],
        ]
        for node in document["nodes"]
        if node["column"] in ("flag", "rate")
    },
}))
"""


def _rendered(*args: pl.Expr, library: Path, symbol: str) -> str:
    """Return how Polars renders one plugin call against the library at ``library``."""
    return str(
        register_plugin_function(
            plugin_path=library,
            function_name=symbol,
            args=list(args),
            is_elementwise=True,
        )
    )


def _a_library_at(path: Path) -> Path:
    """Put a file named as the extension is at ``path``; rendering never loads it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_a_plugin_call_cleans_to_one_text_from_any_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rooted, rooted with spaces, and relative to a virtual environment: one text."""
    name = "_internal.cpython-313-darwin.so"
    checkout = _a_library_at(tmp_path / "src" / "gaspatchio" / name)
    spaced = _a_library_at(tmp_path / "My Models (v2)" / "gaspatchio" / name)
    venv = tmp_path / "venv"
    wheel = _a_library_at(venv / "lib/python3.13/site-packages/gaspatchio" / name)

    condition = (pl.col("duration"), pl.lit(1), pl.col("sum_assured"), pl.lit(0.0))
    renderings = [
        _rendered(*condition, library=checkout, symbol="list_conditional"),
        _rendered(*condition, library=spaced, symbol="list_conditional"),
    ]
    monkeypatch.setattr(sys, "prefix", str(venv))
    relative = _rendered(*condition, library=wheel, symbol="list_conditional")
    # The shape that went wrong, held so this test cannot pass by never
    # meeting it: Polars wrote the wheel's library relative to the prefix.
    assert ".lib/python3.13/site-packages/" in relative
    renderings.append(relative)
    renderings.append(
        'col("duration").C:\\Users\\me\\.venv\\Lib\\site-packages\\gaspatchio'
        "\\_internal.cp313-win_amd64.pyd:list_conditional"
        '([dyn int: 1, col("sum_assured"), dyn float: 0])'
    )

    cleaned = {clean_expression_string(text) for text in renderings}

    one = 'col("duration").list_conditional([dyn int: 1, col("sum_assured"), '
    assert cleaned == {f"{one}dyn float: 0])"}
    # No comparisons were read here, so the conditional keeps the kernel's
    # name -- whole, and a name the package defines.
    assert {_minimal_clean(text) for text in cleaned} == {
        "duration.list_conditional(1, sum_assured, 0)"
    }


def test_a_division_reads_as_the_operator_from_any_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quotient kernel reads as ``/`` whichever path it was rendered with."""
    name = "_internal.cpython-313-darwin.so"
    checkout = _a_library_at(tmp_path / "src" / "gaspatchio" / name)
    venv = tmp_path / "venv"
    wheel = _a_library_at(venv / "lib/python3.13/site-packages/gaspatchio" / name)
    quotient = (pl.lit(1), pl.col("itm"))

    rooted = _rendered(*quotient, library=checkout, symbol="ieee_div")
    monkeypatch.setattr(sys, "prefix", str(venv))
    relative = _rendered(*quotient, library=wheel, symbol="ieee_div")

    assert clean_expression_string(rooted) == clean_expression_string(relative)
    assert clean_expression_string(relative) == '[(dyn int: 1) / (col("itm"))]'


@pytest.mark.skipif(_EXTENSION is None, reason="needs the built extension")
def test_one_model_exports_one_walk_through_from_two_installs(tmp_path: Path) -> None:
    """The same model, run from the checkout and from a virtual environment's wheel.

    The second install is this very package, linked into a directory laid out
    as a virtual environment's ``site-packages`` and run with that directory
    as the interpreter's prefix -- which is exactly what makes Polars write
    the library relative to the prefix, and how it loads it back.
    """
    venv = tmp_path / "a venv (copy)"
    site = venv / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}"
    site = site / "site-packages"
    site.mkdir(parents=True)
    (site / "gaspatchio").symlink_to(_PACKAGE, target_is_directory=True)
    script = tmp_path / "export.py"
    script.write_text(_EXPORT)
    environment = {**os.environ, "PYTHONPATH": str(_PACKAGE.parent)}

    def run(*argv: str) -> dict[str, object]:
        done = subprocess.run(  # noqa: S603 -- this interpreter, this test's own script
            [sys.executable, str(script), *argv],
            capture_output=True,
            text=True,
            check=True,
            env=environment,
            cwd=tmp_path,
        )
        reading: dict[str, object] = json.loads(done.stdout.strip().splitlines()[-1])
        return reading

    from_the_checkout = run("", "")
    from_the_wheel = run(str(venv), str(site))

    assert str(from_the_wheel["package"]).startswith(str(site))
    assert from_the_checkout["nodes"] == from_the_wheel["nodes"]
    for opening, lowered in from_the_wheel["nodes"].values():  # type: ignore[attr-defined]
        assert ".lib" not in opening
        assert "site-packages" not in lowered


@pytest.mark.parametrize("rate", ["1.01", "1.07", "1.5e-05"])
def test_a_decimal_receiver_keeps_every_digit_from_any_install(rate: str) -> None:
    """The scrub starts at the dot before the library, not inside the number.

    A relative run allowed to start after ``1.`` took ``01.`` along with the
    path, so two rates differing only past the point wrote one text -- in the
    walk-through and in the text an engine-native fingerprint is taken over.
    """
    wheel = "lib/python3.13/site-packages/gaspatchio/_internal.abi3.so"
    rooted = "/opt/env/gaspatchio/_internal.cpython-313-darwin.so"
    for library in (wheel, rooted):
        rendered = f'dyn float: {rate}.{library}:list_pow([col("t")])'

        assert without_plugin_library_paths(rendered) == (
            f'dyn float: {rate}.<plugin>:list_pow([col("t")])'
        )
        assert clean_expression_string(rendered) == (
            f'dyn float: {rate}.pow([col("t")])'
        )


def test_two_rates_before_a_kernel_are_two_engine_native_texts() -> None:
    """The fingerprint text tells ``1.01`` from ``1.07`` again.

    The same scrub writes an engine-native fragment's text, which a node's
    fingerprint is taken over: with the digits eaten, two fragments that
    raise different rates to a power stamped as one calculation.
    """
    texts = {
        native_node(list_pow(pl.lit(rate), pl.col("t"))).text for rate in (1.01, 1.07)
    }

    assert texts == {
        'dyn float: 1.01.<plugin>:list_pow([col("t")])',
        'dyn float: 1.07.<plugin>:list_pow([col("t")])',
    }
