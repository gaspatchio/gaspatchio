# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How much of a whole model the format can account for, one calculation at a time.

``af.graph.holes()`` says whether a model can account for every column it
holds. It cannot say whether every line is written in the format's own
vocabulary, and an empty list reads as though it did: a line written in an
engine's own expression language is recorded, so it is no hole, and it is
still a line only that engine can run. ``af.graph.tiers()`` answers the
second question, and the tests below hold it to four claims:

- a present value discounted in Polars' own language leaves no hole and is
  counted ``engine_native``, while the same model written in the
  framework's own terms is counted all core;
- every recorded calculation is counted, a definition a later line replaced
  included, and nothing that computes nothing is;
- all three tiers are stated whatever they hold, because a zero is a claim;
- the census agrees node for node with the tier each node carries in the
  exported document of the same frame, so it reports the file's own answer
  rather than a second opinion beside it.

The Audit View states the same census in its strip, read off the document it
shows, and the last test here holds the census it is tested against to this
one, fixture by fixture.
"""

from __future__ import annotations

import datetime
import doctest
import importlib.util
import inspect
import io
import json
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._authoring import emit
from gaspatchio.frame.graph import (
    GraphExporter,
    GraphFrameAccessor,
    TierCensus,
    document_digest_of,
    node_accounting,
    validate_artifact,
)
from gaspatchio.frame.graph import tiers as tiers_module
from gaspatchio.frame.graph.tiers import _KINDS_THAT_COMPUTE, _census_of_document
from gaspatchio.frame.graph.validate import _LEAF_KINDS
from gaspatchio.frame.lowering import polars as polars_lowering
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.schemas import load_schema
from tests.graph.test_queries import _swap_into_plan
from tests.graph.test_viewer_fixtures import _committed_documents

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext

# An operation from outside the format's vocabulary, registered the way an
# extension registers one: it runs, and nothing has classified it.
_UNCLASSIFIED = "acme.smoothing"


@pytest.fixture
def unclassified_operation(monkeypatch: pytest.MonkeyPatch) -> str:
    """Register an extension's operation for one test, and take it away after."""
    polars_lowering.ensure_rules_loaded()

    def smooth(node: Call, ctx: LoweringContext | None) -> pl.Expr:
        return polars_lowering.lower_polars(node.args[0], ctx) * 0.5

    monkeypatch.setitem(polars_lowering.LOWERINGS, _UNCLASSIFIED, smooth)
    return _UNCLASSIFIED


def _book() -> pl.DataFrame:
    """Return two policies, each with a mortality rate and a discount factor."""
    return pl.DataFrame(
        {
            "sum_assured": [100_000.0, 250_000.0],
            "mortality_rate": [0.001_23, 0.002_04],
            "discount_factor": [0.95, 0.93],
        }
    )


def _plain_model() -> ActuarialFrame:
    """Return claims and their present value, both in the framework's own terms."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af.pv = af.claims * af.discount_factor
    return af


def _native_model() -> ActuarialFrame:
    """Return the same model with the present value written in Polars instead."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    return af.with_columns((pl.col("claims") * pl.col("discount_factor")).alias("pv"))


def _escaped_model() -> ActuarialFrame:
    """Return a model reaching Polars through the named escape rather than a batch."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af.largest_claim_so_far = af.claims.polars_native().cum_max()
    return af


def _reloaded_model() -> ActuarialFrame:
    """Return claims loaded in Polars and then loaded again in the framework's terms.

    Three definitions of one column, the middle one engine-native: the
    first and the second are replaced, and both were lines of the model.
    """
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af = af.with_columns((pl.col("claims") * 1.1).alias("claims"))
    af.claims = af.claims * 1.05
    return af


def _model_with_what_computes_nothing() -> ActuarialFrame:
    """Return a model holding a column of handed-over values and a hole."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1])
    # Written into the plan past every recording route, which is what leaves
    # a column nothing accounts for.
    _swap_into_plan(af, (pl.col("sum_assured") * 0.02).alias("lapse_reserve"))
    return af


def _projected_model() -> ActuarialFrame:
    """Return a model on a monthly timeline, whose own columns are calculations."""
    af = ActuarialFrame(_book())
    af = af.projection.set(
        start_date=datetime.date(2026, 1, 1), n_periods=3, frequency="monthly"
    )
    af.claims = af.sum_assured * af.mortality_rate
    return af


def _renamed_model() -> ActuarialFrame:
    """Return claims renamed to the name the rest of the model reads them by."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af = af.rename({"claims": "death_claims"})
    af.pv = af.death_claims * af.discount_factor
    return af


def _dated_model() -> ActuarialFrame:
    """Return a policy anniversary the frame derives from an entry date."""
    af = ActuarialFrame(pl.DataFrame({"entry_date": [datetime.date(2026, 1, 1)]}))
    af.date.add_duration("entry_date", "12mo", new_col_name="anniversary")
    return af


def _joined_model() -> ActuarialFrame:
    """Return a model that brings an expense rate in by product."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1", "P2"], "product_code": ["TERM", "WL"]})
    )
    af = af.join(
        pl.DataFrame({"product_code": ["TERM", "WL"], "expense_rate": [0.05, 0.08]}),
        on="product_code",
    )
    af.expenses = af.expense_rate * 1_000.0
    return af


def _rollforward_model() -> ActuarialFrame:
    """Return a fund charged on its running balance, and a charge struck on it."""
    af = ActuarialFrame({"av_init": [100.0], "me": [[0.001] * 2]})
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="monthly"
    )
    builder = af.projection.rollforward(states={"av": af["av_init"]})
    _ = builder["av"].charge(af["me"], label="me_charge")
    af.account_value = compile_rollforward(builder).expr_for("av")
    af.fund_charge = af.account_value * 0.01
    return af


def _unclassified_model() -> ActuarialFrame:
    """Return claims smoothed by an operation nothing has classified."""
    af = ActuarialFrame(_book())
    af.claims = af.sum_assured * af.mortality_rate
    af.smoothed_claims = emit.call(_UNCLASSIFIED, (af.claims,), af)
    return af


# --- a line in Polars' own language: no hole, and not core ---------------------


def test_a_present_value_discounted_in_polars_is_no_hole_and_not_core() -> None:
    """Neither model has a hole, and only one of them is written all in core."""
    plain = _plain_model()
    native = _native_model()

    assert plain.graph.holes() == native.graph.holes() == []
    assert plain.graph.tiers() == TierCensus(
        core=("claims@1", "pv@1"), engine_native=(), opaque=()
    )
    assert native.graph.tiers() == TierCensus(
        core=("claims@1",), engine_native=("pv@1",), opaque=()
    )
    assert native.graph.tiers().counts == {"core": 1, "engine_native": 1, "opaque": 0}


def test_the_named_escape_is_counted_where_it_was_used() -> None:
    """``.polars_native()`` states its cost at the line, and the census repeats it."""
    census = _escaped_model().graph.tiers()

    assert census.core == ("claims@1",)
    assert census.engine_native == ("largest_claim_so_far@1",)


def test_an_operation_nothing_has_classified_is_counted_opaque(
    unclassified_operation: str,
) -> None:
    """A registered extension runs, and the census says nothing vouches for it."""
    af = _unclassified_model()

    assert unclassified_operation == _UNCLASSIFIED
    assert af.graph.tiers() == TierCensus(
        core=("claims@1",), engine_native=(), opaque=("smoothed_claims@1",)
    )


# --- what is counted -----------------------------------------------------------


def test_every_tier_is_stated_even_where_it_holds_nothing() -> None:
    """``0 opaque`` is a claim about the model, not an absence to leave out."""
    counts = _plain_model().graph.tiers().counts

    assert counts == {"core": 2, "engine_native": 0, "opaque": 0}
    assert list(counts) == ["core", "engine_native", "opaque"]


def test_a_definition_a_later_line_replaced_is_counted_too() -> None:
    """It was a line of the model, and the lines after it were computed from it."""
    census = _reloaded_model().graph.tiers()

    assert census.core == ("claims@1", "claims@3")
    assert census.engine_native == ("claims@2",)
    assert census.opaque == ()


def test_nothing_that_computes_nothing_is_counted() -> None:
    """An arriving column, handed-over values and a hole carry no tier at all."""
    af = _model_with_what_computes_nothing()

    assert [hole.column for hole in af.graph.holes()] == ["lapse_reserve"]
    assert af.graph.tiers() == TierCensus(
        core=("claims@1",), engine_native=(), opaque=()
    )


def test_every_node_that_computes_is_counted_not_only_assignments() -> None:
    """A joined, a renamed, a timeline and a derived date column are calculations.

    The file records each as computed, with a tier of its own, so the census
    counts each -- on a large model a good share of the count is these.
    """
    assert _joined_model().graph.tiers().core == ("expense_rate@1", "expenses@1")
    assert _renamed_model().graph.tiers().core == (
        "claims@1",
        "death_claims@1",
        "pv@1",
    )
    assert _projected_model().graph.tiers().core == (
        "projection_start_date@1",
        "projection_end_date@1",
        "num_proj_months@1",
        "month@1",
        "claims@1",
    )
    assert _dated_model().graph.tiers().core == ("anniversary@1",)


def test_the_census_follows_the_frame_as_the_model_grows() -> None:
    """A line written after a census was taken is in the next one."""
    af = _plain_model()
    assert af.graph.tiers().engine_native == ()

    af.largest_claim_so_far = af.claims.polars_native().cum_max()

    assert af.graph.tiers().engine_native == ("largest_claim_so_far@1",)


# --- the census and the exported document ----------------------------------------

_MODELS: dict[str, Callable[[], ActuarialFrame]] = {
    "plain": _plain_model,
    "native": _native_model,
    "escaped": _escaped_model,
    "reloaded": _reloaded_model,
    "computes-nothing": _model_with_what_computes_nothing,
    "projected": _projected_model,
    "joined": _joined_model,
    "renamed": _renamed_model,
    "dated": _dated_model,
    "rollforward": _rollforward_model,
    "unclassified": _unclassified_model,
}


@pytest.mark.usefixtures("unclassified_operation")
@pytest.mark.parametrize("build", list(_MODELS.values()), ids=list(_MODELS))
def test_the_census_agrees_node_for_node_with_the_exported_document(
    build: Callable[[], ActuarialFrame],
) -> None:
    """Every node the file gives a tier is at that tier here, in the file's order.

    And nothing else is here: the counts add up to the nodes the file gives
    a tier to, so a node the file leaves without one -- an arriving column,
    a hole, a running state -- cannot be counted by the census either.
    """
    af = build()
    nodes: list[dict[str, Any]] = json.loads(GraphExporter(af).export())["nodes"]

    census = af.graph.tiers()

    for tier in ("core", "engine_native", "opaque"):
        written = tuple(node["id"] for node in nodes if node["tier"] == tier)
        assert getattr(census, tier) == written, tier
    assert sum(census.counts.values()) == sum(
        node["tier"] is not None for node in nodes
    )
    # And the reading the command prints from agrees with both.
    assert _census_of_document(nodes) == census


def _read_the_node_line(line: str) -> tuple[int, dict[str, int]]:
    """Return the total the node line states, and each kind's count, by kind."""
    head, _, tail = line.partition(": ")
    parts: dict[str, int] = {}
    for part in tail.split(", "):
        count, _, kind = part.partition(" ")
        parts[kind.removesuffix("s")] = int(count)
    return int(head.split()[0]), parts


@pytest.mark.usefixtures("unclassified_operation")
@pytest.mark.parametrize("build", list(_MODELS.values()), ids=list(_MODELS))
def test_the_node_line_adds_up_and_counts_what_the_census_counts(
    build: Callable[[], ActuarialFrame],
) -> None:
    """The line above the tier line accounts for every node, and agrees with it.

    Every node is counted under its kind, so the parts add up to the nodes
    the file holds. And the calculations it counts -- computed nodes and
    compiled rollforwards -- are exactly the calculations the census counts,
    so the two lines a reviewer reads one above the other never disagree
    about how many there are.
    """
    af = build()
    nodes: list[dict[str, Any]] = json.loads(GraphExporter(af).export())["nodes"]

    total, parts = _read_the_node_line(node_accounting(nodes))

    assert total == len(nodes)
    assert sum(parts.values()) == total, parts
    assert parts["computed"] + parts.get("compiled rollforward", 0) == sum(
        af.graph.tiers().counts.values()
    )


def test_the_agreement_is_tested_at_every_tier(unclassified_operation: str) -> None:
    """The models above between them reach all three tiers, so no tier is untested."""
    reached = {
        tier
        for build in _MODELS.values()
        for tier, count in build().graph.tiers().counts.items()
        if count
    }

    assert unclassified_operation == _UNCLASSIFIED
    assert reached == {"core", "engine_native", "opaque"}


# --- a census read off a document ------------------------------------------------


def test_the_census_offers_its_three_tuples_and_their_counts_and_no_more() -> None:
    """The type ``tiers()`` returns is compared and read, and built by nobody else.

    Its three tuples and their counts are what a caller reads and a test
    compares. Building one is the frame's business, and the command's when it
    reads a document back, so no public constructor stands beside the class's
    own -- and that one takes its tuples by name, since three tuples of node
    ids in the wrong order would be three wrong answers that all type-check.
    """
    public = {name for name in dir(TierCensus) if not name.startswith("_")}
    # Held without its signature, the way a caller passing tuples by
    # position would hold it.
    build: Any = TierCensus

    assert public == {"core", "engine_native", "opaque", "counts"}
    with pytest.raises(TypeError):
        build(("claims@1",), (), ())


def test_a_document_s_census_keeps_its_order_and_counts_by_kind() -> None:
    """What the file says, in the order it says it, counting what computes."""
    written: list[dict[str, Any]] = [
        {"id": "sum_assured", "kind": "input", "tier": None},
        {"id": "pv@1", "kind": "computed", "tier": "engine_native"},
        {"id": "claims@1", "kind": "computed", "tier": "core"},
        {"id": "state:av@eop", "kind": "state", "tier": None},
        {"id": "rollforward:4a635c5ff001", "kind": "rollforward", "tier": "core"},
        {"id": "lapse_reserve", "kind": "hole", "tier": None},
    ]

    census = _census_of_document(written)

    assert census == TierCensus(
        core=("claims@1", "rollforward:4a635c5ff001"),
        engine_native=("pv@1",),
        opaque=(),
    )


@pytest.mark.parametrize(
    ("kind", "written"),
    [
        ("computed", {"tier": None}),
        ("computed", {}),
        ("rollforward", {"tier": None}),
    ],
    ids=["computed-null", "computed-missing", "rollforward-null"],
)
def test_a_calculation_the_document_gives_no_tier_is_refused_by_name(
    kind: str, written: dict[str, Any]
) -> None:
    """A document with its tiers stripped is not a model with nothing in it.

    Counting a calculation nowhere would print ``0 core, 0 engine_native,
    0 opaque`` -- the zero the census calls a claim -- about a model that
    computes. The refusal names the node instead.
    """
    nodes: list[dict[str, Any]] = [{"id": "claims@1", "kind": kind, **written}]

    with pytest.raises(ValueError, match=r"'claims@1'.*no tier.*gspio validate"):
        _census_of_document(nodes)


def test_the_refusal_s_advice_is_true_and_the_validator_names_the_same_line() -> None:
    """The census sends the reader to ``gspio validate``, which names the node.

    A census refuses a calculation that carries no tier, and its refusal says
    to check the document with ``gspio validate``, which names every field
    that departs from the format. The schema allows a null tier, because a
    leaf needs one, so that advice is only true where the validator holds a
    calculation to a stated tier -- which is what this checks, on a document
    the producer wrote and one hand edited.
    """
    document = json.loads(GraphExporter(_plain_model()).export())
    (pv,) = [node for node in document["nodes"] if node["id"] == "pv@1"]
    pv["tier"] = None

    with pytest.raises(ValueError, match=r"'pv@1'.*no tier.*gspio validate"):
        _census_of_document(document["nodes"])
    report = validate_artifact(document)
    assert [f.where for f in report.findings if f.severity == "error"] == ["pv@1"]


def test_a_tier_the_format_does_not_define_is_refused_by_name() -> None:
    """Counting it nowhere would understate the model; the refusal names it."""
    written: list[dict[str, Any]] = [
        {"id": "claims@1", "kind": "computed", "tier": "fast"}
    ]

    with pytest.raises(ValueError, match=r"'claims@1'.*'fast'.*gspio validate"):
        _census_of_document(written)


# The two payload sections section 17 reserves, each in the hand-built
# example that carries one: a state graph and a nested valuation. No producer
# in this package writes either, and a document may still carry them.
_GOLDENS = Path(__file__).resolve().parent / "goldens"
_PAYLOAD_EXAMPLES: dict[str, str] = {
    "state_graph": "state_graph_example",
    "nested_valuation": "nested_valuation_example",
}


@pytest.mark.parametrize("kind", list(_PAYLOAD_EXAMPLES))
def test_a_document_s_census_counts_a_payload_section_at_its_tier(kind: str) -> None:
    """A state graph and a nested valuation compute, and each states a tier.

    Section 8 calls three kinds leaves -- an arriving column, a hole, a
    running state -- and section 11.2 states a tier on every node that has
    anything to execute, which is every other kind. A census that counted
    only computed nodes and compiled rollforwards would read ``0 opaque``
    off a document whose state graph was opaque, which is the claim the
    census exists not to make.
    """
    example = _GOLDENS / f"{_PAYLOAD_EXAMPLES[kind]}.json"
    nodes: list[dict[str, Any]] = json.loads(example.read_text("utf-8"))["nodes"]
    (payload,) = [node for node in nodes if node["kind"] == kind]

    assert payload["id"] in _census_of_document(nodes).core

    payload["tier"] = "opaque"
    assert _census_of_document(nodes).opaque == (payload["id"],)


def test_the_census_counts_every_kind_section_8_does_not_call_a_leaf() -> None:
    """Between them the leaves and the kinds that compute are every kind there is.

    The validator holds a leaf to a null tier and a calculation to a stated
    one, and the census counts the calculations. A kind the schema gained
    without a decision about which of the two it is would be counted by
    neither and refused by neither, so it fails here instead.
    """
    kinds = set(load_schema()["$defs"]["node"]["properties"]["kind"]["enum"])

    assert _KINDS_THAT_COMPUTE.isdisjoint(_LEAF_KINDS)
    assert kinds == _KINDS_THAT_COMPUTE | _LEAF_KINDS


def test_the_census_examples_run() -> None:
    """The examples on the census are executed, not merely displayed.

    ``af.graph.tiers()``'s own examples run with the rest of the query
    module's. These are the ones on the class it returns, which live in a
    module nothing else executes the examples of.
    """
    documented = [
        test for test in doctest.DocTestFinder().find(tiers_module) if test.examples
    ]
    assert documented, "the census docstrings carry no runnable example"

    for examples in documented:
        report = io.StringIO()
        runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
        runner.run(examples, out=report.write)
        assert runner.failures == 0, f"{examples.name}:\n{report.getvalue()}"


# --- where a reader of holes() is told --------------------------------------------


def test_holes_says_an_empty_list_is_not_every_line_core() -> None:
    """The qualifier stands where the reader of an empty list will look for it.

    ``holes()`` is the call a reviewer makes to ask what a model cannot
    account for, and an empty answer reads as more than it says. Its own
    documentation has to say so, and has to name the call that answers the
    question it does not.
    """
    said = " ".join((inspect.getdoc(GraphFrameAccessor.holes) or "").split())

    assert "An empty list does not mean every line is ``core``." in said
    assert "``engine_native``" in said
    assert "``opaque``" in said
    assert ":meth:`tiers` says which" in said


# --- the census the Audit View is held to ----------------------------------------

# The census of every committed viewer fixture and of the two payload
# examples, as the core takes it, which viewer/test/tiers.test.ts holds the
# page's own reading to.
_VIEWER_CENSUS = (
    Path(__file__).resolve().parents[4] / "viewer" / "fixtures" / "tier-census.json"
)

# What writes it again, named in the failure that asks for it.
_REGENERATION = "uv run python -m tests.graph.test_tier_census"


def _census_of_the_viewer_fixtures() -> dict[str, dict[str, Any]]:
    """Return the core's census of each document the page's census is held to.

    Every committed viewer fixture that records tiers, by its name, and the
    two payload examples, as ``goldens/`` and their name: the page opens
    none of the examples, and they are the only documents that carry the
    two kinds. For each, the counts at all three tiers, and the
    calculations below core by node id, in the order the file writes them.
    A fixture in which no node carries a tier is left out, because it has
    no census to give, and the page is tested to state none for it.
    """
    documents = {fixture.stem: fixture for fixture in _committed_documents()}
    for example in _PAYLOAD_EXAMPLES.values():
        documents[f"goldens/{example}"] = _GOLDENS / f"{example}.json"
    census: dict[str, dict[str, Any]] = {}
    for name, path in documents.items():
        nodes = json.loads(path.read_text(encoding="utf-8"))["nodes"]
        if not any("tier" in node for node in nodes):
            continue
        counted = _census_of_document(nodes)
        census[name] = {
            "counts": counted.counts,
            "engine_native": list(counted.engine_native),
            "opaque": list(counted.opaque),
        }
    return census


@pytest.mark.skipif(
    not _VIEWER_CENSUS.parent.is_dir(), reason="needs this repository's viewer/ tree"
)
def test_the_page_is_held_to_the_core_s_census_of_every_fixture() -> None:
    """The page's census is tested against this file, so this file is held to the core.

    ``viewer/test/tiers.test.ts`` holds the page's counts and names to the
    committed census of every fixture the page is tested against, and of
    the two payload examples. This holds the committed census to the core's
    own reading of the same documents, the one ``gspio calc-graph`` prints,
    so a fixture added, exported again or retiered without the census being
    written again fails here rather than leaving the page held to an answer
    the core no longer gives. One fixture, ``tiers``, carries a calculation
    at each of the three tiers, so all three are compared.
    """
    committed = json.loads(_VIEWER_CENSUS.read_text(encoding="utf-8"))
    taken = _census_of_the_viewer_fixtures()

    assert {"engine_native", "opaque"} <= {
        tier
        for counted in taken.values()
        for tier in ("engine_native", "opaque")
        if counted[tier]
    }
    assert committed == taken, (
        "viewer/fixtures/tier-census.json is not the census the core takes today "
        "of the committed fixtures. If a fixture moved on purpose, write it again "
        f"with `{_REGENERATION}` from bindings/python."
    )


# The fixture the census is tested at all three tiers on, and the script that
# exports it from the model and the points committed beside it.
_TIERS_FIXTURE = _VIEWER_CENSUS.parent / "tiers.json"
_TIERS_EXPORT = _VIEWER_CENSUS.parent / "tiers" / "export.py"
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _unstamped(document: dict[str, Any]) -> dict[str, Any]:
    """Return ``document`` without when it was written, its seal or its versions.

    ``producer.versions`` goes with the package's version: it names the build
    that ran -- the extension's sha256, the platform -- and is withheld in the
    export, so it is masked as ``created_at`` is.
    """
    rest = json.loads(json.dumps(document))
    rest.pop("created_at")
    rest.pop("document_digest")
    rest["producer"].pop("version")
    rest["producer"].pop("versions", None)
    return rest


@pytest.mark.skipif(
    not _VIEWER_CENSUS.parent.is_dir(), reason="needs this repository's viewer/ tree"
)
def test_the_tiers_fixture_is_the_export_of_the_model_beside_it(
    tmp_path: Path,
) -> None:
    """The fixture with a line at each tier is what its committed model exports.

    ``viewer/fixtures/tiers.json`` is ``gspio calc-graph`` over the
    ``model.py`` and ``model_points.csv`` beside it, run by the ``export.py``
    beside them. Exported again here it is the same document but for when it
    was written, its seal and the version stamped on it, which is the
    installed core's. The committed one is stamped with this tree's own
    version, which ``export.py`` refuses to stamp anything else with, and
    carries a seal over its own bytes.
    """
    spec = importlib.util.spec_from_file_location("tiers_export", _TIERS_EXPORT)
    assert spec is not None
    assert spec.loader is not None
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)

    exporter.export(tmp_path / "tiers.json")
    again = json.loads((tmp_path / "tiers.json").read_text("utf-8"))
    committed = json.loads(_TIERS_FIXTURE.read_text("utf-8"))
    tree = tomllib.loads(_PYPROJECT.read_text("utf-8"))["project"]["version"]

    assert committed["producer"]["version"] == tree
    assert document_digest_of(committed) == committed["document_digest"]
    assert _unstamped(again) == _unstamped(committed)


def _write_the_viewer_census() -> None:
    """Write the census the page is held to, from the fixtures it is taken over."""
    if not _VIEWER_CENSUS.parent.is_dir():
        msg = (
            "The viewer's fixtures are not in this tree, so there is no census "
            "to write."
        )
        raise SystemExit(msg)
    written = json.dumps(_census_of_the_viewer_fixtures(), indent=2, sort_keys=True)
    _VIEWER_CENSUS.write_text(f"{written}\n", encoding="utf-8")


if __name__ == "__main__":
    _write_the_viewer_census()
