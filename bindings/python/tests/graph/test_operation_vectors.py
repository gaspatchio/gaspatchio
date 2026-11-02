# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Published synthetic vectors exercise the producer and a standalone reader."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast
from zipfile import ZipFile

import jsonschema
import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError, neutral_dtype
from gaspatchio._semantic.ir import BinOp
from gaspatchio.assumptions import Table
from gaspatchio.column import ExpressionProxy
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.curves import Curve
from gaspatchio.curves._curve import Curve as RuntimeCurve
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.op_json import op_node_from_json
from gaspatchio.frame.lowering.artefacts import (
    register_curve,
    register_schedule,
    register_table,
)
from gaspatchio.rollforward import RollforwardBuilder, compile_rollforward
from gaspatchio.schedule import Schedule
from gaspatchio.schedule._schedule import Schedule as RuntimeSchedule

if TYPE_CHECKING:
    from collections.abc import Iterator

_ROOT = Path(__file__).resolve().parents[4]
_VECTORS = _ROOT / "bindings/python/gaspatchio/schemas/vectors"
_REFERENCE = _ROOT / "spec/graph-artifact/conformance/reference.py"
_IDENTITY = _REFERENCE.with_name("identity.py")
_CORPUS = _VECTORS.parent / "conformance/corpus.json"


# What reads, in a reviewed-boundary sentence, as a claim about nulls. Matches
# "null", "nulls" and "nullable", which are the three spellings the checklist
# uses, and nothing else -- a claim worded some other way is not caught, so
# this is a floor under the evidence rather than a proof of completeness.
_A_NULL_BOUNDARY = re.compile(r"\bnull", re.IGNORECASE)


def _cases() -> Iterator[dict[str, Any]]:
    for path in sorted(_VECTORS.glob("*.json")):
        bundle = json.loads(path.read_text())
        yield from bundle["cases"]


def _carries_a_null(value: object) -> bool:
    """Return True when ``value`` is a null or holds one at any depth."""
    if value is None:
        return True
    return isinstance(value, list) and any(_carries_a_null(item) for item in value)


def _inputs_carry_a_null(case: dict[str, Any]) -> bool:
    """Return True when any input column of ``case`` carries a null value."""
    return any(_carries_a_null(column["values"]) for column in case["inputs"].values())


def _decode(value: object) -> object:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict) and set(value) == {"nonfinite"}:
        return {"nan": math.nan, "+inf": math.inf, "-inf": -math.inf}[
            value["nonfinite"]
        ]
    return value


# The input-only dtype names the envelope added for the conversion clauses:
# the storage types a column arrives in that section 10 has no name for, and
# that a conversion is the door out of. They appear on inputs and never on an
# expected result, which is why they are listed apart from the five above.
_ARRIVING_FROM_OUTSIDE: Final[frozenset[str]] = frozenset(
    {"u64", "i128", "u128", "categorical", "duration"}
)


def _dtype(name: str) -> pl.DataType | type[pl.DataType]:
    if name.startswith("list["):
        return pl.List(_dtype(name[5:-1]))
    if name.startswith("array["):
        element, _, width = name[len("array[") : -1].rpartition(",")
        return pl.Array(_dtype(element), int(width))
    return {
        "i64": pl.Int64,
        "f64": pl.Float64,
        "bool": pl.Boolean,
        "str": pl.String,
        "date": pl.Date,
        "u64": pl.UInt64,
        "i128": pl.Int128,
        "u128": pl.UInt128,
        "categorical": pl.Categorical,
        # A whole number of microseconds per value (the envelope's input-only name).
        "duration": pl.Duration("us"),
    }[name]


def _arrives_from_outside(dtype: str) -> bool:
    """Return whether an input column's type is one section 10 cannot name."""
    return dtype in _ARRIVING_FROM_OUTSIDE or dtype.startswith("array[")


def _date_values(value: object) -> object:
    if isinstance(value, list):
        return [_date_values(item) for item in value]
    return date.fromisoformat(value) if isinstance(value, str) else value


def _schedule(payload: dict[str, Any]) -> Schedule:
    if payload["kind"] == "fixed_step":
        return Schedule.fixed_step(
            n_periods=payload["n_periods"],
            step_years=payload.get("step_years"),
            steps_per_year=payload.get("steps_per_year"),
        )
    if payload["kind"] == "from_inception":
        return Schedule.from_inception(
            inception_column=payload["inception_column"],
            n_periods=payload["n_periods"],
            frequency=payload["frequency"],
        )
    if payload["kind"] == "per_policy_grid":
        return Schedule.from_per_policy_grid(
            start_date=date.fromisoformat(payload["start_date"]),
            frequency=payload["frequency"],
            until_kind=payload["until_kind"],
            until_value_column=payload["until_value_column"],
        )
    return Schedule.from_calendar_grid(
        start_date=date.fromisoformat(payload["start_date"]),
        n_periods=payload["n_periods"],
        frequency=payload["frequency"],
        anchor=payload["anchor"],
    )


def _register_assumptions(case: dict[str, Any]) -> None:
    for assumption in case.get("assumptions", []):
        payload = assumption["payload"]
        if assumption["kind"] == "schedule":
            schedule = _schedule(payload)
            # Public stubs currently redeclare these runtime classes.
            assert isinstance(schedule, RuntimeSchedule)
            assert schedule.canonical_form() == payload
            assert register_schedule(schedule) == assumption["source_sha"]
        elif assumption["kind"] == "table":
            source = pl.DataFrame(
                payload["rows"],
                schema=[
                    (column["name"], _dtype(column["dtype"]))
                    for column in payload["columns"]
                ],
                orient="row",
            )
            table = Table(
                name=assumption["name"],
                source=source,
                dimensions={name: name for name in payload["dimensions"]},
                value=payload["value"],
                storage_mode=case.get("producer_setup", {}).get(
                    "table_storage", "auto"
                ),
            )
            assert register_table(table) == assumption["fingerprint"]
        else:
            curve = Curve.from_zero_rates(
                tenors=payload["tenors"],
                rates=payload["rates"],
                interpolation=payload["interpolation"],
            )
            assert isinstance(curve, RuntimeCurve)
            assert curve.canonical_form() == payload
            assert register_curve(curve) == assumption["source_sha"]


def _register_compilation(case: dict[str, Any], frame: ActuarialFrame) -> None:
    build = case.get("producer_build")
    if build is None:
        return
    builder = RollforwardBuilder(
        states={name: frame[column] for name, column in build["states"].items()},
        schedule=_schedule(build["schedule"]),
        track_increments=build["track_increments"],
    )
    for step in build["steps"]:
        target = builder[step["state"]]
        if step["method"] == "add":
            target.add(frame[step["operand"]], label=step["label"])
        elif step["method"] == "subtract":
            target.subtract(frame[step["operand"]], label=step["label"])
        elif step["method"] == "grow":
            target.grow(frame[step["operand"]], label=step["label"])
        else:
            assert step["method"] == "charge"
            target.charge(frame[step["operand"]], label=step["label"])
    compiled = compile_rollforward(builder)
    assert compiled.fingerprint() == case["expr"]["attrs"]["fingerprint"]
    # Emitting the extraction files the compilation with the replay registry.
    attrs = case["expr"]["attrs"]
    if case["expr"]["name"] == "rollforward.increment":
        compiled.increment_for(attrs["label"])
    elif case["expr"]["name"] == "rollforward.struct":
        compiled.plugin_expr()
    else:
        compiled.expr_for(attrs["state"])


def _recorded_door(case: dict[str, Any], frame: ActuarialFrame) -> ActuarialFrame:
    setup = case["producer_setup"]
    if setup["kind"] == "projection_set" and "start_date" not in setup:
        return frame.projection.set(
            n_periods=setup["n_periods"],
            step_years=setup.get("step_years"),
            steps_per_year=setup.get("steps_per_year"),
        )
    if setup["kind"] == "projection_set":
        return frame.projection.set(
            start_date=date.fromisoformat(setup["start_date"]),
            n_periods=setup["n_periods"],
            frequency=setup["frequency"],
        )
    return frame.join(
        pl.DataFrame(setup["right"]),
        on=setup["on"],
        how=setup["how"],
        on_missing=setup.get("on_missing", "raise"),
    )


def _assert_values(actual: object, expected: object, atol: float, rtol: float) -> None:
    if isinstance(actual, date):
        actual = actual.isoformat()
    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for received, wanted in zip(actual, expected, strict=True):
            _assert_values(received, wanted, atol, rtol)
        return
    if expected is None or isinstance(expected, (bool, str)):
        assert type(actual) is type(expected)
        assert actual == expected
        return
    if isinstance(expected, float) and math.isnan(expected):
        assert isinstance(actual, float)
        assert math.isnan(actual)
        return
    assert isinstance(actual, (int, float))
    assert not isinstance(actual, bool)
    assert isinstance(expected, (int, float))
    if not math.isfinite(expected):
        assert actual == expected
        return
    assert actual == expected or abs(actual - expected) <= atol + rtol * abs(expected)


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["id"]) for case in _cases() if case["producer_check"]],
)
def test_producer_agrees_with_published_vector(case: dict[str, Any]) -> None:
    columns = {
        name: pl.Series(
            name,
            cast(
                "list[object]",
                _date_values(item["values"])
                if "date" in item["dtype"]
                else _decode(item["values"]),
            ),
            dtype=_dtype(item["dtype"]),
        )
        for name, item in case["inputs"].items()
    }
    frame = _selected(case, ActuarialFrame(pl.DataFrame(columns)))
    _register_assumptions(case)
    _register_compilation(case, frame)
    node = op_node_from_json(case["expr"])
    # Exercise semantic replay through the same proxy/assignment door as a formula.
    if case["case_kind"] == "recording-door-value":
        frame = _recorded_door(case, frame)
    elif case.get("producer_setup", {}).get("kind") == "join" and "refusal" in case:
        # A door that refuses where it is written: the join that leaves a
        # policy without a row refuses before the frame changes (11.1.2).
        with pytest.raises(ValueError, match=case["producer_message"]):
            _recorded_door(case, frame)
        return
    elif isinstance(node, BinOp) and node.op in {"lt", "le", "gt", "ge", "eq", "ne"}:
        frame.answer = ConditionExpression(node, frame)
    else:
        # A conversion refuses a type it has no form for while the formula is
        # being written, not while it runs: the type is known then, and a
        # refusal that waits for data would let the model be built wrong. So
        # a refusal case accepts either door, and says which it took. A
        # calendar operation over a value per period is refused where the
        # line is written too, as a ValueError naming the operand (11.1.33).
        try:
            frame.answer = ExpressionProxy._from_node(node, frame)  # noqa: SLF001
        except (TypeError, ValueError) as refused:
            if "refusal" not in case:
                raise
            assert re.search(case["producer_message"], str(refused))
            return
    if "refusal" in case:
        if case["case_kind"] == "artifact-type-refusal":
            for profile in ("audit", "executable"):
                with pytest.raises(UnmappedDtypeError, match=case["producer_message"]):
                    GraphExporter(frame).export(profile=profile)
            return
        with pytest.raises(
            pl.exceptions.PolarsError,
            match=case.get("producer_message", "stored numeric predicate"),
        ):
            frame.collect()
        return
    output_column = case.get("output_column", "answer")
    values = frame.collect()
    if "sort_output_by" in case:
        # Streaming row position is not row identity after a relational join.
        values = values.sort(case["sort_output_by"])
    result = values[output_column]
    assert neutral_dtype(result.dtype, column="answer") == case["expected"]["dtype"]
    _assert_values(
        result.to_list(),
        _decode(case["expected"]["values"]),
        case["comparison"]["atol"],
        case["comparison"]["rtol"],
    )
    # An input column arriving in a type section 10 cannot name is the one
    # the conversion exists to get out of, and it cannot stay on an exported
    # frame -- which is the refusal that names the conversion in the first
    # place. Dropping it is what an author following that refusal does.
    exportable = frame.drop(
        *[
            name
            for name, item in case["inputs"].items()
            if _arrives_from_outside(item["dtype"])
        ]
    )
    artifact = GraphExporter(exportable).export(profile="executable")
    assert validate_artifact(artifact, deep=True).ok
    answer = next(
        n for n in json.loads(artifact)["nodes"] if n["column"] == output_column
    )
    assert answer["tier"] == "core"
    assert answer["expr"] == case["expr"]
    # The record carries each step a selection case states as the case states
    # it, a join's right side under the digest the case publishes (section 7.6).
    recorded = json.loads(artifact).get("selection", [])
    assert [(step["kind"], step["expr"]) for step in recorded] == [
        (step["kind"], step["expr"]) for step in case.get("selection", [])
    ]


def _selected(case: dict[str, Any], frame: ActuarialFrame) -> ActuarialFrame:
    """Take each of a selection case's steps on the frame, as a model writes them."""
    for step in case.get("selection", []):
        if step["kind"] == "filter":
            predicate = op_node_from_json(step["expr"])
            frame = frame.filter(ExpressionProxy._from_node(predicate, frame))  # noqa: SLF001
            continue
        attrs = step["expr"]["attrs"]
        frame = frame.join(
            pl.DataFrame(step["right"]), on=attrs["on"], how=step["kind"]
        )
    return frame


def test_broadcast_records_the_implicit_axis_dependency() -> None:
    """Changing the timeline must propagate through a broadcast in the graph."""
    frame = ActuarialFrame({"rate": [0.02], "month": [[0, 1, 2]]})
    frame.answer = frame.rate.projection.broadcast_to_periods()
    assert set(frame.graph.precedents("answer")) == {"rate", "month"}
    assert "answer@1" in frame.graph.affected("month")
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    answer = next(node for node in artifact["nodes"] if node["column"] == "answer")
    assert answer["expr"]["args"] == [
        {"op": "col", "name": "rate"},
        {"op": "col", "name": "month"},
    ]
    assert frame.collect()["answer"].to_list() == [[0.02, 0.02, 0.02]]


def test_independent_standard_library_reader_accepts_vectors() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed local interpreter and repository fixtures
        [
            sys.executable,
            "-I",
            str(_REFERENCE),
            *map(str, sorted(_VECTORS.glob("*.json"))),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["cases"] == len(list(_cases()))
    assert report["failures"] == {}


def test_independent_reader_rejects_a_wrong_expected_answer(tmp_path: Path) -> None:
    bundle = json.loads((_VECTORS / "base.json").read_text())
    case = bundle["cases"][0]
    case["expected"]["values"][0] = 123456
    bundle["cases"] = [case]
    source = tmp_path / "wrong-answer.json"
    source.write_text(json.dumps(bundle))
    result = subprocess.run(  # noqa: S603 -- fixed local verifier and a synthetic wrong answer
        [sys.executable, "-I", str(_REFERENCE), str(source)],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert case["id"] in json.loads(result.stdout)["failures"]


def test_independent_current_token_identity_reader() -> None:
    """The grammar proof also travels with the schema, without private inputs."""
    original = Path(__file__).parent / "goldens/conformance_corpus.json"
    assert _CORPUS.read_bytes() == original.read_bytes()
    result = subprocess.run(  # noqa: S603 -- local independent verifier and published corpus
        [sys.executable, "-I", str(_IDENTITY), str(_CORPUS)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "algorithm": "gspv0-preview-3",
        "nodes": 12,
        "failures": [],
    }


def test_independent_identity_reader_detects_a_mutation(tmp_path: Path) -> None:
    """It recomputes a local digest instead of trusting the published value."""
    artifact = json.loads(_CORPUS.read_text())
    artifact["nodes"][0]["local_fingerprint"] = "sha256:" + "0" * 64
    source = tmp_path / "mutated-corpus.json"
    source.write_text(json.dumps(artifact))
    result = subprocess.run(  # noqa: S603 -- local verifier over an intentional mutation
        [sys.executable, "-I", str(_IDENTITY), str(source)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["failures"] == [
        "sum_assured: local_fingerprint",
        "document_digest",
    ]


def test_independent_identity_reader_recomputes_the_formulas_fingerprint(
    tmp_path: Path,
) -> None:
    """A moved formulas-only figure is caught even under a seal taken again over it.

    Section 12.6's figure is published in the corpus beside its graph
    fingerprint, so the kit's reader recomputes it from the masked trees rather
    than reading it as written. The mutation is re-sealed, so the seal cannot
    be what catches it.
    """
    artifact = json.loads(_CORPUS.read_text())
    artifact["formulas_fingerprint"] = "sha256:" + "0" * 64
    unsealed = {
        key: value for key, value in artifact.items() if key != "document_digest"
    }
    artifact["document_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                unsealed,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
    )
    source = tmp_path / "resealed-corpus.json"
    source.write_text(json.dumps(artifact))
    result = subprocess.run(  # noqa: S603 -- local verifier over an intentional mutation
        [sys.executable, "-I", str(_IDENTITY), str(source)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["failures"] == ["formulas_fingerprint"]


def test_vector_envelopes_and_index_agree() -> None:
    directory = _CORPUS.parent
    schema = json.loads((directory / "vector-envelope.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for source in sorted(_VECTORS.glob("*.json")):
        validator.validate(json.loads(source.read_text()))
    index = json.loads((directory / "index.json").read_text())
    assert index["case_counts"] == Counter(c["case_kind"] for c in _cases())
    assert len({c["id"] for c in _cases()}) == len(list(_cases()))
    # That the map's identifiers are the producer's own table is held once,
    # in that table's census: ``test_vocabulary.py`` compares the checked-in
    # bytes with what the generator prints from the rows, and holds ``TIERS``
    # to the same rows' tier column. Here the map is what the kit's index is
    # read against.
    contracts = json.loads((_REFERENCE.parent / "contracts.json").read_text())
    assert {op["identifier"] for op in index["operations"]} == set(contracts)
    assert Counter(op["status"] for op in index["operations"]) == {
        "bounded-value": 99,
        "structural-identity": 1,
        "excluded-output": 1,
    }
    for operation in index["operations"]:
        assert operation["clause"] == contracts[operation["identifier"]]
        if operation["status"] == "bounded-value":
            assert any(
                example["kind"] in {"value", "recording-door-value"}
                for example in operation["examples"]
            )


def test_archive_carries_current_reader_source() -> None:
    sources = [
        _REFERENCE,
        _IDENTITY,
        _REFERENCE.with_name("content.py"),
        _REFERENCE.with_name("citation.py"),
        *(_REFERENCE.parent / "reader").glob("*.py"),
    ]
    with ZipFile(_CORPUS.parent / "reader.pyz") as archive:
        expected = {str(path.relative_to(_REFERENCE.parent)) for path in sources}
        assert set(archive.namelist()) == expected | {"__main__.py"}
        for source in sources:
            assert archive.read(str(source.relative_to(_REFERENCE.parent))) == (
                source.read_bytes()
            )


def test_boundary_review_covers_every_clause_with_resolvable_evidence() -> None:
    """A packaged checklist must not claim missing cases or omit a contract clause.

    The claim a checklist makes is that a boundary was reviewed against the
    cases it lists, so a boundary named in the prose with no case exhibiting
    it is a claim with nothing behind it -- and the prose being non-empty is
    no evidence that anything was reviewed. Nulls are where that is checked
    here: a clause naming an identifier and claiming a reviewed null boundary
    must list at least one case with a null in its inputs.

    Clauses naming no identifier -- section 10's type vocabulary, 11.1.11's
    signature schedule -- are outside this check, because their claims are
    about the format rather than about an operation and their evidence is
    spread across every clause that carries a value.
    """
    path = _CORPUS.parent / "boundary-review.json"
    review = json.loads(path.read_text())
    index = json.loads((_CORPUS.parent / "index.json").read_text())
    assert (
        index["boundary_review"]["sha256"]
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    clauses = {row["clause"]: row for row in review["clauses"]}
    assert len(clauses) == len(review["clauses"])
    assert {operation["clause"] for operation in index["operations"]} <= clauses.keys()
    by_id = {case["id"]: case for case in _cases()}
    ids = set(by_id)
    for row in clauses.values():
        assert row["reviewed_boundaries"]
        assert row["limits"]
        assert row["case_ids"] or row["producer_tests"]
        assert set(row["case_ids"]) <= ids
        if row["identifiers"] and _A_NULL_BOUNDARY.search(row["reviewed_boundaries"]):
            evidence = [
                case_id
                for case_id in row["case_ids"]
                if _inputs_carry_a_null(by_id[case_id])
            ]
            assert evidence, (
                f"clause {row['clause']} says it reviewed a null boundary, and "
                f"none of its {len(row['case_ids'])} cases for "
                f"{row['identifiers']} has a null anywhere in its inputs"
            )
        for source in row["producer_tests"]:
            assert (_ROOT / "bindings/python" / source).is_file()
    for operation in index["operations"]:
        assert operation["identifier"] in clauses[operation["clause"]]["identifiers"]
        if operation["status"] == "bounded-value":
            assert "empty-portfolio-" + operation["identifier"] in ids


@pytest.mark.parametrize("identity", [False, True])
def test_packaged_reader_runs_outside_the_repository(
    tmp_path: Path, *, identity: bool
) -> None:
    """Only distributed data and the standard-library archive travel to the reader."""
    directory = shutil.copytree(_CORPUS.parent, tmp_path / "conformance")
    vectors = shutil.copytree(_VECTORS, tmp_path / "vectors")
    arguments = (
        ["--identity", str(directory / "corpus.json")]
        if identity
        else list(map(str, sorted(vectors.glob("*.json"))))
    )
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and synthetic copied package data
        [sys.executable, "-I", str(directory / "reader.pyz"), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    if identity:
        assert report["nodes"] == 12
        assert report["failures"] == []
    else:
        assert report["cases"] == len(list(_cases()))
        assert report["failures"] == {}
