# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Audit sidecar JSON writer/reader + schema for ScenarioRun outputs.
# ABOUTME: Completes the source_sha governance story; opt-in via audit param.

"""The audit record a scenario run or an aggregated run writes beside its output.

A single JSON file co-located with run output, containing:
    schema_version, source_sha, plan_canonical_form, run_metadata,
    aggregator_outputs, aggregator_identity, graph_fingerprint,
    input_data_fingerprint.

Two runs write this record -- a scenario run over the scenario axis and a
plain aggregation over the policy axis -- through one writer, so that an
auditor holding either meets the same document.

The record and the calculation graph are two documents, linked rather than
merged: this one carries the real numbers and what the run cost, which the
graph artifact deliberately never carries, and it names the graph it folded
(``graph_fingerprint``) and the data it read (``input_data_fingerprint``).
Read from either end, the chain closes -- a reported total, the fold that
produced it, the calculation that fold ran, the formula behind it.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import numpy as np
import polars as pl

from gaspatchio._dtypes import UnmappedDtypeError, neutral_dtype
from gaspatchio.engines._versions import versions_in_this_process

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping

# 2.1 adds ``graph_fingerprint``, ``graph_fingerprint_by_scenario`` and
# ``aggregator_identity``, and fills ``input_data_fingerprint``. The bump is
# not additive: 2.1 removes ``run_metadata.library_version``, which 0.9.0's
# 2.0 record wrote, and states the library by the six keys a results file's
# manifest states (``library_versions`` below), of which ``polars_version``
# and ``python_version`` were already written. A reader built against 2.0
# that reads ``library_version`` finds nothing there; section 13.2 of the
# specification sets out every difference.
#
# The per-scenario map arrived after the other three and extends 2.1 rather
# than minting 2.2, because 2.1 has not been released: it names the same
# thing 2.1 already set out to name -- the calculation the run folded -- one
# scenario at a time, and two version numbers for one unreleased shape would
# leave a reader asking which is canonical.
#
# 2.1 also carries ``bases``: per table a scenario shock moved, the content it
# was applied to and the file it came from. A plan no longer hands the model
# its tables -- the model reads its own and the plan shocks those reads -- so
# the plan's own canonical form cannot say which rates a shock moved, and the
# run says it instead. ``base_tables`` in the plan became optional in the same
# change. Both ride in 2.1 for the reason the per-scenario map does: 2.1 is
# unreleased, and the shape it names is still the calculation the run folded.
#
# 2.1 also settles what ``input_data_fingerprint`` says when it cannot say
# everything. Its ``model_points`` value is a content digest where the stamp
# covers the whole book, and an object carrying the digest together with the
# columns it could not cover wherever it does not -- so a partial claim is
# never reachable in the shape a whole one arrives in. That is a change to
# the shape of a value rather than one more field beside it, which is
# exactly what an unreleased version number is free to make: nobody holds a
# 2.1 record written the earlier way, so there is no reader to break and
# nothing to bump.
AUDIT_SCHEMA_VERSION = "2.1"


def write_audit(  # noqa: PLR0913
    path: Path,
    *,
    source_sha: str,
    plan_canonical_form: dict[str, Any],
    run_metadata: dict[str, Any],
    aggregator_outputs: dict[str, Any],
    aggregator_identity: dict[str, Any],
    graph_fingerprint: str | None,
    graph_fingerprint_by_scenario: dict[str, str | None] | None,
    input_data_fingerprint: dict[str, Any],
    bases: dict[str, dict[str, Any]] | None = None,
    named_by_the_run: bool = False,
) -> None:
    """Write the audit JSON sidecar to ``path``.

    Args:
        path: Where the record goes.
        source_sha: The identity of the recipe the run folded.
        plan_canonical_form: That recipe, written out.
        run_metadata: What the run cost and what it ran under.
        aggregator_outputs: The numbers, one per alias.
        aggregator_identity: What each of those numbers *is* -- the alias's
            own canonical form, naming the kind of fold and the column it
            folded. It sits beside the outputs rather than only inside
            ``plan_canonical_form`` so that a reader asking "what is this
            number?" is answered where the number is, without walking a
            second structure.
        graph_fingerprint: The calculation the run folded, or None where the
            run folded more than one and no single stamp is true of it.
        graph_fingerprint_by_scenario: The calculation each scenario folded,
            keyed by that scenario's own name -- the one a shocked run
            really has, since every scenario reads its own assumption
            bases. None where the run had no scenario axis to key it by,
            which is every run on the policy axis.
        input_data_fingerprint: A content stamp per input the run read,
            keyed the way the graph artifact keys them (``model_points``).
            A stamp is a digest where it covers the whole input, and an
            object carrying the digest it could take beside the columns it
            could not -- each by name and type -- where the content grammar
            has no name for one of them.
        bases: Per table a scenario shock moved, keyed by the table's own
            name: the content fingerprint of the table the model read --
            the one the shock was applied to -- and the file it was read
            from (``source_file``, relative, or null for a table built in
            memory). None where nothing was shocked: an ids or drivers run,
            or a run on the policy axis.
        named_by_the_run: The path is the default one, named by the run's
            id rather than by the caller. Two runs of one plan in one second
            share that id, so a record already under the name is another
            run's evidence, and it is refused rather than written over. A
            path the caller named is theirs to replace.

    Raises:
        FileExistsError: If ``named_by_the_run`` and a record is already
            under that name. Nothing is written.

    """
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "source_sha": source_sha,
        "plan_canonical_form": plan_canonical_form,
        "run_metadata": run_metadata,
        "aggregator_outputs": _coerce_outputs_to_json(aggregator_outputs),
        "aggregator_identity": aggregator_identity,
        "graph_fingerprint": graph_fingerprint,
        "graph_fingerprint_by_scenario": graph_fingerprint_by_scenario,
        "input_data_fingerprint": input_data_fingerprint,
        "bases": bases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the destination and renamed into place, so a reader never
    # finds half a record under its name: a run that dies mid-write leaves
    # either the previous record or none. The uuid keeps two runs writing one
    # path from writing over each other's working.
    unpublished = path.with_name(f"{path.name}.{uuid.uuid4().hex}.unpublished")
    try:
        unpublished.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
        )
        if not named_by_the_run:
            unpublished.replace(path)
            return
        # A link is published whole, as a rename is, and refuses a name that
        # is taken, which a rename does not: no window between a check and
        # the write in which a second run could land.
        try:
            path.hardlink_to(unpublished)
        except FileExistsError:
            raise FileExistsError(_a_record_already_there(path)) from None
        except OSError:
            # A file system with no hard links: the check and the rename are
            # two steps there, which still never writes over a record found.
            if path.exists():
                raise FileExistsError(_a_record_already_there(path)) from None
            unpublished.replace(path)
    finally:
        unpublished.unlink(missing_ok=True)


def _a_record_already_there(path: Path) -> str:
    """Say why a run record named by the run's id was not written."""
    return (
        f"The run record would be written to {path}, and a record is already "
        "there: the default name is the run's id -- the time to the second and "
        "the plan's sha -- so two runs of one plan in one second share it, and "
        "the record there is an earlier run's evidence. Nothing was written "
        "over it, and this run's record was not written. Name the record "
        "yourself, one path per run: audit=Path('...')."
    )


def read_audit(path: Path) -> dict[str, Any]:
    """Read the audit JSON sidecar.

    Raises:
        ValueError: If the file's JSON is not an object, which every audit
            sidecar is.

    """
    audit = json.loads(path.read_text())
    if isinstance(audit, dict):
        return audit
    msg = (
        f"{path} does not hold a scenario audit: its JSON is "
        f"{_json_value_name(audit)}, not an object"
    )
    raise ValueError(msg)


def _json_value_name(value: object) -> str:
    """Name a parsed JSON value the way the JSON file wrote it."""
    # bool before the numbers: True and False are ints to Python.
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    return "null"


def as_path(value: str | os.PathLike[str] | None) -> Path | None:
    """Return a location the caller named as a ``Path``, or None where they named none.

    A string is how most people write a path and ``os.PathLike`` is how the
    rest of Python hands one over; each names a place on disk as a ``Path``
    does. Made a ``Path`` where it comes in, so nothing past the boundary has
    to ask which it was given.
    """
    return None if value is None else Path(value)


def audit_destination(audit: bool | str | os.PathLike[str]) -> bool | Path:  # noqa: FBT001 — the flag-or-path the public ``audit=`` takes
    """Return what ``audit=`` asks for: no record, the default place, or this path.

    ``False`` and ``True`` keep their meaning. Anything else is a path, in
    whichever spelling: a string is not a truthy flag that sends the record
    to the default location while the caller looks for it where they said.
    """
    if isinstance(audit, bool):
        return audit
    return Path(audit)


def default_audit_path(source_sha: str, sink_dir: Path | None) -> Path:
    """Return where a sidecar goes when the caller named no path.

    ``<sink_dir>/<run_id>.audit.json`` where the run has an output directory,
    and ``./gaspatchio_audit/<run_id>.audit.json`` where it has none.
    ``run_id`` is ``<utc-iso-timestamp>_<short-sha>``, filename-safe, so two
    runs of one plan on one day sort into the order they were taken.

    Both runs that write the record derive the name here rather than each
    spelling it out, so an auditor meets one naming convention whichever axis
    was folded.
    """
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    short = source_sha.split(":", 1)[-1][:8]
    directory = sink_dir if sink_dir is not None else Path("./gaspatchio_audit")
    return directory / f"{timestamp}_{short}.audit.json"


def graph_fingerprint_map(
    by_scenario: Mapping[str | int, str | None] | None,
) -> dict[str, str | None] | None:
    """Return the per-scenario graph map in the shape a record carries it.

    JSON has string keys and nothing else, so a scenario named by a number
    is written under that number's own name rather than silently dropped or
    left to a serialiser's default. Both runs that write the record come
    through here -- the policy axis with ``None``, because a run with no
    scenario axis has no scenario to key a map by -- so the two cannot
    drift into two shapes for one idea.
    """
    if by_scenario is None:
        return None
    return {str(scenario_id): stamp for scenario_id, stamp in by_scenario.items()}


def model_points_fingerprint(model_points: pl.DataFrame) -> dict[str, Any]:
    """Return the content stamp of the policy data a run read.

    ``content_sha_of`` is the framework's one content-identity primitive and
    the one the calculation graph takes over a frame held in memory -- the
    specification's own byte grammar rather than any engine's serialisation
    -- so the record and the artifact stamp the same bytes the same way.
    The key is ``model_points``, the name the artifact's own version block
    gives the same thing, so a reader moving between the two documents meets
    one word for one idea.

    **It is not the artifact's file stamp, and cannot be.** Where a model was
    run from a file on disk, the artifact's version block hashes that file's
    bytes; a run handed a frame has no file to hash, and a digest over a
    re-write would move on a writer upgrade with no data behind the movement.
    So this is the in-memory reading of the same grammar: two stamps of one
    frame agree, a stamp of a frame and a stamp of the file it was read from
    do not, and neither is a re-derivation of the other.

    The frame is hashed exactly as the run read it -- those columns in that
    order, those rows in that order, no projection and no re-sort -- because
    the row order is what the batching cut the run into, and a stamp that
    tidied it first would answer a question about a tidied frame nobody ran.

    **The stamp covers the columns the grammar can name, and says which it
    could not.** An ordinary in-force extract carries columns this grammar
    has no name for -- a product code the warehouse dictionary-encoded as a
    category, a rider struct, a column holding nothing but nulls -- and a
    single one of them used to take the whole book's answer away, without
    saying which column did it. The stamp is now taken over the rest, and
    the columns left out are written down beside it, each by name and by
    the type the engine gave it.

    **The digest and that list are one value.** ``model_points`` is a digest
    string only where the stamp covers the whole book, and an object --
    ``content_sha`` beside ``columns_not_stamped`` -- wherever a column was
    left out. A partial stamp is a weaker claim than a whole one, so it is
    not reachable in the shape a whole one arrives in: a reader who found a
    digest string has one over every column the run read, and a reader who
    found an object necessarily has the list of what it does not cover.

    ``content_sha`` is ``None`` where no column could be stamped at all,
    with every column named in the list. A run that asked to be described
    must not be able to die trying: the record says nothing about the data
    rather than the run saying nothing at all.

    **An unsigned column is judged by its values, not by its width.** Where
    they all fit a signed 64-bit integer the column is stamped as the
    ``.cast(pl.Int64)`` its author could have written -- the same digest, to
    the byte -- because that is the name the calculation graph already gives
    the same column, and one column with two answers in one run is worse
    than either answer alone. A value past the signed maximum has no exact
    name left, so that column joins the list instead.
    """
    from gaspatchio._identity import content_sha_of  # noqa: PLC0415 - import cycle

    signed: list[pl.Series] = []
    left_out: list[dict[str, str]] = []
    for name in model_points.columns:
        column = model_points.get_column(name)
        try:
            as_signed = _stampable_as(column, name)
        except UnmappedDtypeError:
            left_out.append({"column": name, "dtype": str(column.dtype)})
        else:
            if as_signed is not None:
                signed.append(as_signed)

    # The book itself wherever nothing had to move, so the ordinary run's
    # digest is the one it has always been rather than one of a rebuilt
    # frame that happens to agree.
    stamped = model_points.with_columns(signed) if signed else model_points
    if not left_out:
        return {"model_points": content_sha_of(stamped)}
    stamped = stamped.drop(skipped["column"] for skipped in left_out)
    return {
        "model_points": {
            "content_sha": content_sha_of(stamped) if stamped.width else None,
            "columns_not_stamped": left_out,
        }
    }


def _stampable_as(column: pl.Series, name: str) -> pl.Series | None:
    """Return the signed form the grammar hashes this column in, if it needs one.

    ``None`` is the ordinary answer, and means the grammar takes the column
    exactly as the run read it: nothing is rewritten and the bytes are the
    ones this book has always produced. A column comes back rewritten only
    where the grammar refuses its storage width unasked and its values fit
    the signed width anyway.

    That judgement is not made here. It is the same function the exporter
    calls, asked twice -- once holding the column's values and once not --
    and the difference between the two answers *is* the rule: what the
    grammar will not name on sight, and what it will name once somebody has
    read the numbers.

    Args:
        column: The column as the run read it.
        name: Its name, so a refusal can say which column it was about.

    Returns:
        The column cast to the signed width the measurement approved, or
        None where the grammar hashes it as held.

    Raises:
        UnmappedDtypeError: The grammar cannot name this column at all --
            a type it has no name for, or a number no signed 64-bit
            integer carries.

    """
    from gaspatchio._identity import (  # noqa: PLC0415 - import cycle
        _without_fixed_width,
    )

    # A fixed-width array is hashed as the list it already is, so the
    # measurement is put to the type the grammar will actually meet.
    carried = _without_fixed_width(column)
    neutral_dtype(carried.dtype, column=name, values=carried)
    try:
        neutral_dtype(carried.dtype, column=name)
    except UnmappedDtypeError:
        return column.cast(_signed_sixty_four(carried.dtype))
    return None


def _signed_sixty_four(dtype: pl.DataType) -> pl.DataType:
    """Return ``dtype`` with every integer inside it as a signed 64-bit one.

    Reached only for a column whose width the grammar refuses on sight and
    whose values have just been measured to fit, so the rewrite says what
    the author's own ``.cast(pl.Int64)`` would say and produces the same
    bytes. Lists recurse, because the numbers are kept inside them rather
    than being one of them; a fixed-width array cannot arrive here, the
    caller having already carried it as the list the grammar hashes it as.
    """
    inner = getattr(dtype, "inner", None)
    if inner is not None and dtype.base_type() is pl.List:
        return pl.List(_signed_sixty_four(inner))
    return pl.Int64() if dtype.is_integer() else dtype


# What a run's record states about the library that produced its numbers:
# the versions as this process has them, the default; or section 6.1's
# withheld form, for a record committed as a golden. The names are the ones a
# calculation-graph export takes for ``producer.versions``, so one word means
# one thing on both of a run's records.
VERSIONS_RECORDED: Final[str] = "recorded"
VERSIONS_WITHHELD: Final[str] = "withheld"
_WITHHELD: Final[dict[str, str]] = {"omitted": VERSIONS_WITHHELD}


def checked_versions(versions: object) -> None:
    """Refuse a ``versions=`` that is neither setting, before a run starts.

    Asked at the door rather than when the record is written, so a misspelt
    setting costs nothing: a scenario run can take minutes, and a refusal at
    the end of one would throw them away.

    Raises:
        ValueError: Where ``versions`` is neither ``"recorded"`` nor
            ``"withheld"``.

    """
    if versions in (VERSIONS_RECORDED, VERSIONS_WITHHELD):
        return
    msg = (
        f"versions={versions!r} is not a setting. 'recorded' states the "
        "library versions the run ran under; 'withheld' records them as "
        "withheld, for a record committed as a golden."
    )
    raise ValueError(msg)


def library_versions(
    versions: Literal["recorded", "withheld"] = "recorded",
) -> dict[str, Any]:
    """Return the versions of everything the run's numbers passed through.

    A quantile that moved between two quarters moved either because the book
    did or because the sketch underneath it did, and the second is only
    answerable if the version is written down beside the number.

    The six keys a results file's manifest and a calculation-graph document's
    ``producer.versions`` state -- the core's version and its compiled
    extension's, the extension's sha256, Polars, Python and the platform --
    spelled as they spell them, so the sidecar and the document of one run
    can be held against each other key for key. ``ddsketch_version`` beside
    them reports ``"unavailable"`` where it is not installed, which is the
    honest answer for a run that used no sketch-backed aggregator.

    **Withheld**, every one of those keys is still written and each says
    ``{"omitted": "withheld"}``: section 6.1's form, the one a document's
    ``producer.versions`` takes, so the record says a decision was taken
    rather than going silent. It is for a record committed as a golden,
    whose strings must not move with the machine that wrote it -- a platform
    string and an extension digest name one desk's build -- and it is never
    the default.

    Args:
        versions: ``"recorded"``, the default, states what this process
            runs under; ``"withheld"`` writes the withheld form under every
            key.

    Returns:
        The keys, each with its version or the withheld form.

    Raises:
        ValueError: Where ``versions`` is neither setting.

    """
    checked_versions(versions)
    try:
        import ddsketch  # noqa: PLC0415 - optional, and its absence is an answer

        ddsketch_version = str(getattr(ddsketch, "__version__", "unknown"))
    except ImportError:
        ddsketch_version = "unavailable"

    stated: dict[str, Any] = {
        **versions_in_this_process(),
        "ddsketch_version": ddsketch_version,
    }
    if versions == VERSIONS_WITHHELD:
        return {key: dict(_WITHHELD) for key in stated}
    return stated


NON_FINITE_SENTINELS: dict[str, str] = {
    "nan": "NaN",
    "inf": "Infinity",
    "-inf": "-Infinity",
}
"""The artifact specification's §10 spelling of a non-finite ``f64``.

A non-finite float travels as a string naming itself. JSON has no token for
one: the bare ``NaN`` a lenient writer emits is not in the grammar, so a
strict parser refuses the whole document rather than the one value -- a file
that reads as valid until somebody parses it. Null cannot stand in, because
null already means *no value here* and a NaN is a value the fold produced.

Keyed by ``repr`` of the float so the three cases are looked up rather than
branched through, and so the spelling sits in one place beside the words it
has to match.
"""


def _non_finite_sentinel(value: float) -> str:
    """Return the §10 string a non-finite float travels as."""
    return NON_FINITE_SENTINELS[repr(value)]


def _coerce_outputs_to_json(outputs: dict[str, Any]) -> dict[str, Any]:
    """Convert aggregator outputs to JSON-reloadable values (recursing containers).

    Handles numpy ndarrays (Period* vectors -> lists), dict-of-ndarray
    (PeriodQuantile -> ``{level: list}``), numpy scalars, and ``pl.DataFrame``
    (partitioned outputs -> list of row dicts). Without this, ndarray outputs fall
    through to ``json``'s ``default=str`` and are written as non-reloadable repr
    strings (with numpy ``...`` truncation for large arrays).

    **A non-finite result is written as §10's string sentinel, not as a bare
    word.** A fold over a column holding a NaN answers NaN, and ``json.dumps``
    writes that as the token ``NaN``, which no strict reader accepts -- so the
    one number that most needs reading is the one that took the whole record
    down with it. The numpy and frame conversions recurse rather than return,
    because a NaN inside a period vector or a partitioned frame is the same
    defect one container deeper.

    The record is written this way and not read back that way: the sidecar's
    outputs carry no declared type beside them, and ``ArgMin``/``ArgMax``
    answer a scenario's own name, so a reader turning every ``"NaN"`` back
    into a float would be guessing at a scenario that happens to be called
    one. §10's rule disambiguates by the column's ``dtype``; here the writer
    is the half that is owed.
    """

    def _to_jsonable(val: Any) -> Any:  # noqa: ANN401
        # An engine's own container first becomes a plain Python one, and is
        # then walked like any other -- so a NaN inside a period vector or a
        # partitioned frame meets the same rule as one standing on its own.
        if isinstance(val, pl.DataFrame):
            val = val.to_dicts()
        elif isinstance(val, np.ndarray):
            val = val.tolist()
        elif isinstance(val, np.generic):  # numpy scalar (np.float64, ...)
            val = val.item()
        if isinstance(val, dict):
            return {k: _to_jsonable(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_to_jsonable(x) for x in val]
        if isinstance(val, float) and not math.isfinite(val):
            return _non_finite_sentinel(val)
        return val

    return {name: _to_jsonable(val) for name, val in outputs.items()}


def _json_default(obj: Any) -> Any:  # noqa: ANN401
    """Fallback serialiser for non-standard types (Path, tuples-as-keys, etc.)."""
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "VERSIONS_RECORDED",
    "VERSIONS_WITHHELD",
    "as_path",
    "audit_destination",
    "checked_versions",
    "default_audit_path",
    "graph_fingerprint_map",
    "library_versions",
    "model_points_fingerprint",
    "read_audit",
    "write_audit",
]
