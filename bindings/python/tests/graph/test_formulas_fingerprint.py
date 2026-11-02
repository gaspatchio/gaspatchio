# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One figure for "did the logic change, or only the data?".

``graph_fingerprint`` is the model as run: a lookup carries its table's
content hash, so a re-sourced basis moves it exactly as an edited formula
does. ``formulas_fingerprint`` is the same fold over trees with every content
digest masked and the tables section left out (section 12.6), so a reviewer
signing off a quarter can quote one figure that moved only if a formula did.

Each claim below is held against both figures at once, because the point of
the second is what it does *not* move with.
"""

from __future__ import annotations

import copy
import datetime
import json
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame, Schedule
from gaspatchio.assumptions import Table
from gaspatchio.cli import app
from gaspatchio.curves import Curve
from gaspatchio.frame.graph import (
    GraphExporter,
    diff_artifacts,
    fold,
    formulas_fingerprint,
    validate_artifact,
)
from gaspatchio.frame.graph.diff import _formulas_said
from gaspatchio.frame.graph.fingerprint import FORMULAS_MASK, content_attributes
from gaspatchio.mortality import MortalityTable
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.schemas import load_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

runner = CliRunner()

# Every data change below re-registers a basis under its own name with new
# rates, which is the case that warning exists for and the case these tests
# are about.
pytestmark = pytest.mark.filterwarnings("ignore:Assumption table .* re-registered")

_STAMP = re.compile(r"sha256:[0-9a-f]{64}")

# Ages a one-dimension basis covers, wide enough for every key below.
_AGES = list(range(20, 121))


# --- the bases and the models --------------------------------------------------


def _basis(name: str, *, bump: float = 0.0) -> Table:
    """Return a one-dimension mortality basis, its rates moved by ``bump``."""
    return Table(
        name=name,
        source=pl.DataFrame(
            {
                "age": _AGES,
                "rate": [0.0005 + 0.0004 * (age - 20) + bump for age in _AGES],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _lookup_model(
    *, bump: float = 0.0, factor: float = 1.0, name: str = "mortality"
) -> ActuarialFrame:
    """Return a model reading one basis, scaling its claims by ``factor``."""
    af = ActuarialFrame(
        pl.DataFrame({"issue_age": [40, 55], "sum_assured": [1e5, 2e5]})
    )
    af.mortality_rate = _basis(name, bump=bump).lookup(age=af.issue_age)
    af.death_claims = af.sum_assured * af.mortality_rate * factor
    return af


def _two_basis_model(*, swapped: bool) -> ActuarialFrame:
    """Return a model reading two bases of one shape, their contents swapped or not."""
    low, high = (0.0, 0.001) if not swapped else (0.001, 0.0)
    af = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    af.male_rate = _basis("male", bump=low).lookup(age=af.issue_age)
    af.female_rate = _basis("female", bump=high).lookup(age=af.issue_age)
    return af


def _curve_model(
    *, shift: float = 0.0, start: datetime.date | None = None
) -> ActuarialFrame:
    """Return a model reading a schedule and a yield curve."""
    schedule = Schedule.from_calendar_grid(
        start_date=start or datetime.date(2026, 1, 31), n_periods=6, frequency="1M"
    )
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2]}))
    af = af.projection.set(schedule=schedule)
    af.years_elapsed = af.projection.t_years()
    curve = Curve.from_zero_rates(
        tenors=[1.0, 2.0, 3.0], rates=[0.02 + shift, 0.025 + shift, 0.03 + shift]
    )
    af.spot_rate = curve.spot_rate(af.years_elapsed)
    af.discount = curve.discount_factor(af.years_elapsed)
    return af


def _join_model(*, load: float = 0.1) -> ActuarialFrame:
    """Return a model joining a product table onto its policies."""
    right = pl.DataFrame({"product_code": ["A", "B"], "load": [load, 0.2]})
    af = ActuarialFrame(
        pl.DataFrame({"product_code": ["A", "B"], "premium": [1.0, 2.0]})
    )
    af = af.join(right, on="product_code")
    af.loaded_premium = af.premium * (1.0 + af.load)
    return af


def _mortality_model(*, bump: float = 0.0) -> ActuarialFrame:
    """Return a model reading a basis through the convention-aware wrapper."""
    wrapper = MortalityTable(
        table=_basis("mortality", bump=bump),
        age_basis="age_last_birthday",
        structure="aggregate",
    )
    af = ActuarialFrame(pl.DataFrame({"issue_age": [40, 55]}))
    af.mortality_rate = wrapper.at(age=af.issue_age)
    return af


def _injection_model(*, shock: float = 0.01, as_array: bool = False) -> ActuarialFrame:
    """Return a model handed a column of shocks at a line."""
    values = [shock, -0.02, 0.03]
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [1.0, 2.0, 3.0]}))
    af.shock = np.array(values) if as_array else pl.Series(values)
    af.shocked = af.sum_assured * (1.0 + af.shock)
    return af


def _rollforward_model(
    *, start: datetime.date, rounded: bool = False
) -> ActuarialFrame:
    """Return a model rolling a fund forward over an explicit schedule."""
    schedule = Schedule.from_calendar_grid(
        start_date=start, n_periods=12, frequency="1M"
    )
    af = ActuarialFrame(
        pl.DataFrame({"av_init": [10.0, 20.0], "credited_rate": [[0.003] * 12] * 2})
    )
    af = af.projection.set(schedule=schedule)
    builder = af.projection.rollforward(states={"av": af["av_init"]})
    builder["av"].grow(
        af["credited_rate"], label="interest", round_charge=2 if rounded else None
    )
    af.fund = compile_rollforward(builder).expr_for("av")
    return af


def _valuation_model(valuation_date: datetime.date) -> ActuarialFrame:
    """Return a model whose valuation date is typed into its projection."""
    af = ActuarialFrame(pl.DataFrame({"issue_age": [40, 50]}))
    af = af.projection.set(
        valuation_date=valuation_date,
        until="maximum_age",
        until_value=42,
        frequency="monthly",
    )
    af.doubled_month = af.month * 2
    return af


def _document(af: ActuarialFrame, *, profile: str = "audit") -> dict[str, Any]:
    """Return ``af``'s exported document, parsed back from the wire."""
    exported: dict[str, Any] = json.loads(GraphExporter(af).export(profile=profile))  # type: ignore[arg-type]
    return exported


def _figures(af: ActuarialFrame) -> tuple[str, str]:
    """Return the document's two model figures: as run, and formulas only."""
    document = _document(af)
    return document["graph_fingerprint"], document["formulas_fingerprint"]


def _moved(
    before: Callable[[], ActuarialFrame], after: Callable[[], ActuarialFrame]
) -> tuple[bool, bool]:
    """Return whether (graph_fingerprint, formulas_fingerprint) moved between two."""
    graph_was, formulas_was = _figures(before())
    graph_now, formulas_now = _figures(after())
    return graph_was != graph_now, formulas_was != formulas_now


# --- what moves which figure ----------------------------------------------------


def test_a_comment_or_a_reformat_moves_neither_figure(tmp_path: Path) -> None:
    """Source locations and layout are no part of either digest."""
    plain = (
        "import polars as pl\n"
        "from gaspatchio import ActuarialFrame\n"
        "af = ActuarialFrame(pl.DataFrame({'sum_assured': [1.0, 2.0]}))\n"
        "af.claims = af.sum_assured * 0.002\n"
    )
    reformatted = (
        "# the valuation model, reformatted and commented\n"
        "import polars as pl\n\n"
        "from gaspatchio import ActuarialFrame\n\n\n"
        "af = ActuarialFrame(\n    pl.DataFrame({'sum_assured': [1.0, 2.0]})\n)\n"
        "# death claims at a flat rate\n"
        "af.claims = (\n    af.sum_assured\n    * 0.002\n)\n"
    )
    figures = []
    for name, source in (("plain.py", plain), ("reformatted.py", reformatted)):
        path = tmp_path / name
        path.write_text(source, "utf-8")
        scope: dict[str, Any] = {}
        exec(compile(source, str(path), "exec"), scope)  # noqa: S102 -- the model under test
        figures.append(_figures(scope["af"]))

    assert figures[0] == figures[1]


def test_a_table_edit_moves_the_graph_fingerprint_only() -> None:
    """A re-sourced basis is data: the formulas did not change."""
    assert _moved(_lookup_model, lambda: _lookup_model(bump=0.0001)) == (True, False)


def test_a_formula_edit_moves_both_figures() -> None:
    """An edited factor is logic, and the as-run figure moves with it too."""
    assert _moved(_lookup_model, lambda: _lookup_model(factor=1.1)) == (True, True)


def test_pointing_a_lookup_at_another_table_name_moves_both() -> None:
    """The table's name is typed in the model, so it stays in the formulas bytes."""
    assert _moved(_lookup_model, lambda: _lookup_model(name="mortality_2026")) == (
        True,
        True,
    )


def test_two_bases_of_one_shape_swapped_by_content_moves_the_graph_only() -> None:
    """Which values each named basis holds is data; which name a line reads is not."""
    assert _moved(
        lambda: _two_basis_model(swapped=False),
        lambda: _two_basis_model(swapped=True),
    ) == (True, False)


def test_a_curve_content_change_moves_the_graph_only() -> None:
    """A shocked curve is a different curve object and the same formula."""
    assert _moved(_curve_model, lambda: _curve_model(shift=0.01)) == (True, False)


def test_a_schedule_content_change_moves_the_graph_only() -> None:
    """A schedule is data, as a table and a curve are."""
    assert _moved(
        _curve_model, lambda: _curve_model(start=datetime.date(2026, 4, 30))
    ) == (True, False)


def test_a_join_s_right_side_moving_moves_the_graph_only() -> None:
    """A joined product table is data, keyed by what the model typed."""
    assert _moved(_join_model, lambda: _join_model(load=0.15)) == (True, False)


def test_a_mortality_basis_read_through_its_wrapper_moves_the_graph_only() -> None:
    """Both of the wrapper's digests are masked: its recipe and its base."""
    assert _moved(_mortality_model, lambda: _mortality_model(bump=0.0001)) == (
        True,
        False,
    )


def test_a_column_of_values_handed_over_moves_the_graph_only() -> None:
    """Injected values are data, and so is the container they arrived in."""
    assert _moved(_injection_model, lambda: _injection_model(shock=0.02)) == (
        True,
        False,
    )
    assert _moved(_injection_model, lambda: _injection_model(as_array=True)) == (
        True,
        False,
    )


def test_a_typed_valuation_date_is_logic() -> None:
    """A quarter roll that edits the date written in the model is a code edit."""
    assert _moved(
        lambda: _valuation_model(datetime.date(2025, 1, 1)),
        lambda: _valuation_model(datetime.date(2025, 4, 1)),
    ) == (True, True)


def _synthetic_model(start: datetime.date) -> ActuarialFrame:
    """Return a model whose timeline start is typed into ``projection.set`` itself."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2]}))
    af = af.projection.set(start_date=start, n_periods=6, frequency="monthly")
    af.doubled_month = af.month * 2
    return af


def test_a_start_typed_into_the_projection_is_logic() -> None:
    """A schedule object's restated start is data; one typed in the model is not."""
    assert _moved(
        lambda: _synthetic_model(datetime.date(2026, 1, 31)),
        lambda: _synthetic_model(datetime.date(2026, 4, 30)),
    ) == (True, True)


def test_a_schedule_under_a_rollforward_moves_the_graph_only() -> None:
    """The compiled identity is the machine; the schedule it runs on is data.

    The rollforward node's ``fingerprint`` and id leave the schedule out, and
    its calls carry the schedule's own digest beside them, which the mask
    covers -- so a re-sourced schedule under a state machine is a data change
    like any other, and an edit to the machine is still a formula change.
    """
    assert _moved(
        lambda: _rollforward_model(start=datetime.date(2026, 1, 31)),
        lambda: _rollforward_model(start=datetime.date(2026, 4, 30)),
    ) == (True, False)
    assert _moved(
        lambda: _rollforward_model(start=datetime.date(2026, 1, 31)),
        lambda: _rollforward_model(start=datetime.date(2026, 1, 31), rounded=True),
    ) == (True, True)


# --- what is masked, and nothing else -------------------------------------------


def _attribute_digests(tree: object) -> Iterator[tuple[str, str]]:
    """Yield (identifier, key) for every stamped digest in a call attribute."""
    if isinstance(tree, dict):
        if tree.get("op") == "call":
            for key, value in (tree.get("attrs") or {}).items():
                if isinstance(value, str) and _STAMP.fullmatch(value):
                    yield tree["name"], key
        for value in tree.values():
            yield from _attribute_digests(value)
    elif isinstance(tree, list):
        for member in tree:
            yield from _attribute_digests(member)


def test_every_digest_a_tree_carries_is_masked_but_the_compiled_machine_s() -> None:
    """The mask covers every content digest the producer writes into a tree.

    Read off executable documents of models that read every kind of value
    object, so a digest added to a signature without joining the mask is
    caught here rather than by a quarter whose formulas figure moved on data.
    """
    found: set[tuple[str, str]] = set()
    for model in (
        _lookup_model,
        _curve_model,
        _join_model,
        _mortality_model,
        lambda: _rollforward_model(start=datetime.date(2026, 1, 31)),
    ):
        for node in _document(model(), profile="executable")["nodes"]:
            found.update(_attribute_digests(node.get("expr")))

    unmasked = {
        (name, key) for name, key in found if key not in content_attributes(name)
    }
    assert unmasked == {
        ("rollforward", "fingerprint"),
        ("rollforward.state", "fingerprint"),
    }
    assert {key for _, key in found} >= {
        "table_fingerprint",
        "right_fingerprint",
        "mortality",
        "curve",
        "schedule",
        "schedule_source_sha",
    }


def test_the_mask_is_one_fixed_text() -> None:
    """Not a digest's shape, so a printed masked tree is never read as holding one."""
    assert FORMULAS_MASK == "masked"
    assert not _STAMP.search(FORMULAS_MASK)


# --- reading the figure back ----------------------------------------------------


def test_the_producer_and_the_document_agree_on_the_figure() -> None:
    """The envelope states exactly what the graph folds to."""
    af = _lookup_model()

    stated = _document(af)["formulas_fingerprint"]

    assert stated == f"sha256:{formulas_fingerprint(fold(af)).hex()}"


@pytest.mark.parametrize(
    "model",
    [
        _lookup_model,
        _curve_model,
        _join_model,
        _mortality_model,
        _injection_model,
        lambda: _rollforward_model(start=datetime.date(2026, 1, 31)),
    ],
)
def test_an_executable_document_recomputes_its_figure(
    model: Callable[[], ActuarialFrame],
) -> None:
    """A consumer holding the trees reaches the figure, and catches a forged one."""
    document = _document(model(), profile="executable")
    forged = copy.deepcopy(document)
    forged["formulas_fingerprint"] = "sha256:" + "0" * 64
    del forged["document_digest"]

    honest = validate_artifact(document, deep=True)
    caught = validate_artifact(forged, deep=True)

    assert not [f for f in honest.findings if "formulas_fingerprint" in f.message]
    assert [
        f.severity for f in caught.findings if "formulas_fingerprint" in f.message
    ] == ["error"]


def test_an_audit_document_s_figure_is_read_as_written() -> None:
    """With no trees there is nothing to take it over again, as for a local digest."""
    forged = _document(_lookup_model())
    forged["formulas_fingerprint"] = "sha256:" + "0" * 64
    del forged["document_digest"]

    report = validate_artifact(forged, deep=True)

    assert not [f for f in report.findings if "formulas_fingerprint" in f.message]


def test_a_document_written_before_the_figure_still_validates() -> None:
    """The member is optional: an older file is read as it always was."""
    import jsonschema

    older = _document(_lookup_model(), profile="executable")
    del older["formulas_fingerprint"]

    jsonschema.Draft202012Validator(load_schema()).validate(older)
    report = validate_artifact(older, deep=True)
    assert not [f for f in report.findings if "formulas_fingerprint" in f.message]


def test_the_schema_refuses_a_figure_that_is_not_a_digest() -> None:
    """The member is a stamped digest or absent, never a placeholder."""
    import jsonschema

    document = _document(_lookup_model())
    document["formulas_fingerprint"] = FORMULAS_MASK

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(load_schema()).validate(document)


# --- the change report's headline -----------------------------------------------


def _written(tmp_path: Path, name: str, document: dict[str, Any]) -> Path:
    """Write ``document`` beside the others and return where."""
    path = tmp_path / name
    path.write_text(json.dumps(document), "utf-8")
    return path


def test_diff_says_the_formulas_held_and_names_the_data_that_moved(
    tmp_path: Path,
) -> None:
    """A quarter that only re-sourced a basis reads as exactly that."""
    before = _written(tmp_path, "q1.json", _document(_lookup_model()))
    after = _written(tmp_path, "q2.json", _document(_lookup_model(bump=0.0001)))

    said = runner.invoke(app, ["diff", str(before), str(after)])
    stored = runner.invoke(app, ["diff", str(before), str(after), "--json"])

    assert said.exit_code == 1
    assert (
        "formulas unchanged (formulas_fingerprint equal); data changed: table mortality"
        in said.output
    )
    compared = json.loads(stored.output)["compared"]
    assert (
        compared["before"]["formulas_fingerprint"]
        == (compared["after"]["formulas_fingerprint"])
    )


def test_diff_says_a_formula_changed(tmp_path: Path) -> None:
    """An edited formula reads as one, whatever data moved beside it."""
    before = _written(tmp_path, "q1.json", _document(_lookup_model()))
    after = _written(
        tmp_path, "q2.json", _document(_lookup_model(bump=0.0001, factor=1.1))
    )

    said = runner.invoke(app, ["diff", str(before), str(after)])

    assert said.exit_code == 1
    assert "formulas changed (formulas_fingerprint differs)" in said.output
    assert "formulas unchanged" not in said.output


def test_diff_says_nothing_new_about_a_document_without_the_figure(
    tmp_path: Path,
) -> None:
    """A file written before the member gets no line inferred from node changes."""
    older = _document(_lookup_model())
    del older["formulas_fingerprint"]
    before = _written(tmp_path, "q1.json", older)
    after = _written(tmp_path, "q2.json", _document(_lookup_model(bump=0.0001)))

    said = runner.invoke(app, ["diff", str(before), str(after)])
    report = diff_artifacts(older, json.loads(after.read_text("utf-8")))

    assert said.exit_code == 1
    assert "formulas_fingerprint" not in said.output
    assert _formulas_said(report) is None
    assert report.compared[0].to_dict()["formulas_fingerprint"] is None
