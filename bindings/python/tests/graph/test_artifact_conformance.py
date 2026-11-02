# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every artifact the shipped models produce, read back against the schema.

The specification says what an artifact is. The schema says the same thing in
a form a machine can check. Neither says anything at all about the files this
package actually writes, and a format whose own producer is never held to it
is a document rather than a contract.

So every model the package ships is run here, exported under both conformance
profiles, and each artifact read back with its digests recomputed rather than
taken on trust. Recomputed is fully true of the nine ``executable`` artifacts
only: an ``audit`` one carries no operation trees, so every one of its
``local_fingerprint`` values is read rather than recomputed, and what the deep
reading checks there is the chain between them. The models are the ones an
actuary meets first -- the base model of each tutorial level, and each of the
rollforward patterns. They are deliberately not a corpus written for the
occasion: a corpus is what the producer was built against, and these are what
it produces.

What this catches is the change nobody meant to make. A member renamed, a
value written in a shape the schema does not allow, a node kind that arrives
without the schema learning it -- each of them fails on the run that made it
rather than in somebody's pipeline a quarter later (*Audit by default*).

What it does not catch is a whole pattern family nobody here builds: these are
nine models, and a modelling shape none of them reaches is not exported, not
read back, and not covered until a model that uses it ships in this list.
"""

from __future__ import annotations

import functools
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import polars as pl
import pytest

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, diff_artifacts, validate_artifact
from gaspatchio.frame.graph.artifact import DOCUMENT_DIGEST_FIELD, document_digest_of
from gaspatchio.tutorials import get_tutorials_dir

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from gaspatchio.frame.graph import Finding

# The two conformance profiles, spelled as the exporter's own parameter
# spells them. Written out rather than imported from the producer's
# constants so that a parameter can carry the literal type a caller may
# actually pass; an artifact exported under a name the producer does not
# know is refused at the export, so the two cannot drift silently.
_Profile = Literal["audit", "executable"]
_PROFILES: tuple[_Profile, ...] = ("audit", "executable")

# The models the package ships, as paths under the bundled tutorials
# directory. Every tutorial level ships a `base/model.py` that takes a frame
# and returns one -- including the typed-inputs variant of level 3, which
# reaches the same projection through `MortalityTable`, `Curve` and
# `Schedule` and so gives its own account of itself rather than a copy of
# another model's. Two of the three rollforward patterns take a frame and
# name the model-point file beside them, which is what lets the exporter run
# a compiled state machine at all; the third is still a standalone script
# that builds its own frame, prints what it came to and returns nothing.
#
# The `steps/` trees under each level are teaching increments of the base
# model beside them rather than models in their own right, and the three
# other `patterns/` trees demonstrate aggregation, curves and period
# aggregators rather than a model; neither set is named here.
_SHIPPED_MODELS: tuple[str, ...] = (
    "level-1-hello-world/base",
    "level-2-assumptions/base",
    "level-3-mini-va/base",
    "level-3-mini-va-typed/base",
    "level-4-lifelib/base",
    "level-5-scenarios/base",
    "patterns/rollforward-patterns/01_single_state_fund",
    "patterns/rollforward-patterns/02_multistate_ratchet",
    "patterns/rollforward-patterns/03_lapse_stop",
)

# The one remark a deep read of a shipped export carries, named rather than
# counted. It is structural -- what this producer's own shapes mean under
# this build's readings, rather than anything wrong with a model -- and
# naming it is what makes a second remark of any grade fail this run in its
# own words instead of being absorbed by a count.
#
# There were two until `gaspatchio-graph/v0-preview.2`. The other was the
# seal: the member was optional under the earlier identifier and the exporter
# wrote none, so every export was unsealed and every deep read said so. It
# retired when the emission flipped, exactly as it was written here that it
# would -- every export carries a seal now, the deep read recomputes it, and
# a recomputation that agrees has nothing to remark on.
#
# The leaves: an `audit` artifact carries no operation tree at all, and an
# `executable` one carries none for a leaf, whose identity is its name and
# its type rather than a tree. Neither profile can recompute those, and the
# remark saying so is the reading working rather than a model falling short.
_A_LEAF_CARRIES_NO_TREE: Final[str] = (
    "``local_fingerprint`` read rather than recomputed"
)

# The deep reading's note on a compiled rollforward whose machine the file
# does not carry -- every one, in the audit profile -- so its identity was read
# as published (spec 13). One per compilation, and about the profile, not a fault.
_A_MACHINE_READ_ON_TRUST: Final[str] = "read as published rather than recomputed"

# The model whose artifact the two comparison claims are made about. Big
# enough to be a real projection -- 72 nodes over a full monthly timeline,
# reading a mortality table, an investment-return table and a schedule --
# and small enough to run a second time without anyone noticing.
_A_WHOLE_MODEL = "level-3-mini-va/base"


def _path_of(model: str) -> Path:
    """Return the file one shipped model is written in.

    Two shapes ship: a level, which is a directory holding ``model.py``, and
    a pattern, which is the script itself.
    """
    root = get_tutorials_dir()
    script = root / f"{model}.py"
    return script if script.is_file() else root / model / "model.py"


def _module_of(model: str) -> ModuleType:
    """Import one shipped model from its own file, under its own name.

    The tutorials carry no package markers -- ``gspio tutorial init`` copies
    them verbatim into a user's directory, where one would be wrong -- and
    several of them share the basename ``model.py``. Loading each from its
    path under a name built from that path is what keeps the sixth import
    from resolving to the first.
    """
    path = _path_of(model)
    name = "shipped_model_" + model.replace("/", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        msg = f"No module spec for the shipped model at {path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _frames_collected() -> Iterator[list[ActuarialFrame]]:
    """Record the frame every ``collect()`` inside the block was called on.

    The rollforward patterns are scripts an actuary runs from a shell: they
    build their own frame, print what it came to and return nothing. There is
    no other seam to take the frame at, and ``collect()`` is the one line
    every one of them passes through.
    """
    seen: list[ActuarialFrame] = []
    collect = ActuarialFrame.collect

    def recording(frame: ActuarialFrame, *, engine: str = "streaming") -> pl.DataFrame:
        seen.append(frame)
        return collect(frame, engine=engine)

    ActuarialFrame.collect = recording  # type: ignore[method-assign]
    try:
        yield seen
    finally:
        ActuarialFrame.collect = collect  # type: ignore[method-assign]


def _run_shipped_model(model: str) -> ActuarialFrame:
    """Run one shipped model and return the frame it finished on.

    Four shapes, each named rather than guessed at: a model whose points are
    written inline in the file, a model that names the file they are in, a
    level that reads them from the ``model_points.parquet`` beside it, and a
    pattern script that builds its own frame.

    The second shape is the two rollforward patterns, which name their own
    points because a directory of patterns holds more than one model and a
    file named for none of them would belong to whichever ran first.
    """
    module = _module_of(model)
    points = getattr(module, "MODEL_POINTS", None)
    if isinstance(points, Path):
        named = ActuarialFrame(pl.read_parquet(points))
        return cast("ActuarialFrame", module.main(named))
    if points is not None:
        return cast("ActuarialFrame", module.main(ActuarialFrame(points)))
    model_points = _path_of(model).parent / "model_points.parquet"
    if model_points.is_file():
        frame = ActuarialFrame(pl.read_parquet(model_points))
        return cast("ActuarialFrame", module.main(frame))
    with _frames_collected() as seen:
        module.main()
    if not seen:
        msg = f"The shipped model {model} never collected a frame to export."
        raise AssertionError(msg)
    return seen[-1]


@functools.cache
def _frame_for(model: str) -> ActuarialFrame:
    """Return one shipped model's finished frame, running it once per session.

    Both profiles are exported off this one frame, which is what keeps nine
    models and eighteen artifacts inside a couple of seconds. Nothing here
    hands the frame to a test, so nothing can edit what the next caller gets.
    """
    return _run_shipped_model(model)


@functools.cache
def _exported(model: str, profile: _Profile) -> str:
    """Return the text one shipped model exports under one profile.

    Cached on the text rather than the parsed document, so that a caller who
    edits what it was handed cannot reach the next caller's copy.
    """
    return GraphExporter(_frame_for(model)).export(profile=profile)


def _export_shipped_model(model: str, profile: _Profile) -> dict[str, Any]:
    """Return the artifact one shipped model exports under one profile."""
    return cast("dict[str, Any]", json.loads(_exported(model, profile)))


def _export_again(model: str, profile: _Profile) -> dict[str, Any]:
    """Return a second artifact from a second, independent run of one model.

    Deliberately past both caches: the claim being made is about two runs of
    the model, and handing back the first one twice would prove nothing.
    """
    exported = GraphExporter(_run_shipped_model(model)).export(profile=profile)
    return cast("dict[str, Any]", json.loads(exported))


@pytest.mark.parametrize("model", _SHIPPED_MODELS)
@pytest.mark.parametrize("profile", _PROFILES)
def test_every_shipped_model_exports_a_valid_artifact(
    model: str, profile: _Profile
) -> None:
    """The producer is held to the schema by the files it actually writes.

    ``deep=True`` because the shallow readings check that the document says
    consistent things, and this one checks that what it says about its own
    identity is true -- the digests recomputed from the operation trees the
    ``executable`` profile carries, and the chain between them either way.
    """
    report = validate_artifact(_export_shipped_model(model, profile), deep=True)

    assert report.ok, "\n".join(finding.message for finding in report.findings)


def _remark(finding: Finding) -> str:
    """Return which structural remark a finding is, or its own words if not.

    The words rather than a flag, so that a run failing this pin names the
    finding it met instead of reporting an arithmetic disagreement about how
    many there should have been.
    """
    if _A_LEAF_CARRIES_NO_TREE in finding.message:
        return _A_LEAF_CARRIES_NO_TREE
    if finding.severity == "warning" and _A_MACHINE_READ_ON_TRUST in finding.message:
        return _A_MACHINE_READ_ON_TRUST
    return f"{finding.severity}: {finding.message}"


@pytest.mark.parametrize("model", _SHIPPED_MODELS)
@pytest.mark.parametrize("profile", _PROFILES)
def test_a_shipped_export_is_read_shallow_without_a_single_remark(
    model: str, profile: _Profile
) -> None:
    """No finding of any grade, which ``.ok`` on its own would not say.

    ``.ok`` is error-only, so a reading that grew over-broad and fired a
    warning on every node of every shipped model would leave this run green
    and the producer's own files carrying remarks nobody meant. A false
    positive on a healthy document is the worst failure a validator has, and
    the models here are the ones an actuary is told to copy.
    """
    report = validate_artifact(_export_shipped_model(model, profile))

    assert [_remark(finding) for finding in report.findings] == []


@pytest.mark.parametrize("model", _SHIPPED_MODELS)
@pytest.mark.parametrize("profile", _PROFILES)
def test_a_shipped_export_is_read_deep_with_only_the_one_structural_remark(
    model: str, profile: _Profile
) -> None:
    """The identity layer adds exactly one, and it is about this build.

    Named rather than counted: a second remark fails here in its own words,
    and this one disappearing fails here as well. An audit document of a
    model holding a compiled rollforward also names each compilation whose
    machine it does not carry, once each, because that identity was read
    rather than recomputed (spec 13); the executable profile carries the
    machine and recomputes it, so it has none.
    """
    artifact = _export_shipped_model(model, profile)
    report = validate_artifact(artifact, deep=True)
    compilations = sum(node["kind"] == "rollforward" for node in artifact["nodes"])
    on_trust = compilations if profile == "audit" else 0

    assert [_remark(finding) for finding in report.findings] == [
        _A_LEAF_CARRIES_NO_TREE,
        *[_A_MACHINE_READ_ON_TRUST] * on_trust,
    ]


def test_a_warning_on_a_shipped_export_is_what_this_pin_is_for() -> None:
    """The reading `.ok` cannot give, on the file it would have missed.

    A second edge into a node whose own ``reads`` do not name its source is
    warning-grade by design -- section 9's row-shaping narrowings are still
    settling -- so an over-broad reading firing this shape on a real model
    passes ``.ok`` on every one of them. It does not pass here.

    The document is re-sealed after the edge is added, because a shipped
    export carries a seal and this test edits one. Without that the reading
    would refuse the file for not being what its producer wrote, which is
    true and is about something else -- the edit is the fixture, not the
    finding. A holder that genuinely transforms a document does the same
    thing, and section 13.1's fourth limit is where it is written down.
    """
    artifact = _export_shipped_model(_A_WHOLE_MODEL, "audit")
    accounted_for = dict(artifact["edges"][0])
    accounted_for["source"] = artifact["nodes"][0]["id"]
    artifact = artifact | {"edges": [*artifact["edges"], accounted_for]}
    artifact[DOCUMENT_DIGEST_FIELD] = document_digest_of(artifact)

    report = validate_artifact(artifact, deep=True)

    assert report.ok
    assert [_remark(finding) for finding in report.findings] != [
        _A_LEAF_CARRIES_NO_TREE,
    ]


@pytest.mark.parametrize("model", _SHIPPED_MODELS)
def test_every_shipped_model_can_account_for_every_column_it_holds(model: str) -> None:
    """The empty holes array, from the models an actuary is told to copy.

    A shipped model that could not account for one of its own columns would
    be teaching the bypass as the pattern. The claim is positive: these
    models explain every column they finish holding.
    """
    artifact = _export_shipped_model(model, "audit")

    assert artifact["holes"] == [], (
        f"{model} finishes holding columns nothing accounts for: "
        f"{[hole['column'] for hole in artifact['holes']]}"
    )


@pytest.mark.parametrize("model", _SHIPPED_MODELS)
def test_every_shipped_model_indexes_its_narrowings_by_the_reads_they_narrow(
    model: str,
) -> None:
    """The reading node's own ``reads`` is the key into its narrowing facet.

    Section 9 writes one edge per entry of the target's ``reads``, in that
    order, and the facet carries one entry per edge. Two orders would leave
    a consumer pairing the wrong narrowing with the wrong read and nothing
    in the document to say it had. Checked on every model an actuary is
    told to copy, because a single hand-written formula proves it for one
    shape of tree and these are every shape the package ships.
    """
    artifact = _export_shipped_model(model, "audit")
    facet = "gaspatchio_column_transformation"

    narrowed = {
        node["id"]: [read["source"] for read in node["facets"][facet]["reads"]]
        for node in artifact["nodes"]
        if facet in node["facets"]
    }
    reading = {node["id"]: node["reads"] for node in artifact["nodes"] if node["reads"]}

    assert narrowed == reading
    assert sorted((e["source"], e["target"]) for e in artifact["edges"]) == sorted(
        (source, target) for target, sources in narrowed.items() for source in sources
    )


def test_an_artifact_a_model_produced_diffs_against_itself_as_no_change() -> None:
    """The floor under every comparison: one document has not moved."""
    artifact = _export_shipped_model(_A_WHOLE_MODEL, "audit")

    assert diff_artifacts(artifact, artifact).drift is False


def test_two_exports_of_one_shipped_model_are_not_a_change() -> None:
    """A condition of releasing the format, on a whole model rather than a fixture.

    Two runs of an untouched model produce two documents that differ -- they
    were written at different moments and say so. Anything a reader could
    call drift here would make the report unusable for the question it
    exists to answer, so the timestamp is moved on purpose rather than left
    to whether the two runs landed in the same second.
    """
    before = _export_shipped_model(_A_WHOLE_MODEL, "audit")
    after = _export_again(_A_WHOLE_MODEL, "audit")
    after["created_at"] = "2027-01-01T00:00:00Z"

    report = diff_artifacts(before, after)

    assert (report.drift, report.calculations, report.data) == (False, (), ())


def test_the_run_names_every_tutorial_level_the_package_ships() -> None:
    """A level added later joins this run rather than quietly missing it."""
    root = get_tutorials_dir()
    ships = sorted(
        path.parent.relative_to(root).as_posix()
        for path in root.glob("*/base/model.py")
    )

    assert ships == sorted(
        model for model in _SHIPPED_MODELS if model.endswith("/base")
    )


def test_the_run_names_every_rollforward_pattern_the_package_ships() -> None:
    """A fourth pattern joins this run rather than quietly missing it."""
    root = get_tutorials_dir()
    patterns = root / "patterns" / "rollforward-patterns"
    ships = sorted(
        path.relative_to(root).with_suffix("").as_posix()
        for path in patterns.glob("[0-9]*.py")
    )

    assert ships == sorted(
        model for model in _SHIPPED_MODELS if "rollforward-patterns" in model
    )
