# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""Render the stochastic showcase chart from scenario_showcase.json.

Pure data -> chart; no model run here. Emits both a Vega-Lite JSON (for embedding
in docs / perf pages) and a PNG. Run after run_scenario_showcase.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root (consistency)

import json

import altair as alt
import polars as pl

HERE = Path(__file__).resolve().parent
DATA = HERE / "scenario_showcase.json"


def build_charts(data: dict) -> alt.VConcatChart:
    """Two-panel showcase: loss distribution + CTE markers, and the percentile fan."""
    dist = data["distribution"]
    cte70, cte95 = dist["cte70"], dist["cte95"]
    dist_df = pl.DataFrame({"loss": dist["per_scenario_loss"]})
    hist = (
        alt.Chart(dist_df)
        .mark_bar(opacity=0.8)
        .encode(
            x=alt.X("loss:Q", bin=alt.Bin(maxbins=40),
                    title="PV net liability (loss) per scenario"),
            y=alt.Y("count()", title="scenarios"),
        )
        .properties(width=600, height=260,
                    title="Stochastic reserve distribution")
    )
    rules = (
        alt.Chart(pl.DataFrame({"x": [cte70, cte95], "label": ["CTE70", "CTE95"]}))
        .mark_rule(color="#CD853F", strokeWidth=2)
        .encode(x="x:Q", tooltip="label:N")
    )
    panel_a = hist + rules

    fan_df = pl.DataFrame(data["fan"])
    base = alt.Chart(fan_df)
    band_outer = base.mark_area(opacity=0.25).encode(
        x="month:Q", y=alt.Y("p05:Q", title="portfolio net cashflow"), y2="p95:Q")
    band_inner = base.mark_area(opacity=0.4).encode(x="month:Q", y="p25:Q", y2="p75:Q")
    median = base.mark_line(strokeWidth=2).encode(x="month:Q", y="p50:Q")
    panel_b = (band_outer + band_inner + median).properties(
        width=600, height=260, title="Percentile fan -- net cashflow over time")

    return alt.vconcat(panel_a, panel_b).resolve_scale(x="independent")


def main() -> None:
    """Read the showcase JSON, render Vega-Lite JSON + PNG next to it."""
    data = json.loads(DATA.read_text())
    chart = build_charts(data)
    (HERE / "scenario_showcase.vl.json").write_text(chart.to_json())
    try:
        chart.save(str(HERE / "scenario_showcase.png"), scale_factor=2)
        png_msg = "scenario_showcase.png"
    except Exception as exc:  # noqa: BLE001 - PNG backend optional; JSON is primary
        png_msg = f"(PNG skipped: no backend -- {exc})"
    print(f"Wrote {HERE / 'scenario_showcase.vl.json'} and {png_msg}")


if __name__ == "__main__":
    main()
