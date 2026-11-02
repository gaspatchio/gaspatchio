# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tier 2: Execute the factual claims of the workbook-conversion skill.

The skill is a document of claims: the fastexcel/calamine reader mangles
float precision behind a String-dtype inference, the API surface the prose
names exists, the sibling skills and files it routes to are where it says.
With its discovery reference it also claims how the timing conventions
differ, what Excel's ``^`` is against ``**``, what the audit file records
for a scalar read with ``.item()``, and which windows a read states.
These tests execute those claims so the skill cannot silently drift from
reality. When one goes red the fix is to update the skill — that is the
point, not a nuisance: a future fastexcel release that repairs the
truncation makes the HARD GATE section fiction, and this suite is the only
thing that would tell us.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import fastexcel
import polars as pl
import pytest
import typer
import xlsxwriter
from gaspatchio import ActuarialFrame, compile_rollforward

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILL_MD = SKILLS_DIR / "gaspatchio-workbook-conversion" / "SKILL.md"

# Probe values from the skill's own HARD GATE table. The table's third probe
# (2238.2200000000003) needs 17 significant digits and dies in xlsxwriter's
# %.16g serialisation before the reader ever sees it — using it here would
# attribute the loss to the wrong tool. These two round-trip the write
# exactly, so any loss measured below belongs to the reader alone.
PROBES = [0.970873786407767, 497761.77773510211]


@pytest.fixture(scope="module")
def probe_workbook(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a workbook with a text title row above a float data block."""
    path = tmp_path_factory.mktemp("claims") / "probe.xlsx"
    workbook = xlsxwriter.Workbook(str(path))
    sheet = workbook.add_worksheet("Sheet1")
    sheet.write_row(0, 0, ["Projection of Account Values"])
    sheet.write_row(1, 0, ["t", "v", "av"])
    sheet.write_row(2, 0, [1, *PROBES])
    sheet.write_row(3, 0, [2, *[p * 1.01 for p in PROBES]])
    workbook.close()
    return path


def test_probe_values_survive_the_write() -> None:
    """Fixture self-check: every probe round-trips xlsxwriter's %.16g.

    Guards future probe edits from reintroducing the 17-digit trap, which
    would make the truncation tests blame the reader for the writer's loss.
    """
    for probe in PROBES:
        assert float(f"{probe:.16g}") == probe


def test_string_inferred_read_truncates_floats(probe_workbook: Path) -> None:
    """The skill's HARD GATE premise holds.

    A text header row above the data block makes the columns infer String,
    and the stringified values lose precision.
    """
    frame = fastexcel.read_excel(str(probe_workbook)).load_sheet(0).to_polars()

    value_dtypes = frame.dtypes[1:]
    assert all(str(dtype) == "String" for dtype in value_dtypes), (
        "The text-header read no longer infers String — the skill's HARD "
        f"GATE premise has changed (got {value_dtypes})"
    )
    # Row 0 is the column-header row swallowed as data; row 1 is the first
    # data row. Parsing the strings back must NOT recover the true doubles.
    read_back = [float(value) for value in frame.row(1)[1:]]
    for got, want in zip(read_back, PROBES, strict=True):
        assert got != want, (
            f"String-path read preserved {want!r} exactly — fastexcel may "
            "have fixed the truncation; re-verify and update the skill's "
            "HARD GATE section"
        )


def test_header_skipped_read_is_lossless(probe_workbook: Path) -> None:
    """The skill's remedy holds.

    Skip the text row and the block reads Float64 bit-exact — this is what
    makes the reader provable against the XML.
    """
    frame = (
        fastexcel.read_excel(str(probe_workbook))
        .load_sheet(0, header_row=1)
        .to_polars()
    )

    value_dtypes = frame.dtypes[1:]
    assert all(str(dtype) == "Float64" for dtype in value_dtypes), (
        f"Header-skipped read no longer infers Float64 (got {value_dtypes})"
    )
    read_back = list(frame.row(0)[1:])
    for got, want in zip(read_back, PROBES, strict=True):
        assert got == want, f"Float64 path lost precision: {got!r} != {want!r}"


def test_named_sibling_skills_exist() -> None:
    """Every gaspatchio-* skill the prose routes to is a real skill dir."""
    content = SKILL_MD.read_text()
    named = {
        match.rstrip("-") for match in re.findall(r"gaspatchio-[a-z][a-z-]*", content)
    }
    assert named, "The skill no longer names any sibling skills"
    for skill_name in sorted(named):
        assert (SKILLS_DIR / skill_name / "SKILL.md").exists(), (
            f"SKILL.md routes to '{skill_name}' but skills/{skill_name}/ does not exist"
        )


def test_discovery_reference_file_exists() -> None:
    """The discovery reference the skill routes to exists.

    The skill sends readers to discovery's spreadsheet-conversion reference
    first; that file must exist where the prose points.
    """
    assert "references/spreadsheet-conversion.md" in SKILL_MD.read_text()
    reference = (
        SKILLS_DIR
        / "gaspatchio-model-discovery"
        / "references"
        / "spreadsheet-conversion.md"
    )
    assert reference.exists(), f"Referenced file missing: {reference}"


def test_named_api_surface_exists() -> None:
    """Every API surface the prose names exists on the shipped package.

    The prose names round_charge=, .clip(), .round(), .norm_cdf() and
    .excel.norm_s_dist(); pin each so the skill cannot outlive a rename.
    """
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.rollforward._builder import _StateHandle

    for op_name in ("charge", "grow", "deduct_nar"):
        signature = inspect.signature(getattr(_StateHandle, op_name))
        assert "round_charge" in signature.parameters, (
            f"Skill prose promises round_charge= on ops, but "
            f"_StateHandle.{op_name} does not accept it"
        )
    assert hasattr(ColumnProxy, "clip"), (
        "Skill prose promises .clip() on the lookup key"
    )
    assert callable(getattr(_StateHandle, "round", None)), (
        "Skill prose promises .round() on the rollforward state"
    )
    from gaspatchio.accessors.excel import ExcelColumnAccessor

    assert hasattr(ColumnProxy, "norm_cdf"), (
        "Skill prose promises .norm_cdf() for NORM.S.DIST and NORM.DIST"
    )
    assert (
        "cumulative" in inspect.signature(ExcelColumnAccessor.norm_s_dist).parameters
    ), "Skill prose promises .excel.norm_s_dist() as the same node"


# --- The skill and its discovery reference, as one document of claims ---

DISCOVERY_DIR = SKILLS_DIR / "gaspatchio-model-discovery"
SPREADSHEET_MD = DISCOVERY_DIR / "references" / "spreadsheet-conversion.md"
OWNED_TEXT = (SKILL_MD, DISCOVERY_DIR / "SKILL.md", SPREADSHEET_MD)

# Sentences once shipped that say the timing conventions agree at constant rates.
# They are false: at flat rates the conventions already differ (the tests below
# measure it); what flat rates hide is a wrong conversion between them.
_CONSTANT_RATES_CLAIMS = re.compile(
    r"identical answers|agree when rates are constant|agree until rates vary"
    r"|constant rates[^.]*\b(agree|identical)",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    "path", OWNED_TEXT, ids=lambda p: str(p.relative_to(SKILLS_DIR))
)
def test_no_text_says_conventions_agree_at_constant_rates(path: Path) -> None:
    """No skill text claims the timing conventions agree when rates are flat."""
    text = " ".join(path.read_text().split())
    found = _CONSTANT_RATES_CLAIMS.search(text)
    assert found is None, (
        f"{path.name} says {found.group(0)!r}: the conventions differ even at flat "
        "rates; say that a wrong conversion between them passes a flat-rate test"
    )


@pytest.mark.parametrize(
    "path", OWNED_TEXT, ids=lambda p: str(p.relative_to(SKILLS_DIR))
)
def test_no_private_issue_numbers(path: Path) -> None:
    """Shipped skill text names no private tracker id (it says 'not in 1.0')."""
    assert "GSP-" not in path.read_text(), f"{path.name} cites a private issue id"


def test_timing_conventions_differ_at_flat_rates() -> None:
    """The replacement sentence's first clause: the conventions differ when rates are flat."""
    af = ActuarialFrame({"q": [[0.01, 0.01, 0.01]], "cf": [[100.0, 100.0, 100.0]]})
    af.surv_bop = af.q.projection.cumulative_survival(rate_timing="beginning_of_period")
    af.surv_eop = af.q.projection.cumulative_survival(rate_timing="end_of_period")
    af.pv_bop = af.cf.projection.prospective_value(
        discount_rate=0.05, timing="beginning_of_period"
    )
    af.pv_eop = af.cf.projection.prospective_value(
        discount_rate=0.05, timing="end_of_period"
    )
    row = af.collect().row(0, named=True)
    assert row["surv_bop"] != row["surv_eop"]
    assert row["surv_eop"][:2] == pytest.approx(row["surv_bop"][1:], rel=1e-15), (
        "a survival curve should differ by exactly one period's decrement"
    )
    assert row["pv_bop"] != row["pv_eop"]


@pytest.mark.parametrize(
    ("rates", "should_pass"),
    [([0.05, 0.05, 0.05], True), ([0.03, 0.05, 0.07], False)],
    ids=["flat", "varying"],
)
def test_wrong_conversion_passes_only_at_flat_rates(
    rates: list[float], *, should_pass: bool
) -> None:
    """The replacement sentence's second clause: one multiplication by v hides on flat rates."""
    af = ActuarialFrame({"cf": [[100.0, 100.0, 100.0]], "i": [rates]})
    af.v = 1 / (1 + af.i)
    af.bop = af.cf.projection.prospective_value(
        discount_rate=af.i, timing="beginning_of_period"
    )
    af.eop = af.cf.projection.prospective_value(
        discount_rate=af.i, timing="end_of_period"
    )
    af.eop_by_one_v = af.bop * af.v
    row = af.collect().row(0, named=True)
    agrees = row["eop"] == pytest.approx(row["eop_by_one_v"], rel=1e-12)
    assert agrees is should_pass


def test_deduct_nar_conventions_differ_at_flat_rates() -> None:
    """The deduct_nar row: its two named conventions part in the first period at a flat 4%."""

    def balance(timing: str) -> list[float]:
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "av0": [1000.0],
                    "coi": [[0.01] * 3],
                    "db": [[5000.0] * 3],
                    "rate": [[0.04] * 3],
                }
            )
        )
        af = af.projection.set(
            start_date=dt.date(2025, 1, 31), n_periods=3, frequency="annual"
        )
        builder = af.projection.rollforward(states={"av": af["av0"]})
        extra = (
            {}
            if timing == "beginning_of_period"
            else {"coi_discount_rate": af["rate"], "credited_rate": af["rate"]}
        )
        builder["av"].grow(af["rate"]).deduct_nar(
            af["coi"], death_benefit=af["db"], nar_timing=timing, **extra
        )
        af.av = compile_rollforward(builder).expr_for("av")
        return af.collect()["av"].to_list()[0]

    bop, eop = balance("beginning_of_period"), balance("end_of_period")
    assert bop[0] != pytest.approx(eop[0], rel=1e-9)


def _square_and_multiply(x: float, n: int) -> float:
    result, base = 1.0, x
    while n:
        if n & 1:
            result *= base
        base *= base
        n >>= 1
    return result


def _ulps(a: float, b: float) -> int:
    def as_int(x: float) -> int:
        return struct.unpack("<q", struct.pack("<d", x))[0]

    return abs(as_int(a) - as_int(b))


def test_power_is_pow_not_square_and_multiply() -> None:
    """The `^` quirk: `**` is the C library's pow, and parts from squaring as n grows."""
    bases = [1 + i / 10000 for i in range(1, 1001, 7)]
    exponents = list(range(1, 121))
    af = ActuarialFrame(
        pl.DataFrame({"base": bases, "n": [[float(k) for k in exponents]] * len(bases)})
    )
    af.p = af.base**af.n
    got = af.collect()["p"].to_list()
    assert all(
        value == math.pow(b, k)
        for b, row in zip(bases, got, strict=True)
        for k, value in zip(exponents, row, strict=True)
    ), "`**` is no longer the C library's pow; re-measure the skill's `^` quirk"
    worst = {
        limit: max(
            _ulps(value, _square_and_multiply(b, k))
            for b, row in zip(bases, got, strict=True)
            for k, value in zip(exponents, row, strict=True)
            if k <= limit
        )
        for limit in (10, 120)
    }
    assert 0 < worst[10] <= 5, worst
    assert worst[10] < worst[120] <= 100, worst


# --- The record: what the skill says the audit file holds, exported for real ---

_MODELS = {
    "model_item.py": """
from pathlib import Path
import polars as pl
from gaspatchio import ActuarialFrame
HERE = Path(__file__).parent

def main(af: ActuarialFrame) -> ActuarialFrame:
    params = pl.read_parquet(HERE / "assumptions" / "expenses.parquet")
    acquisition = params.filter(pl.col("product") == "TERM")["acquisition"].item()
    af.expense = af.pols * acquisition
    return af
""",
    "model_table.py": """
from pathlib import Path
from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
HERE = Path(__file__).parent
expenses = Table(name="expenses", source=str(HERE / "assumptions" / "expenses.parquet"),
                 dimensions={"product": "product"}, value="acquisition")

def main(af: ActuarialFrame) -> ActuarialFrame:
    af.acquisition = expenses.lookup(product="TERM")
    af.expense = af.pols * af.acquisition
    return af
""",
    "model_survival.py": """
import datetime as dt
from gaspatchio import ActuarialFrame

def main(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(start_date=dt.date(2025, 1, 1), n_periods=3, frequency="annual")
    af.q = af.month * 0.0 + 0.01
    af.surv_bop = af.q.projection.cumulative_survival()
    return af
""",
}


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Export each small model's audit file through the CLI, as the skill does."""
    root = tmp_path_factory.mktemp("record")
    (root / "assumptions").mkdir()
    pl.DataFrame(
        {"product": ["TERM", "WL"], "acquisition": [500.0, 800.0]}
    ).write_parquet(root / "assumptions" / "expenses.parquet")
    pl.DataFrame({"policy_id": ["P1", "P2"], "pols": [1.0, 2.0]}).write_parquet(
        root / "mp.parquet"
    )
    for name, source in _MODELS.items():
        (root / name).write_text(source)
        stem = name.removesuffix(".py")
        subprocess.run(  # this interpreter: the package under test
            [
                sys.executable,
                "-m",
                "gaspatchio.cli",
                "calc-graph",
                name,
                "mp.parquet",
                "-o",
                f"{stem}.audit.json",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
    return root


def _record(root: Path, stem: str) -> dict[str, object]:
    return json.loads((root / f"{stem}.audit.json").read_text())


def test_item_scalar_leaves_no_assumption_link(exported: Path) -> None:
    """`.item()` makes a literal the record cannot tie to its file; a Table read is named."""
    item, table = _record(exported, "model_item"), _record(exported, "model_table")
    assert item["assumptions"] == []
    assert [a["name"] for a in table["assumptions"]] == ["expenses"]


def test_d5_fence_executes(exported: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The skill's one-row Table read runs as printed and stays a core operation."""
    fences = re.findall(r"```python\n(.*?)```", SKILL_MD.read_text(), re.DOTALL)
    fence = next(f for f in fences if "expenses.lookup(" in f)
    monkeypatch.chdir(exported)
    namespace: dict[str, object] = {}
    exec(compile(fence, str(SKILL_MD), "exec"), namespace)  # noqa: S102 — executing the doc's own example is the test
    frame = namespace["af"]
    assert frame.collect()["expense"].to_list() == [500.0, 1000.0]
    assert frame.graph.tiers().engine_native == ()


def test_survival_read_records_its_window(exported: Path) -> None:
    """The structural route: `cumulative_survival()` records the window `{first, -1}`."""
    out = subprocess.run(  # this interpreter: the package under test
        [
            sys.executable,
            "-m",
            "gaspatchio.cli",
            "graph",
            "precedents",
            "model_survival.audit.json",
            "surv_bop",
            "--json",
        ],
        cwd=exported,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    reads = json.loads(out)["reads"]
    windows = [t.get("periods") for r in reads for t in r["transformations"]]
    assert {"from": "first", "to": -1} in windows


def test_named_cli_surface_exists() -> None:
    """Every command and option the deliverables name is on the shipped CLI."""
    from gaspatchio.cli import app

    root = typer.main.get_command(app)
    commands = root.commands  # type: ignore[attr-defined]
    for name in ("calc-graph", "verify", "diff", "sheet", "graph", "compare"):
        assert name in commands, f"the skill names `gspio {name}`"
    assert {"precedents", "unused"} <= set(commands["graph"].commands)

    def options(command: str) -> set[str]:
        return {opt for param in commands[command].params for opt in param.opts}

    assert {"--xlsx", "--policies", "--results"} <= options("calc-graph")
    assert {"--model", "--model-points", "--results", "--assumptions"} <= options(
        "verify"
    )
    assert {"--results", "-o"} <= options("sheet")
    policies = next(p for p in commands["calc-graph"].params if p.name == "policies")
    assert "Default ':1'" in (policies.help or ""), (
        "the skill says calc-graph samples one policy by default"
    )


def test_named_python_surface_exists() -> None:
    """The fixed-step axis, the reverse rollback and the record readers exist as named."""
    from gaspatchio.accessors.projection import ProjectionColumnAccessor
    from gaspatchio.accessors.projection_frame import ProjectionFrameAccessor
    from gaspatchio.graph import read_artifact

    assert (
        "reverse" in inspect.signature(ProjectionColumnAccessor.accumulate).parameters
    )
    set_params = inspect.signature(ProjectionFrameAccessor.set).parameters
    assert {"n_periods", "step_years", "steps_per_year"} <= set(set_params)
    assert callable(read_artifact)


def test_negative_control_step_is_gated() -> None:
    """The skill asks for negative controls, and its completion gate checks for them."""
    text = SKILL_MD.read_text()
    assert "## Negative controls" in text
    gate = text.split("## COMPLETION GATE", 1)[1]
    assert "Negative controls run" in gate


def test_marinade_blank_cell_caveat_names_its_version() -> None:
    """The xl-marinade warning names the release it was measured on."""
    for path in (SKILL_MD, SPREADSHEET_MD):
        text = " ".join(path.read_text().split())
        assert "xl-marinade 0.4.0 drops edges to blank" in text, path.name
