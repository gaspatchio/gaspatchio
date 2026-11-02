# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One run's refusals, grouped by the moment each of them could be known.

An engine that stops on the first thing it cannot do sends the reader back
round the loop once per problem. This module is the other shape: every
finding travels in one report, grouped into the three moments a finding can
be reached in, and each one names the actuarial thing, where it is, how many
rows it is about, the next move, and the clause of the specification it rests
on.

The three groups are not severities. They are when the answer was available:

- ``tree`` -- from the document and its payloads alone, before any book was
  read. An identifier this engine has no lowering for, a state graph, a
  compilation outside the admitted subset.
- ``inputs`` -- from the book, before anything was compiled. A missing or
  mistyped column, a null in a column something reads as a value, an
  integer outside the range its type carries.
- ``completion`` -- from flags the run itself carried: a lookup that missed
  on a computed key, a balance that stopped being finite. The run finishes
  so the flags can be read, and nothing is published.

Which groups a report carries decides its closing sentence, and the sentence
is the claim the reader actually needs: a refusal from the first two groups
means nothing ran, and one from the third means something ran and none of it
was published. Those are different facts about the file system and about the
clock, and a report that blurred them would be making the reader guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Literal

from ._versions import versions_in_this_process

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "EngineRefusal",
    "Group",
    "Refusal",
    "RunReport",
    "RunSummary",
]

Group = Literal["tree", "inputs", "completion"]

# The order the groups are printed in, which is the order they become
# knowable in. A reader works down the report the way the run worked down
# the model.
_GROUP_ORDER: tuple[Group, ...] = ("tree", "inputs", "completion")

# What each group is, in the framework's voice. The heading says which
# moment the findings under it were reached at, because "before the book was
# read" and "after the run finished" are what tell the reader whether the
# next attempt costs them a file or a run.
_HEADINGS: dict[Group, str] = {
    "tree": "From the model's tree and its payloads, before any book was read:",
    "inputs": "From the book, before anything was compiled:",
    "completion": "At completion, with every output withheld:",
}

_NOTES_HEADING = "Reported, not refused:"

# The two closing sentences. Nothing else may be said here: a report that
# invented a third claim would be a third thing to keep true.
_NOTHING_RAN = "Nothing was computed."
_NOTHING_PUBLISHED = "No results were published."

# What separates a refusal's fields on one line. A middle dot rather than a
# comma, because every field is a sentence or an identifier and several of
# them carry commas of their own.
_FIELD = " · "


@dataclass(frozen=True, slots=True)
class Refusal:
    """One thing the engine will not do, and what to do about it.

    Attributes:
        group: The moment this was knowable in -- see the module docstring.
        where: What the finding is about, named the way the reader would name
            it: a node id, a column name, a table name -- and, where the
            finding is about the run itself rather than about anything in the
            model, the engine's own name. A completion refusal for a run that
            published nothing is about the engine, and there is no column to
            put here that would not be a guess.
        count: Rows, cells or keys, where a count exists and means something.
        what: The actuarial thing, in one sentence.
        move: The next move, in one sentence.
        clause: The section of the specification the refusal rests on, such
            as ``"11.1.24"``, or None where no section states the rule -- a
            fold into aggregates, which the specification leaves outside the
            artifact. Never an internal reference a reader has nowhere to
            look up.

    """

    group: Group
    where: str
    count: int | None
    what: str
    move: str
    clause: str | None

    def line(self) -> str:
        """Return this refusal as the one line a report prints for it.

        A field with no value contributes no separator. A count of ``None``
        is not "no rows" -- it is a finding a count would say nothing about,
        such as an identifier the engine has no lowering for -- and printing
        an empty slot for it would invite the reader to wonder what it meant.
        """
        parts: list[str] = [self.where]
        if self.count is not None:
            parts.append(str(self.count))
        parts.extend((self.what, self.move))
        if self.clause is not None:
            parts.append(self.clause)
        return _FIELD.join(parts)

    def to_dict(self) -> dict[str, object]:
        """Return this refusal as JSON carries it."""
        return {
            "group": self.group,
            "where": self.where,
            "count": self.count,
            "what": self.what,
            "move": self.move,
            "clause": self.clause,
        }


@dataclass(frozen=True, slots=True)
class RunReport:
    """Everything one run has to say, refused and merely reported apart.

    Attributes:
        refusals: Every finding that stops the run, in whatever order they
            were appended; the rendering groups them.
        notes: What the run wants the reader to know and does not stop for --
            a table that fell back to the sparse path, a compile cache miss.

    """

    refusals: tuple[Refusal, ...]
    notes: tuple[str, ...] = ()

    def refused(self) -> bool:
        """Return whether anything here stops the run."""
        return bool(self.refusals)

    def closing_sentence(self) -> str:
        """Return the one claim the reader needs about what happened.

        A completion refusal means the run reached the end and every output
        was withheld, which is a different fact from a run that never
        started -- different in cost, and different in what is on disk.

        **A report with no refusals has nothing to close, and says nothing.**
        Both sentences are claims about a run that stopped, and a run that
        merely had something to *say* -- a table on the fallback path, a
        column of nulls nothing read -- finished and published. Printing
        "Nothing was computed." under a note would be the report contradicting
        the values the caller is holding, and the two sentences stay the only
        two rather than a third being invented for the case.
        """
        if not self.refusals:
            return ""
        completion = any(one.group == "completion" for one in self.refusals)
        return _NOTHING_PUBLISHED if completion else _NOTHING_RAN

    def render(self) -> str:
        """Return the whole report, grouped, in the framework's voice."""
        blocks: list[str] = []
        for group in _GROUP_ORDER:
            found = [one for one in self.refusals if one.group == group]
            if not found:
                continue
            lines = "\n".join(f"  {one.line()}" for one in found)
            blocks.append(f"{_HEADINGS[group]}\n{lines}")
        if self.notes:
            noted = "\n".join(f"  {note}" for note in self.notes)
            blocks.append(f"{_NOTES_HEADING}\n{noted}")
        closing = self.closing_sentence()
        if closing:
            blocks.append(closing)
        return "\n\n".join(blocks)

    def to_dict(self) -> dict[str, object]:
        """Return the report as JSON carries it, closing sentence included."""
        return {
            "refusals": [one.to_dict() for one in self.refusals],
            "notes": list(self.notes),
            "closing_sentence": self.closing_sentence(),
        }


@dataclass(frozen=True, slots=True)
class RunSummary:
    """The last successful collection of the frame's current plan.

    Read through ``af.graph.last_run``. This carries no values or new lineage;
    the frame's calculation log and completed snapshot remain their owners.
    ``polars_mode`` names the requested Polars execution strategy, or None
    for profiling and discovered engines. ``profiled`` distinguishes the
    profiling route without guessing which strategy Polars used internally.
    ``report`` preserves the engine's own findings, including successful notes.
    :attr:`versions` names what produced the values.
    """

    engine: str
    polars_mode: str | None
    profiled: bool
    rows: int
    columns: int
    report: RunReport
    # What produced the values, where that is stated rather than read off
    # this process: a second engine's own result manifest, handed in by
    # ``_stating``, or a Polars run's own versions, taken as the summary is
    # pickled. None on a Polars run that has not been, whose versions are
    # this process's and are read only when asked for (see ``versions``).
    # Sorted items, so the summary stays a value that hashes. Out of the
    # constructor, because what produced a run is the run's to state and not
    # a caller's; and out of equality and hashing, so a summary pickled and
    # restored is the summary it was.
    _stated: tuple[tuple[str, str], ...] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def versions(self) -> dict[str, str]:
        """Which library versions produced these values.

        Same model, same data: would the library this ran on give the same
        answer again? The model is ``af.graph.fingerprint()`` and the data is
        the book; this is the third part of the question, and a result that
        cannot name what produced it cannot be compared with one from another
        day. For a model that rebuilds its frame from bare values in setup, as
        the three-phase template teaches, the fingerprint the commands state
        is not ``af.graph.fingerprint()`` -- they are told the model points
        file's columns and state the rebuilt ones as holes -- and building the
        frame with ``ActuarialFrame(df, continue_from=af)`` keeps the two one
        model.

        A run on Polars states this process's versions: the core package's
        version as installed, the version compiled into the extension it
        loaded -- two numbers that agree in a release wheel and can differ in
        any other install, so each is stated as it is -- the Polars version,
        the platform, Python, and the digest of that extension, or, where the
        file on disk changed after the process loaded it, a statement that it
        did, beginning ``unavailable:``. It is the mapping a result manifest
        written by the same process carries. A run on a second engine states
        what that engine's own result manifest says produced it. The mapping
        is read when it is asked for and never during the collect, every read
        hands back a mapping of the caller's own, and a summary pickled here
        carries it.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame(pl.DataFrame({"premium": [1200.0, 900.0]}))
            >>> af.commission = af.premium * 0.05
            >>> _ = af.collect()
            >>> af.graph.last_run.versions["polars_version"] == pl.__version__
            True

        """
        if self._stated is not None:
            return dict(self._stated)
        return versions_in_this_process()

    def __getstate__(self) -> list[object]:
        """Return the state a pickle carries, with the versions taken first.

        A summary restored in another process -- a worker's, or a notebook's
        a day later -- has to state what produced its values, not what the
        restoring process runs on. So a Polars run's versions are read here,
        in the process that ran it, and travel as stated ones.
        """
        taken = tuple(sorted(self.versions.items()))
        return [
            taken if one.name == "_stated" else getattr(self, one.name)
            for one in fields(self)
        ]


def _stating(summary: RunSummary, versions: Mapping[str, str]) -> RunSummary:
    """Return ``summary`` stating ``versions`` as what produced its values.

    The frame's engine door uses this for a run on a second engine, whose own
    result manifest names what produced the values. It writes the one field
    the constructor does not take, on a summary nobody else holds yet.
    """
    object.__setattr__(summary, "_stated", tuple(sorted(versions.items())))
    return summary


# ``EngineRefusal`` rather than a name ending in Error: a refusal is this
# framework's own word for a run it will not do, it is what the report calls
# itself, and ``EngineRefusalError`` would say the same thing twice.
class EngineRefusal(RuntimeError):  # noqa: N818 -- named above
    """The one exception class: its message is :meth:`RunReport.render`.

    One class rather than one per group, because the report already says
    which group each finding belongs to and a caller branching on the type
    would be branching on something the message states better. The frame
    door raises it; the commands catch it, print the report and exit.
    """

    report: RunReport

    def __init__(self, report: RunReport) -> None:
        """Carry the report, and say it as the exception's own message."""
        super().__init__(report.render())
        self.report = report
