# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Facets: the named, optional blocks an artifact carries beside its base record.

A facet is a place to put something the artifact format does not define,
without changing anything it does. Every facet carries two members --
``_producer``, naming who produced it, and ``_schemaURL``, naming its own
schema -- and both are opaque identifiers a reader must never fetch. The
grammar is the one OpenLineage uses for the same purpose, borrowed rather
than invented: an extension convention with existing readers behind it is
worth more to a second implementer than one designed for this format alone.

The artifact announces its facets twice, and the two lists are what make the
mechanism safe in both directions. ``facets_used`` names every facet present
anywhere in the artifact, so a consumer can see what it is about to meet
without walking the whole document first. ``facets_required`` names the
subset a consumer *must* understand for the artifact to mean what it says:
meeting a name there it does not know, a consumer refuses the artifact rather
than reading a document the producer did not write. Meeting one that is only
in ``facets_used``, it ignores the facet and passes it on unchanged.

:class:`FacetLedger` is where a producer keeps those two lists while it builds
an artifact, so that "announce every facet you emit" is one call at the site
that emits it rather than a second pass that can fall out of step with the
first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "PRODUCER_URI",
    "SCHEMA_URL_TEMPLATE",
    "FacetLedger",
    "facet",
]

# Who produced a facet this package writes. An identifier first: a facet whose
# validity depended on a host still answering would be a facet with an expiry
# date on it, so nothing reads either URI over the network.
#
# It names the edition of the specification the producer wrote the facet
# under, so it moves with the schema identifier: a facet stamped
# `v0-preview.2` inside a document that is `v0-preview.3` throughout would
# have this producer claiming an edition it is not writing.
PRODUCER_URI: Final[str] = "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3"

# Where a facet this package writes says its own schema lives. Every facet
# name this package produces begins ``gaspatchio_``; a third party defining a
# facet uses its own prefix, and a bare name is reserved.
#
# **The counter here is the facet's own and holds still while `PRODUCER_URI`
# moves.** The two strings answer different questions: that one is who wrote
# this facet and under which edition of the specification, this one is where
# the schema for a facet of this name lives. No facet's own shape changed at
# `v0-preview.2` or at `v0-preview.3`, so moving this would point every facet
# at a document that does not exist to say nothing had changed in it.
SCHEMA_URL_TEMPLATE: Final[str] = (
    "https://gaspatchio.dev/schemas/facets/{name}-v0-preview.1.json"
)

# The two members every facet carries, whoever wrote it.
_PRODUCER_KEY: Final[str] = "_producer"
_SCHEMA_URL_KEY: Final[str] = "_schemaURL"


def facet(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``payload`` wrapped as a facet, with its producer and schema URI.

    Args:
        name: The facet's name, as it will appear in the artifact's ``facets``
            object and in both declaration lists.
        payload: What the facet carries. It must not stamp its own
            ``_producer`` or ``_schemaURL``.

    Returns:
        The facet object: the two identity members, then everything
        ``payload`` carries.

    Raises:
        ValueError: If ``payload`` carries either identity member. A payload
            that stamps its own producer is somebody else's facet, and
            restamping it would put this package's name on another party's
            record.

    Examples:
        >>> from gaspatchio.frame.graph.facets import facet
        >>> facet("gaspatchio_lowered", {"engine": "polars"})["engine"]
        'polars'

    """
    stamped = [key for key in (_PRODUCER_KEY, _SCHEMA_URL_KEY) if key in payload]
    if stamped:
        msg = (
            f"The payload for facet {name!r} carries {', '.join(stamped)}, which "
            "identifies who produced the facet and which schema reads it. A "
            "payload that stamps its own is another party's facet, and this "
            "would restamp it as ours. Emit that facet object as it stands "
            "instead of wrapping it."
        )
        raise ValueError(msg)
    return {
        _PRODUCER_KEY: PRODUCER_URI,
        _SCHEMA_URL_KEY: SCHEMA_URL_TEMPLATE.format(name=name),
        **payload,
    }


@dataclass(slots=True)
class FacetLedger:
    """The two declaration lists an artifact carries: used, and required.

    ``used`` is every facet name the artifact carries anywhere -- in the
    envelope and on every node. ``required`` is the subset a consumer must
    understand for the artifact to mean what it says, and it is always a
    subset: anything a consumer has to know about in order to read the base
    record correctly is required, and anything required is announced.

    Examples:
        >>> from gaspatchio.frame.graph.facets import FacetLedger
        >>> ledger = FacetLedger(used=set(), required=set())
        >>> ledger.record("gaspatchio_lowered")
        >>> ledger.as_lists()
        (['gaspatchio_lowered'], [])

    """

    used: set[str]
    required: set[str]

    def record(self, name: str, *, required: bool = False) -> None:
        """Record that the artifact carries facet ``name``.

        Args:
            name: The facet's name.
            required: Whether a consumer must understand the facet for the
                artifact to mean what it says. A facet that changes the
                meaning of a defined field is required; one that only adds
                something beside it is not.
        """
        self.used.add(name)
        if required:
            self.required.add(name)

    def as_lists(self) -> tuple[list[str], list[str]]:
        """Return ``(facets_used, facets_required)``, each sorted by name.

        Sorted so that two runs of one model produce two artifacts a reader
        can diff: a set's iteration order is not a fact about the model.
        """
        return sorted(self.used), sorted(self.required)
