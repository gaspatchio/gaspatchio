# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The published corpus a second implementation proves its agreement against.

Section 12.5 of ``spec/graph-artifact/v0-preview.md`` publishes a small
artifact together with every digest in it, so that somebody writing a second
producer can reproduce those digests from the corpus's own calculations
before claiming to have implemented the byte grammar. A format with one
implementation is a press release.

Three things have to say the same thing, and each has a test here: the
artifact this module's model exports, the file checked in beside it, and the
digest table printed in the specification. Any two of them agreeing is a copy
of a copy; all three agreeing is a corpus.

The model is a function in this module rather than data sitting beside the
corpus, so that it cannot drift from the file it produced. After a deliberate
change to the byte grammar, regenerate the file with::

    uv run python -m tests.graph.test_conformance_corpus

and reprint its digests into section 12.5, which is what section 12.5
requires whenever ``fingerprint_algorithm`` moves.
"""

from __future__ import annotations

import datetime
import hashlib
import inspect
import json
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import polars as pl

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter, validate_artifact

if TYPE_CHECKING:
    from collections.abc import Iterable

# The repository this checkout is, so that a published file can name a path
# inside it rather than a path on the machine that wrote it.
_REPOSITORY = Path(__file__).resolve().parents[4]
_CORPUS_PATH = Path(__file__).parent / "goldens" / "conformance_corpus.json"
_SPEC_PATH = _REPOSITORY / "spec" / "graph-artifact" / "v0-preview.md"

# Where in the specification the corpus is printed, and the shape the digest
# table is printed in. Both are read back out below rather than restated, so
# that the document and the file cannot drift apart without a test failing.
_CORPUS_SECTION = "### 12.5 The conformance corpus"
_DIGEST_TABLE_HEADER = ("Node", "`local_fingerprint`", "`fingerprint`")
_SHA256_CELL = re.compile(r"sha256:[0-9a-f]{64}")

# What regenerates the file, named in the failure that asks for it. A
# staleness guard that fails as a diff of two eight-kilobyte blobs has told
# the reader what is wrong and nothing about the cure.
_REGENERATION = "uv run python -m tests.graph.test_conformance_corpus"


# --- the model the corpus is an account of ----------------------------------


def _the_corpus_model() -> ActuarialFrame:
    """Return the model the published corpus is an account of.

    Eleven columns, between them carrying one of each thing the byte grammar
    of section 12.1 has to get right: a column that arrived with the data, an
    arithmetic formula, a conditional, a formula holding a sequence literal,
    an accessor call carrying a typed offset, a whole column of values
    injected at a line, a column the model wrote twice, a leaf whose type is
    a date, a date literal under the tag the grammar mints for one, a
    reduction whose answer has a different shape from its operand, and a
    decimal literal the grammar now tells from its own negation.

    The date three arrived with ``gspv0-preview-2`` and the signed zero with
    ``gspv0-preview-3``, for the same reason both times. A grammar that grew
    a date tag, or that stopped writing a negative zero as zero, published
    beside a corpus carrying neither would leave the one new thing in the
    grammar untested by the one artifact whose job is to let a second
    implementation test it -- and would publish two artifacts under two
    tokens carrying identical digests, which is the shape section 12.2
    forbids comparing.

    ``.list.sum()`` and not ``.sum()``: ``select_loaded_claims`` is a
    per-period column, and this is the fold along its periods. The bare
    spelling is the engine's fold down the *rows* of the model-point file,
    a different calculation whose answer depends on the order the rows stand
    in, and section 11.1.12 forbids writing this identifier for it.

    Deliberately no rollforward and no assumption table. The corpus is
    pinned, and one that moved when a payload section landed would be pinning
    the wrong thing.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0, 500_000.0],
                "entry_date": [
                    datetime.date(2019, 3, 1),
                    datetime.date(2021, 7, 15),
                    datetime.date(2023, 11, 30),
                ],
            }
        )
    )
    af.death_claims = af.sum_assured * 0.001_23
    af.ceded_claims = (
        when(af.sum_assured > 200_000.0).then(af.death_claims).otherwise(0.0)
    )
    af.select_loaded_claims = af.death_claims * [1.5, 1.25, 1.0]
    af.prior_period_claims = af.select_loaded_claims.projection.at_period(-1)
    af.simulated_shock = pl.Series([0.01, -0.02, 0.03])
    af.net_cashflow = af.sum_assured * 0.02 - af.death_claims + af.ceded_claims
    af.net_cashflow = af.net_cashflow * (1.0 + af.simulated_shock)
    af.post_reform = (
        when(af.entry_date > datetime.date(2022, 1, 1)).then(1.0).otherwise(0.0)
    )
    af.total_claims = af.select_loaded_claims.list.sum()
    af.unceded_claims = (
        when(af.ceded_claims == 0.0).then(af.death_claims).otherwise(-0.0)
    )
    return af


def _export_the_corpus_model() -> dict[str, Any]:
    """Return that model's artifact, in the form the corpus is published in.

    ``source_root`` is what makes the published locations repository-relative,
    and it is a producer setting rather than something this module does to the
    document afterwards. It has to be: the seal covers every byte, so a
    location rewritten after ``export()`` would leave the corpus carrying a
    digest taken over a document nobody holds, and its own deep reading would
    refuse the file section 12.5 publishes.

    **The source is withheld, and that is a statement about this fixture
    rather than a recommendation.** The corpus's model is written in this test
    module, beside every other test in it; its text is not the corpus's
    subject, and inlining it would publish thirty kilobytes of this
    repository's test scaffolding into a conformance document that exists to
    pin a byte grammar. What the entry still carries is the path and the
    digest, so a reader can see where the model was written and check a copy
    against it -- which is exactly the sentence section 6.1's third reason was
    added to make sayable, and the corpus is now a published example of it.
    A model file exported by ``gspio calc-graph`` carries its text.

    **The library versions are withheld too**, for the reason every committed
    document withholds them: they name one machine's build, and a published
    file must not move with it.
    """
    return cast(
        "dict[str, Any]",
        json.loads(
            GraphExporter(_the_corpus_model()).export(
                source_root=_REPOSITORY, include_source=False, versions="withheld"
            )
        ),
    )


def _write_the_corpus() -> None:
    """Write the corpus file from the model above -- regeneration, in one place."""
    published = json.dumps(_export_the_corpus_model(), indent=2, ensure_ascii=False)
    _CORPUS_PATH.write_text(f"{published}\n", "utf-8")


def _the_published_corpus() -> dict[str, Any]:
    """Return the corpus as it is checked in."""
    published: dict[str, Any] = json.loads(_CORPUS_PATH.read_text("utf-8"))
    return published


def _digests_of(artifact: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Return both of every node's digests, keyed by node id."""
    return {
        node["id"]: (node["local_fingerprint"], node["fingerprint"])
        for node in artifact["nodes"]
    }


def _the_corpus_model_with_its_values(*, retain: bool = True) -> dict[str, Any]:
    """Return the same model exported with the values one collect read.

    The published corpus carries no values at all -- it is the account of a
    calculation, and a digest is taken over none of them. This is the same
    model put through the other half of the export, which is where a
    superseded definition either carries its own number or does not.
    """
    model = _the_corpus_model()
    values = model.collect()
    return cast(
        "dict[str, Any]",
        json.loads(
            GraphExporter(model).export(values, retain_superseded=retain),
        ),
    )


def _the_executable_tree(node_id: str) -> dict[str, Any]:
    """Return one node's operation tree, from the profile that writes one.

    The corpus is published at the ``audit`` profile and carries no ``expr``;
    section 12.5 prints the trees separately and says they are what the
    digests were taken over. This is the same model at the other profile, so
    a test about a literal's own bytes reads the literal rather than the
    sentence quoted beside it.
    """
    artifact = cast(
        "dict[str, Any]",
        json.loads(
            GraphExporter(_the_corpus_model()).export(
                source_root=_REPOSITORY, include_source=False, profile="executable"
            )
        ),
    )
    return cast("dict[str, Any]", _node_of(artifact, node_id)["expr"])


def _node_of(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[node['id'] for node in artifact['nodes']]}"
    return cast("dict[str, Any]", found[0])


# --- reading the specification back --------------------------------------


def _specification_section(path: Path, heading: str) -> str:
    """Return the text under ``heading``, up to the next heading of any depth."""
    text = path.read_text("utf-8")
    tail = text[text.index(heading) + len(heading) :]
    stop = tail.find("\n#")
    return tail if stop < 0 else tail[:stop]


def _markdown_table(section: str) -> list[list[str]]:
    """Return the rows of the markdown table in ``section``, cells stripped.

    A parser over the cells rather than one pattern matched against a whole
    row, so that a row the specification prints in the wrong shape arrives as
    a row of the wrong width instead of quietly failing to match and quietly
    not being checked.
    """
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|")
    ]
    return [row for row in rows if not all(_is_rule(cell) for cell in row)]


def _is_rule(cell: str) -> bool:
    """Return whether ``cell`` is part of a table's alignment row rather than data."""
    return set(cell) <= set("-: ")


def _digest_table_from_specification(path: Path) -> dict[str, tuple[str, str]]:
    """Return the digests section 12.5 prints, keyed by node id.

    Every pipe-led line in the section joins one map, so a second table
    landing in section 12.5 would silently widen this into a reader of two
    tables at once and the check below would start comparing rows nobody
    meant it to compare. The header settles which table this is, the width
    guard settles that each row has three cells to read, and the shape
    guard settles that two of them are digests -- which is as much as a
    parser over a document can honestly claim.

    The two guards are one question asked twice because a row of the wrong
    width and a row of the wrong content fail differently: a narrower table
    would otherwise be an ``IndexError`` from inside a comprehension, which
    names the line that tripped over it and not the document that is wrong.

    Raises:
        ValueError: If the table is not headed the way this reads it, if a
            row is not three cells wide, or if a row's digest cells are not
            digests -- any of which would mean the check below was silently
            checking something else.

    """
    header, *body = _markdown_table(_specification_section(path, _CORPUS_SECTION))
    if tuple(header) != _DIGEST_TABLE_HEADER:
        msg = f"section 12.5's digest table is headed {header!r}"
        raise ValueError(msg)
    wrong_width = [row for row in body if len(row) != len(_DIGEST_TABLE_HEADER)]
    if wrong_width:
        msg = f"section 12.5 prints rows that are not digest rows: {wrong_width!r}"
        raise ValueError(msg)
    digests = {
        _unquoted(row[0]): (_unquoted(row[1]), _unquoted(row[2])) for row in body
    }
    misshapen = {
        node: cells
        for node, cells in digests.items()
        if not all(_SHA256_CELL.fullmatch(cell) for cell in cells)
    }
    if misshapen:
        msg = f"section 12.5 prints non-digest cells for {sorted(misshapen)}"
        raise ValueError(msg)
    return digests


def _envelope_from_specification(path: Path) -> dict[str, str]:
    """Return the envelope fields section 12.5 prints beside the digest table."""
    printed = re.compile(r"^- \*\*`(?P<field>[a-z_]+)`:\*\* `(?P<value>[^`]+)`$")
    return {
        found["field"]: found["value"]
        for line in _specification_section(path, _CORPUS_SECTION).splitlines()
        if (found := printed.match(line.strip()))
    }


def _model_source_from_specification(path: Path) -> str:
    """Return the corpus model's source as section 12.5 prints it.

    Raises:
        ValueError: If the section prints no source at all, which would leave
            a second implementation with digests and nothing to take them of.

    """
    section = _specification_section(path, _CORPUS_SECTION)
    found = re.search(r"```python\n(?P<source>.*?)```", section, re.DOTALL)
    if found is None:
        msg = "section 12.5 prints no source for the corpus model"
        raise ValueError(msg)
    return found["source"]


def _unquoted(cell: str) -> str:
    """Return a table cell with the backticks the document prints it in removed."""
    return cell.strip("`")


def _schema_refusals(artifact: dict[str, Any]) -> set[str]:
    """Return the name of every field the published schema refuses in ``artifact``."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    missing = re.compile(r"^'(?P<field>[^']+)' is a required property$")
    validator = jsonschema.Draft202012Validator(load_schema())
    refused: set[str] = set()
    for error in validator.iter_errors(artifact):
        named = missing.match(error.message)
        refused.add(named["field"] if named else error.message)
    return refused


def _kinds(artifact: dict[str, Any], field: str) -> set[str | None]:
    """Return every value ``field`` takes across the artifact's nodes."""
    values: Iterable[str | None] = (node[field] for node in artifact["nodes"])
    return set(values)


# --- the corpus is reproducible ---------------------------------------------


def test_the_published_corpus_is_reproduced_exactly() -> None:
    """A second implementation proves agreement against these digests."""
    artifact = _export_the_corpus_model()
    published = _the_published_corpus()

    assert artifact["fingerprint_algorithm"] == published["fingerprint_algorithm"]
    assert artifact["graph_fingerprint"] == published["graph_fingerprint"]
    assert artifact["formulas_fingerprint"] == published["formulas_fingerprint"]
    assert _digests_of(artifact) == _digests_of(published)


def test_the_specification_prints_the_same_digests_the_corpus_carries() -> None:
    """The document and the file cannot drift apart without this failing."""
    published = _the_published_corpus()

    printed = _digest_table_from_specification(_SPEC_PATH)

    assert printed == _digests_of(published)


def test_the_specification_prints_the_model_identity_the_corpus_carries() -> None:
    """The digest standing for the whole model, and the grammar it was taken under."""
    published = _the_published_corpus()

    printed = _envelope_from_specification(_SPEC_PATH)

    assert printed == {
        "fingerprint_algorithm": published["fingerprint_algorithm"],
        "graph_fingerprint": published["graph_fingerprint"],
        "formulas_fingerprint": published["formulas_fingerprint"],
    }


# The bytes a column of values handed over at a line encodes as once both of
# its attributes are masked -- section 12.6 prints them, and every such node
# in every model shares them.
_MASKED_INJECTION = (
    "0408696e6a6563746564000207636f6e74656e7414066d61736b6564"
    "066f726967696e14066d61736b6564"
)


def test_the_formulas_figure_follows_from_the_published_digests_and_one_mask() -> None:
    """A second implementation reaches the corpus's formulas figure from section 12.

    The corpus reads no table, curve or schedule, so the only content digest
    in its trees is the injected column's: every other node's masked local
    digest is the one the table publishes. Fold the published locals with
    that one replaced by the masked bytes section 12.6 prints, over the reads
    section 12.5 states, and take the two sections over the result.
    """
    published = _the_published_corpus()
    masked_injection = hashlib.sha256(bytes.fromhex(_MASKED_INJECTION)).digest()
    folded: dict[str, bytes] = {}
    for node in published["nodes"]:
        local = (
            masked_injection
            if node["provenance"] == "injected"
            else bytes.fromhex(node["local_fingerprint"].removeprefix("sha256:"))
        )
        reads = b"".join(folded[read] for read in node["reads"])
        folded[node["id"]] = hashlib.sha256(local + reads).digest()

    pairs = b"".join(
        _uvarint(len(node_id.encode())) + node_id.encode() + folded[node_id]
        for node_id in sorted(folded)
    )
    taken = hashlib.sha256(_uvarint(len(folded)) + pairs + _uvarint(0)).hexdigest()

    assert published["formulas_fingerprint"] == f"sha256:{taken}"
    assert _MASKED_INJECTION in _specification_section(
        _SPEC_PATH, "### 12.6 The formulas-only fingerprint"
    )


def _uvarint(value: int) -> bytes:
    """Return ``value`` as section 12.1's unsigned base-128 varint, low group first."""
    out = bytearray()
    while True:
        group, value = value & 0x7F, value >> 7
        if not value:
            out.append(group)
            return bytes(out)
        out.append(group | 0x80)


def test_the_specification_prints_the_model_the_digests_were_taken_of() -> None:
    """Digests with no model behind them are a number nobody can reproduce."""
    printed = _model_source_from_specification(_SPEC_PATH)

    assert inspect.getsource(_the_corpus_model) in printed


# --- what the corpus is, and what it deliberately is not ---------------------


def test_the_corpus_holds_no_rollforward_and_no_assumption_payload() -> None:
    """It is pinned, so it must not depend on anything still being built."""
    published = _the_published_corpus()

    assert published["assumptions"] == []
    assert "rollforward" not in _kinds(published, "kind")
    assert "state" not in _kinds(published, "kind")


def test_the_corpus_covers_every_shape_it_was_built_to_pin() -> None:
    """Eleven columns, twelve accounts of them, one of each thing they cover.

    The twelfth account is the redefinition: a column written twice is two
    nodes, and the superseded one is the history that makes a change report
    possible. Named by what each node is rather than counted, because a
    count passes just as happily with two of one shape and none of another.
    """
    published = _the_published_corpus()
    nodes = {node["id"]: node for node in published["nodes"]}

    assert {node["column"] for node in published["nodes"]} == {
        "sum_assured",
        "entry_date",
        "death_claims",
        "ceded_claims",
        "select_loaded_claims",
        "prior_period_claims",
        "simulated_shock",
        "net_cashflow",
        "post_reform",
        "total_claims",
        "unceded_claims",
    }
    assert nodes["sum_assured"]["provenance"] == "model_points"
    assert nodes["simulated_shock@1"]["provenance"] == "injected"
    assert nodes["death_claims@1"]["formula"] == "af.sum_assured * 0.001_23"
    assert nodes["ceded_claims@1"]["formula"].startswith("when(")
    assert "[1.5, 1.25, 1.0]" in nodes["select_loaded_claims@1"]["formula"]
    assert "at_period(-1)" in nodes["prior_period_claims@1"]["formula"]
    assert nodes["net_cashflow@1"]["in_final_schema"] is False
    assert nodes["net_cashflow@2"]["in_final_schema"] is True
    # The three the token move added, each named by the thing it is here to
    # exercise rather than by being present: a leaf whose type is a date, a
    # date literal under its own key, and a fold whose answer is a scalar
    # where its operand is a per-period column.
    assert nodes["entry_date"]["dtype"] == "date"
    assert nodes["post_reform@1"]["formula"].startswith("when(af.entry_date >")
    assert nodes["total_claims@1"]["formula"] == "af.select_loaded_claims.list.sum()"
    # The one `gspv0-preview-3` added: a decimal literal whose sign the
    # grammar keeps. Read off the operation tree rather than the quoted
    # formula, because `formula` is no part of any node's canonical bytes
    # and it is the literal's own bytes that this column is here for.
    otherwise = _the_executable_tree("unceded_claims@1")["otherwise"]
    assert math.copysign(1.0, otherwise["value"]) < 0
    assert otherwise["value"] == 0.0


def test_the_corpus_names_no_path_from_the_machine_that_wrote_it() -> None:
    """A published file locates the model in the repository, not on a disk."""
    published = _the_published_corpus()

    located = [
        node["source_location"]
        for node in published["nodes"]
        if node["source_location"] is not None
    ]

    assert located
    assert all(
        location.startswith("bindings/python/tests/graph/") for location in located
    ), located


def test_the_corpus_is_itself_a_conforming_artifact() -> None:
    """It is published, so the one thing it must not be is unreadable.

    Nothing in it is refused, and the empty set is the point: while any
    field of the node record was still being written, that field's name sat
    here as a known absence, and the last of them left on the change that
    filled it. The section publishing this file tells a reader holding only
    the document that they are not missing anything, and that sentence is
    now true of the file as well as of the digests beside it.
    """
    assert _schema_refusals(_the_published_corpus()) == set()


def test_the_corpus_is_still_the_artifact_this_producer_writes() -> None:
    """Not only the digests: everything the file says, the producer still says.

    The digests are what the corpus is for, and they are what a second
    implementation checks. But a corpus whose edges, sections or field order
    stopped matching what the producer emits would be a published account of
    a producer nobody runs any more, and nothing else here would notice: no
    digest is taken over an edge.

    Three fields are excluded and none is a fact about the model. The
    timestamp is when the file was written, and moves on every regeneration;
    the producer block moves on every release; and the seal is taken with the
    timestamp inside it, so two exports of one unchanged model carry two
    seals. Pinning any of them would ask for the corpus to be regenerated by
    things that did not change it. These three are exactly what a re-export
    moves without the model moving, which is the same rule anywhere else a
    fresh export is held against a stored document.
    """
    fresh = _export_the_corpus_model()
    published = _the_published_corpus()

    for artifact in (fresh, published):
        del artifact["created_at"]
        del artifact["producer"]
        del artifact["document_digest"]

    assert fresh == published, (
        "The published corpus is no longer what this producer writes. If the "
        "change that caused this was deliberate, regenerate the file with "
        f"`{_REGENERATION}` from bindings/python -- and if any digest moved "
        "with it, section 12.5's table is reprinted in the same breath, "
        "because a corpus pinning a grammar nobody emits any more proves "
        "agreement with nothing."
    )


# --- what the model's superseded definition carries -------------------------

# `net_cashflow` is written twice, which is why the corpus has twelve accounts
# of eleven columns. The published file carries no values, so these read the same
# model through an export that does.


def test_a_superseded_definition_carries_its_own_number_not_its_successors() -> None:
    """The honesty of the whole mechanism is that the two numbers differ.

    ``net_cashflow@1`` is the cashflow before the shock and ``@2`` is the
    cashflow after it. A value read off the finished frame for ``@1`` would
    be ``@2``'s number under ``@1``'s formula -- correct arithmetic, checked
    against the wrong calculation -- so what makes the retained value worth
    carrying is precisely that it is not the one beside it.
    """
    artifact = _the_corpus_model_with_its_values()

    superseded = _node_of(artifact, "net_cashflow@1")
    live = _node_of(artifact, "net_cashflow@2")

    assert superseded["in_final_schema"] is False
    assert superseded["retained"] is True
    assert superseded["value_sample"] != live["value_sample"]
    assert superseded["trace"][-1]["result"] == superseded["value_sample"]
    # Held to every reading the format defines, the identity one included:
    # a document this producer writes and its own validator refuses is a
    # validator nobody runs twice.
    assert validate_artifact(artifact, deep=True).ok, [
        finding.message for finding in validate_artifact(artifact, deep=True).findings
    ]


def test_a_retained_definition_states_the_type_the_producer_read() -> None:
    """``unknown`` is the permission for a type nothing could be read from."""
    superseded = _node_of(_the_corpus_model_with_its_values(), "net_cashflow@1")

    assert superseded["dtype"] == "f64"
    assert superseded["shape"] == "scalar"


def test_retention_switched_off_writes_the_definition_as_history() -> None:
    """The format's older reading of a superseded node, still available.

    No values, no declaration, and the two type fields back at ``unknown`` --
    the frame holds nothing to read them off, which is the case the format's
    permission to write ``unknown`` was written for.
    """
    artifact = _the_corpus_model_with_its_values(retain=False)

    superseded = _node_of(artifact, "net_cashflow@1")

    assert "retained" not in superseded
    assert superseded["value_sample"] is None
    assert superseded["trace"] is None
    assert (superseded["dtype"], superseded["shape"]) == ("unknown", "unknown")
    assert validate_artifact(artifact).ok


def test_retaining_a_definition_moves_no_digest_the_corpus_publishes() -> None:
    """Enrichment is no part of any node's canonical bytes, and this proves it.

    The same model exported three ways -- with the values and the retention,
    with the values and without it, and the way the corpus itself is written,
    with no values at all -- reaches one set of digests. A reader holding two
    quarters of a model exported under different settings compares them on
    the identities, and this is what says those identities are comparable.
    """
    published = _digests_of(_the_published_corpus())

    assert _digests_of(_the_corpus_model_with_its_values()) == published
    assert _digests_of(_the_corpus_model_with_its_values(retain=False)) == published
    assert (
        _the_corpus_model_with_its_values()["graph_fingerprint"]
        == (_the_published_corpus()["graph_fingerprint"])
    )


def test_the_frame_s_own_retention_lever_moves_no_digest_either() -> None:
    """The corpus model built without retention reaches the published digests.

    The lever that declines the cost is a construction argument, and the
    model above is pinned to the line -- section 12.5 prints its source and
    every node's ``source_location`` counts the lines of this file -- so it
    cannot be parameterised. Standing in front of the constructor for the
    length of the build is what lets the published model be run under the
    other setting without a character of it moving.

    What is being held is that values and identity are separate: a reviewer
    comparing two quarters of one model compares fingerprints, and that
    comparison is worth nothing if a memory setting can move one.
    """
    built = ActuarialFrame.__init__

    def without_retention(
        frame: ActuarialFrame, data: object = None, **kwargs: object
    ) -> None:
        kwargs.setdefault("retain_superseded", False)
        built(frame, data, **kwargs)

    ActuarialFrame.__init__ = without_retention  # type: ignore[method-assign]
    try:
        model = _the_corpus_model()
        assert model._retain_superseded is False  # noqa: SLF001 -- the lever
        artifact = cast(
            "dict[str, Any]",
            json.loads(GraphExporter(model).export(model.collect())),
        )
    finally:
        ActuarialFrame.__init__ = built  # type: ignore[method-assign]

    published = _the_published_corpus()

    assert "retained" not in _node_of(artifact, "net_cashflow@1")
    assert _digests_of(artifact) == _digests_of(published)
    assert artifact["graph_fingerprint"] == published["graph_fingerprint"]


if __name__ == "__main__":
    _write_the_corpus()
