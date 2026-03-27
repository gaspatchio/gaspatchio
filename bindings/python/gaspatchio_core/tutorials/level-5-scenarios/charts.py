# ruff: noqa: INP001
"""Shared Altair chart and report generation module for Level 5 tutorial steps.

Provides professional-quality chart functions and a report writer for
scenario analysis. All L5 ``run_scenarios.py`` scripts import from this
module.

Every chart function accepts a **Polars** DataFrame and returns an
``alt.Chart`` (or layered chart).  Altair 5+ supports Polars natively,
so no conversion is required.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import altair as alt
import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

PALETTE: dict[str, str] = {
    "BASE": "#4682B4",  # steel blue
    "favorable": "#2E8B57",  # sea green
    "mild_adverse": "#CD853F",  # peru
    "moderate_adverse": "#CD5C5C",  # indian red
    "severe_adverse": "#8B0000",  # dark red
}

SCENARIO_COLORS: list[str] = [
    "#4682B4",  # steel blue
    "#2E8B57",  # sea green
    "#CD853F",  # peru
    "#CD5C5C",  # indian red
    "#8B0000",  # dark red
    "#4B0082",  # indigo
    "#2F4F4F",  # dark slate grey
]

# ---------------------------------------------------------------------------
# Altair theme
# ---------------------------------------------------------------------------

_FONT = "Segoe UI, Helvetica Neue, Arial, sans-serif"


def _gaspatchio_theme() -> alt.theme.ThemeConfig:
    """Return a consistent Altair theme for all tutorial charts."""
    return {
        "config": {
            "background": "#FAFAFA",
            "title": {"font": _FONT, "fontSize": 16, "anchor": "start"},
            "axis": {
                "labelFont": _FONT,
                "labelFontSize": 11,
                "titleFont": _FONT,
                "titleFontSize": 12,
                "grid": True,
                "gridColor": "#E0E0E0",
            },
            "legend": {
                "labelFont": _FONT,
                "labelFontSize": 11,
                "titleFont": _FONT,
                "titleFontSize": 12,
            },
            "view": {"strokeWidth": 0},
        },
    }


alt.themes.register("gaspatchio", _gaspatchio_theme)
alt.themes.enable("gaspatchio")

# ---------------------------------------------------------------------------
# Number formatting helpers
# ---------------------------------------------------------------------------


def format_number(n: float | int) -> str:
    """Format a number for display.

    Large numbers (abs >= 1) get commas and no decimals.
    Small numbers (abs < 1) get 2 decimal places.
    """
    if abs(n) >= 1:
        return f"{n:,.0f}"
    return f"{n:,.2f}"


def format_pct(n: float | int) -> str:
    """Format *n* as a percentage string with 1 decimal place.

    >>> format_pct(-0.092)
    '-9.2%'
    >>> format_pct(0.15)
    '15.0%'
    """
    return f"{n * 100:.1f}%"


def df_to_markdown(
    df: pl.DataFrame,
    fmt: dict[str, Callable[[object], str]] | None = None,
) -> str:
    """Convert a Polars DataFrame to a Markdown table string.

    Parameters
    ----------
    df
        The DataFrame to render.
    fmt
        Optional mapping of *column name* to a callable that formats
        individual cell values.  Columns not in *fmt* are rendered with
        ``str()``.
    """
    fmt = fmt or {}
    headers = df.columns
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"

    rows: list[str] = []
    for row in df.iter_rows(named=True):
        cells: list[str] = []
        for col in headers:
            value = row[col]
            if col in fmt:
                cells.append(fmt[col](value))
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_line, separator, *rows])


# ---------------------------------------------------------------------------
# Chart functions
# ---------------------------------------------------------------------------


def scenario_bar_chart(
    df: pl.DataFrame,
    metric: str,
    group_col: str,
    scenario_col: str,
    title: str,
) -> alt.Chart:
    """Create a grouped bar chart of *metric* by scenario, grouped by *group_col*.

    Parameters
    ----------
    df
        DataFrame with at least *metric*, *group_col*, and *scenario_col*.
    metric
        Column name for the bar heights.
    group_col
        Column used for grouping (e.g. ``"product_id"``).
    scenario_col
        Column identifying scenarios.
    title
        Chart title.
    """
    scenarios = df[scenario_col].unique().sort().to_list()
    color_domain = scenarios
    color_range = SCENARIO_COLORS[: len(scenarios)]

    # Build a formatted label column
    df_plot = df.with_columns(
        pl.col(metric).map_elements(format_number, return_dtype=pl.String).alias("_label"),
    )

    bars = (
        alt.Chart(df_plot)
        .mark_bar()
        .encode(
            x=alt.X(f"{group_col}:N", title=group_col.replace("_", " ").title()),
            xOffset=alt.XOffset(f"{scenario_col}:N"),
            y=alt.Y(f"{metric}:Q", title=metric.replace("_", " ").title()),
            color=alt.Color(
                f"{scenario_col}:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                title=scenario_col.replace("_", " ").title(),
            ),
        )
    )

    text = (
        alt.Chart(df_plot)
        .mark_text(dy=-8, fontSize=9)
        .encode(
            x=alt.X(f"{group_col}:N"),
            xOffset=alt.XOffset(f"{scenario_col}:N"),
            y=alt.Y(f"{metric}:Q"),
            text=alt.Text("_label:N"),
            color=alt.value("#333333"),
        )
    )

    return (
        (bars + text)
        .properties(width=600, height=400, title=title)
    )


def tornado_chart(
    df: pl.DataFrame,
    base_scenario: str,
    metric: str,
    title: str,
    scenario_col: str = "scenario_id",
) -> alt.Chart:
    """Create a tornado (butterfly) chart showing deviation from *base_scenario*.

    Parameters
    ----------
    df
        DataFrame with *scenario_col* and the *metric* column.
    base_scenario
        The scenario id treated as the baseline.
    metric
        Numeric column to measure.
    title
        Chart title.
    scenario_col
        Name of the scenario identifier column.
    """
    base_row = df.filter(pl.col(scenario_col) == base_scenario)
    if base_row.is_empty():
        msg = f"Base scenario '{base_scenario}' not found in '{scenario_col}'"
        raise ValueError(msg)
    base_value = base_row[metric][0]

    others = df.filter(pl.col(scenario_col) != base_scenario)
    tornado_df = others.with_columns(
        (pl.col(metric) - base_value).alias("delta"),
    ).with_columns(
        (pl.col("delta") / base_value).alias("pct_change"),
        pl.col("delta").abs().alias("abs_delta"),
    ).with_columns(
        (
            pl.col("delta").map_elements(format_number, return_dtype=pl.String)
            + pl.lit(" (")
            + pl.col("pct_change").map_elements(format_pct, return_dtype=pl.String)
            + pl.lit(")")
        ).alias("_label"),
    ).sort("abs_delta", descending=True)

    bar_color = alt.condition(
        alt.datum.delta >= 0,
        alt.value("#2E8B57"),  # green for positive
        alt.value("#CD5C5C"),  # red for negative
    )

    bars = (
        alt.Chart(tornado_df)
        .mark_bar()
        .encode(
            x=alt.X("delta:Q", title=f"Delta ({metric.replace('_', ' ').title()})"),
            y=alt.Y(
                f"{scenario_col}:N",
                sort=alt.EncodingSortField(field="abs_delta", order="descending"),
                title="Scenario",
            ),
            color=bar_color,
        )
    )

    text = (
        alt.Chart(tornado_df)
        .mark_text(align="left", dx=4, fontSize=10)
        .encode(
            x=alt.X("delta:Q"),
            y=alt.Y(
                f"{scenario_col}:N",
                sort=alt.EncodingSortField(field="abs_delta", order="descending"),
            ),
            text=alt.Text("_label:N"),
        )
    )

    rule = alt.Chart(pl.DataFrame({"x": [0]})).mark_rule(color="black", strokeWidth=1).encode(
        x=alt.X("x:Q"),
    )

    n_scenarios = len(tornado_df)
    chart_height = max(200, n_scenarios * 40)

    return (
        (bars + text + rule)
        .properties(width=600, height=chart_height, title=title)
    )


def waterfall_chart(
    df: pl.DataFrame,
    components: list[str],
    base_scenario: str,
    target_scenario: str,
    title: str,
    scenario_col: str = "scenario_id",
) -> alt.Chart:
    """Create a waterfall chart showing component-level deltas between two scenarios.

    Parameters
    ----------
    df
        DataFrame with *scenario_col* and all *components* columns.
    components
        List of column names representing additive components.
    base_scenario
        Baseline scenario id.
    target_scenario
        Target scenario id.
    title
        Chart title.
    scenario_col
        Name of the scenario identifier column.
    """
    base_row = df.filter(pl.col(scenario_col) == base_scenario)
    target_row = df.filter(pl.col(scenario_col) == target_scenario)

    if base_row.is_empty():
        msg = f"Base scenario '{base_scenario}' not found"
        raise ValueError(msg)
    if target_row.is_empty():
        msg = f"Target scenario '{target_scenario}' not found"
        raise ValueError(msg)

    base_total = sum(base_row[c][0] for c in components)

    # Build waterfall data
    records: list[dict[str, object]] = []
    running = base_total

    # Starting bar
    records.append({
        "component": f"Base ({base_scenario})",
        "start": 0.0,
        "end": float(base_total),
        "delta": float(base_total),
        "order": 0,
        "color": "neutral",
    })

    for i, comp in enumerate(components, start=1):
        delta = float(target_row[comp][0]) - float(base_row[comp][0])
        start = running
        running += delta
        records.append({
            "component": comp.replace("_", " ").title(),
            "start": start,
            "end": running,
            "delta": delta,
            "order": i,
            "color": "favorable" if delta <= 0 else "adverse",
        })

    # Ending bar
    records.append({
        "component": f"Target ({target_scenario})",
        "start": 0.0,
        "end": running,
        "delta": running,
        "order": len(components) + 1,
        "color": "neutral",
    })

    wf_df = pl.DataFrame(records)

    color_scale = alt.Scale(
        domain=["favorable", "adverse", "neutral"],
        range=["#2E8B57", "#CD5C5C", "#4682B4"],
    )

    bars = (
        alt.Chart(wf_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "component:N",
                sort=alt.EncodingSortField(field="order", order="ascending"),
                title="Component",
            ),
            y=alt.Y("start:Q", title="Value"),
            y2=alt.Y2("end:Q"),
            color=alt.Color("color:N", scale=color_scale, legend=None),
        )
    )

    wf_df_labels = wf_df.with_columns(
        pl.col("delta").map_elements(format_number, return_dtype=pl.String).alias("_label"),
    )

    text = (
        alt.Chart(wf_df_labels)
        .mark_text(dy=-8, fontSize=10)
        .encode(
            x=alt.X(
                "component:N",
                sort=alt.EncodingSortField(field="order", order="ascending"),
            ),
            y=alt.Y("end:Q"),
            text=alt.Text("_label:N"),
        )
    )

    # Connector lines between bars
    connectors_data = []
    for i in range(len(records) - 1):
        connectors_data.append({
            "x": records[i]["component"],
            "x2": records[i + 1]["component"],
            "y": records[i]["end"],
            "order": records[i]["order"],
            "order2": records[i + 1]["order"],
        })

    if connectors_data:
        conn_df = pl.DataFrame(connectors_data)
        connectors = (
            alt.Chart(conn_df)
            .mark_rule(color="#999999", strokeDash=[2, 2])
            .encode(
                x=alt.X(
                    "x:N",
                    sort=alt.EncodingSortField(field="order", order="ascending"),
                ),
                x2=alt.X2("x2:N"),
                y=alt.Y("y:Q"),
            )
        )
        return (bars + text + connectors).properties(width=700, height=400, title=title)

    return (bars + text).properties(width=700, height=400, title=title)


def sensitivity_line(
    df: pl.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    base_x: float | None = None,
) -> alt.Chart:
    """Create a line + point chart for single-variable sensitivity analysis.

    Parameters
    ----------
    df
        DataFrame with *x_col* and *y_col*.
    x_col
        Column for the x-axis (the varied parameter).
    y_col
        Column for the y-axis (the result metric).
    title
        Chart title.
    base_x
        If provided, draw a dashed grey vertical reference line at this value.
    """
    line = (
        alt.Chart(df)
        .mark_line(point=True, color=SCENARIO_COLORS[0])
        .encode(
            x=alt.X(f"{x_col}:Q", title=x_col.replace("_", " ").title()),
            y=alt.Y(f"{y_col}:Q", title=y_col.replace("_", " ").title()),
        )
    )

    layers: list[alt.Chart] = [line]

    if base_x is not None:
        ref_df = pl.DataFrame({"_ref_x": [base_x]})
        ref_line = (
            alt.Chart(ref_df)
            .mark_rule(color="grey", strokeDash=[4, 4], strokeWidth=1.5)
            .encode(x=alt.X("_ref_x:Q"))
        )
        layers.append(ref_line)

    return alt.layer(*layers).properties(width=600, height=400, title=title)


def heatmap_2d(
    df: pl.DataFrame,
    x_col: str,
    y_col: str,
    value_col: str,
    title: str,
) -> alt.Chart:
    """Create a 2-D grid heatmap with text labels in each cell.

    Parameters
    ----------
    df
        DataFrame with *x_col*, *y_col*, and *value_col*.
    x_col
        Column for the x-axis categories.
    y_col
        Column for the y-axis categories.
    value_col
        Numeric column for the cell colour and label.
    title
        Chart title.
    """
    df_plot = df.with_columns(
        pl.col(value_col).map_elements(format_number, return_dtype=pl.String).alias("_label"),
    )

    rect = (
        alt.Chart(df_plot)
        .mark_rect()
        .encode(
            x=alt.X(f"{x_col}:O", title=x_col.replace("_", " ").title()),
            y=alt.Y(f"{y_col}:O", title=y_col.replace("_", " ").title()),
            color=alt.Color(
                f"{value_col}:Q",
                scale=alt.Scale(scheme="redblue"),
                title=value_col.replace("_", " ").title(),
            ),
        )
    )

    text = (
        alt.Chart(df_plot)
        .mark_text(fontSize=11)
        .encode(
            x=alt.X(f"{x_col}:O"),
            y=alt.Y(f"{y_col}:O"),
            text=alt.Text("_label:N"),
            color=alt.value("black"),
        )
    )

    return (rect + text).properties(width=500, height=400, title=title)


def cashflow_line(
    df: pl.DataFrame,
    time_col: str,
    value_col: str,
    scenario_col: str,
    title: str,
) -> alt.Chart:
    """Create a multi-line chart with one line per scenario.

    Parameters
    ----------
    df
        DataFrame with *time_col*, *value_col*, and *scenario_col*.
    time_col
        Column for the x-axis (time periods).
    value_col
        Column for the y-axis (values).
    scenario_col
        Column identifying scenarios (each gets its own line).
    title
        Chart title.
    """
    scenarios = df[scenario_col].unique().sort().to_list()
    color_domain = scenarios
    color_range = SCENARIO_COLORS[: len(scenarios)]

    return (
        alt.Chart(df)
        .mark_line()
        .encode(
            x=alt.X(f"{time_col}:Q", title=time_col.replace("_", " ").title()),
            y=alt.Y(f"{value_col}:Q", title=value_col.replace("_", " ").title()),
            color=alt.Color(
                f"{scenario_col}:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                title=scenario_col.replace("_", " ").title(),
            ),
        )
        .properties(width=700, height=400, title=title)
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def write_report(
    path: Path | str,
    title: str,
    metadata: dict[str, object],
    sections: list[dict[str, object]],
) -> Path:
    """Write a Markdown report to *path*/report/report.md.

    Parameters
    ----------
    path
        Base directory. A ``report/`` subdirectory is created if needed.
    title
        Report title (H1 heading).
    metadata
        Dict with keys such as ``points``, ``scenarios``, ``runtime_s``.
    sections
        List of dicts.  Each dict must have a ``"heading"`` key plus one of:

        - ``"content"`` -- rendered as text
        - ``"table"`` -- a ``pl.DataFrame`` rendered as Markdown
        - ``"chart"`` -- filename string, embedded as ``![heading](filename)``
        - ``"findings"`` -- list of strings, rendered as bullets

    Returns
    -------
    Path
        The path to the written report file.
    """
    report_dir = Path(path) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "report.md"

    lines: list[str] = []

    # Title
    lines.append(f"# {title}")
    lines.append("")

    # Metadata header
    points = metadata.get("points", "?")
    scenarios = metadata.get("scenarios", "?")
    runtime_s = metadata.get("runtime_s", "?")
    if isinstance(runtime_s, float):
        runtime_str = f"{runtime_s:.2f}s"
    else:
        runtime_str = f"{runtime_s}s"

    lines.append(
        f"**Model**: gaspatchio appliedlife VA | "
        f"**Points**: {points} | "
        f"**Scenarios**: {scenarios} | "
        f"**Runtime**: {runtime_str}"
    )
    lines.append("")

    # Sections
    for section in sections:
        heading = section["heading"]
        lines.append(f"## {heading}")
        lines.append("")

        if "content" in section:
            lines.append(str(section["content"]))
            lines.append("")

        if "table" in section:
            table_df = section["table"]
            if isinstance(table_df, pl.DataFrame):
                lines.append(df_to_markdown(table_df))
            else:
                lines.append(str(table_df))
            lines.append("")

        if "chart" in section:
            chart_filename = section["chart"]
            lines.append(f"![{heading}]({chart_filename})")
            lines.append("")

        if "findings" in section:
            findings = section["findings"]
            if isinstance(findings, list):
                for finding in findings:
                    lines.append(f"- {finding}")
            lines.append("")

    report_file.write_text("\n".join(lines))
    return report_file
