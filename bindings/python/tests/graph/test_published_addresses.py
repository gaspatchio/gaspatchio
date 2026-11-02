# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every address an artifact names is published from a file in this repository.

An artifact names the specification it was written under in every facet's
``_producer``, the section that says what closes a hole in every hole's
``closes_with``, and each facet's own schema in its ``_schemaURL``. None has
to answer for the artifact to be valid, and each is published at its address
all the same, from the repository's tree as it stands:
``spec/graph-artifact/README.md`` states which file answers each address.

These hold the three together. Every address the producer writes, and every
one the shipped code and schemas name, is a row of that table; every row names
a file that is there; a schema's ``$id`` is its address and the page states
the edition its address names; a fragment names something its file holds; and
every facet the producer writes validates against the schema its own
``_schemaURL`` names, read from the file the table publishes it from.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Final

import jsonschema
import polars as pl
import pytest
from referencing import Registry, Resource

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import (
    KNOWN_FACETS,
    PRODUCER_URI,
    SCHEMA_URL_TEMPLATE,
    GraphExporter,
)
from gaspatchio.frame.graph.artifact import _HOLE_CLOSES_WITH
from gaspatchio.rollforward import compile_rollforward

_REPOSITORY: Final = Path(__file__).resolve().parents[4]
_README: Final = _REPOSITORY / "spec" / "graph-artifact" / "README.md"
_SPECIFICATION: Final = _REPOSITORY / "spec" / "graph-artifact" / "v0-preview.md"

# What ships: each distribution's package, whose code and data name addresses.
_SHIPPED: Final = ("bindings/python/gaspatchio", "engines/jax/src", "viewer/python")
_ADDRESS: Final = re.compile(
    r"https://gaspatchio\.dev/(?:spec|schemas)/[^\s\"'`<>()\[\],;\\]+"
)
_ROW: Final = re.compile(r"^\| `(https://gaspatchio\.dev/[^`]+)` \| `([^`]+)` \|$")


def _published() -> dict[str, Path]:
    """Return the README's table: each address, and the file it is published from."""
    rows = {
        found.group(1): _REPOSITORY / found.group(2)
        for line in _README.read_text("utf-8").splitlines()
        if (found := _ROW.match(line))
    }
    assert rows, "the README states no address at all"
    return rows


def _written() -> set[str]:
    """Return every address the producer writes into an artifact."""
    return {
        PRODUCER_URI,
        _HOLE_CLOSES_WITH,
        *(SCHEMA_URL_TEMPLATE.format(name=name) for name in KNOWN_FACETS),
    }


def _named() -> set[str]:
    """Return every address the shipped code and data name, templates expanded."""
    found: set[str] = set()
    for root in _SHIPPED:
        for path in sorted((_REPOSITORY / root).rglob("*")):
            if path.suffix not in {".py", ".pyi", ".json"} or not path.is_file():
                continue
            for address in _ADDRESS.findall(path.read_text("utf-8")):
                if "{name}" in address:
                    found |= {address.format(name=name) for name in KNOWN_FACETS}
                else:
                    found.add(address)
    return found


def _base(address: str) -> str:
    return address.partition("#")[0]


def test_every_address_the_producer_writes_is_published() -> None:
    unpublished = sorted({_base(one) for one in _written()} - set(_published()))

    assert unpublished == [], (
        "The producer writes an address spec/graph-artifact/README.md does not "
        f"publish: {unpublished}. Add the file that answers it to the table."
    )


def test_every_address_the_shipped_code_names_is_published() -> None:
    named = _named()
    assert _written() <= named, "the scan missed an address the producer writes"

    unpublished = sorted({_base(one) for one in named} - set(_published()))

    assert unpublished == [], unpublished


def test_every_published_address_is_a_file_that_is_there() -> None:
    missing = sorted(
        str(path.relative_to(_REPOSITORY))
        for path in _published().values()
        if not path.is_file()
    )

    assert missing == []


def test_a_published_schema_is_the_schema_its_address_names() -> None:
    schemas = {
        address: path
        for address, path in _published().items()
        if address.startswith("https://gaspatchio.dev/schemas/")
    }
    assert len(schemas) == 1 + len(KNOWN_FACETS)

    for address, path in schemas.items():
        schema = json.loads(path.read_text("utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["$id"] == address, path.name


def test_the_published_page_states_the_edition_its_address_names() -> None:
    pages = {
        address: path
        for address, path in _published().items()
        if address.startswith("https://gaspatchio.dev/spec/")
    }
    assert pages

    for address, path in pages.items():
        edition = address.rsplit("/", 1)[-1]
        assert f"**Identifier:** `gaspatchio-graph/{edition}`" in path.read_text(
            "utf-8"
        ), address


def test_every_fragment_names_what_its_file_holds() -> None:
    published = _published()
    fragments = sorted(one for one in _written() | _named() if "#" in one)
    assert _HOLE_CLOSES_WITH in fragments

    for address in fragments:
        base, _, fragment = address.partition("#")
        text = published[base].read_text("utf-8")
        if fragment.startswith("/"):
            held: Any = json.loads(text)
            for step in fragment.strip("/").split("/"):
                held = held[step]
        else:
            assert f'<a id="{fragment}"></a>' in text, address


def _registry() -> Registry:
    """Return every published schema, keyed by its address, and nothing fetched."""
    return Registry().with_resources(
        (address, Resource.from_contents(json.loads(path.read_text("utf-8"))))
        for address, path in _published().items()
        if path.suffix == ".json"
    )


def _schema_for(
    facet: dict[str, Any], registry: Registry
) -> jsonschema.Draft202012Validator:
    """Return the validator for the schema a facet's own ``_schemaURL`` names."""
    resolved = registry.resolver().lookup(facet["_schemaURL"]).contents
    return jsonschema.Draft202012Validator(resolved, registry=registry)


def _machine_model(*, boundary: bool) -> ActuarialFrame:
    """Return a model that escalated to a state machine, and every facet with it.

    A fund opening at an expression the tree has no node for, grown, then
    rounded -- a structural step, so a null label -- and, where asked, stopped
    by a contract boundary.
    """
    periods = 12
    frame = ActuarialFrame(
        {
            "av_init": [100_000.0],
            "load": [0.95],
            "fund_return": [[0.01] * periods],
            "surrendered": [[False] * periods],
        }
    ).projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=periods, frequency="monthly"
    )
    builder = frame.projection.rollforward(
        states={"fund_value": pl.col("av_init") * pl.col("load")},
        lapse_when_all_non_positive=("fund_value",),
        contract_boundary=frame["surrendered"] if boundary else None,
    )
    builder["fund_value"].grow(frame["fund_return"], label="growth").round(decimals=2)
    frame.fund = compile_rollforward(builder).expr_for("fund_value")
    return frame


@pytest.mark.parametrize("boundary", [True, False], ids=["bounded", "unbounded"])
def test_every_facet_the_producer_writes_validates_against_its_published_schema(
    *, boundary: bool
) -> None:
    artifact = json.loads(
        GraphExporter(_machine_model(boundary=boundary)).export(
            profile="executable", include_lowered=True
        )
    )
    carried = [
        *artifact["facets"].items(),
        *(
            (name, facet)
            for node in artifact["nodes"]
            for name, facet in (node.get("facets") or {}).items()
        ),
    ]
    assert {name for name, _ in carried} == set(KNOWN_FACETS)
    registry = _registry()

    for name, facet in carried:
        errors = [
            error.message for error in _schema_for(facet, registry).iter_errors(facet)
        ]
        assert errors == [], name


def test_a_movement_the_producer_cannot_classify_validates() -> None:
    """``reads_running_balance`` is null where the amount's expression is opaque.

    The producer writes ``None`` for an expression the tree cannot classify,
    and the artifact's own increment summary allows the null; the facet that
    carries the machine has to allow it too, or a document the producer wrote
    would fail against the schema it names.
    """
    artifact = json.loads(
        GraphExporter(_machine_model(boundary=False)).export(profile="executable")
    )
    facet = artifact["facets"]["gaspatchio_rollforward_ir"]
    (machine,) = facet["compilations"].values()
    machine["increments"][0]["reads_running_balance"] = None
    registry = _registry()

    errors = [
        error.message for error in _schema_for(facet, registry).iter_errors(facet)
    ]

    assert errors == []
    machine["increments"][0]["reads_running_balance"] = "unknown"
    assert list(_schema_for(facet, registry).iter_errors(facet))


_FACET: Final = {"_producer": PRODUCER_URI}


@pytest.mark.parametrize(
    "facet",
    [
        {
            **_FACET,
            "_schemaURL": SCHEMA_URL_TEMPLATE.format(name="gaspatchio_lowered"),
            "engine": "polars",
        },
        {
            **_FACET,
            "_schemaURL": SCHEMA_URL_TEMPLATE.format(
                name="gaspatchio_column_transformation"
            ),
            "reads": [
                {
                    "source": "a",
                    "transformations": [{"type": "DIRECT", "subtype": "JOIN"}],
                }
            ],
        },
        {
            **_FACET,
            "_schemaURL": SCHEMA_URL_TEMPLATE.format(name="gaspatchio_rollforward_ir"),
            "compilations": {"sha256:0": {"points": ["bop", "eop"]}},
        },
    ],
    ids=["lowered-without-text", "a-direct-read-narrowed-by-a-join", "a-bare-body"],
)
def test_a_published_facet_schema_refuses_what_the_producer_never_writes(
    facet: dict[str, Any],
) -> None:
    registry = _registry()

    assert list(_schema_for(facet, registry).iter_errors(facet))


def _facet_examples() -> list[tuple[str, dict[str, Any]]]:
    """Return every facet the specification's own JSON examples show."""
    blocks = re.findall(
        r"^```json\n(.*?)^```",
        _SPECIFICATION.read_text("utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    examples = []
    for block in blocks:
        if '"_producer"' not in block:
            continue
        document = json.loads(
            block if block.lstrip().startswith("{") else f"{{{block}}}"
        )
        examples.extend(document["facets"].items())
    return examples


def test_the_specification_shows_the_addresses_the_producer_writes() -> None:
    """An example of a facet is one a reader can hold a real artifact up to."""
    examples = _facet_examples()
    assert {name for name, _ in examples} == {
        "gaspatchio_lowered",
        "gaspatchio_column_transformation",
    }
    registry = _registry()

    for name, facet in examples:
        assert facet["_producer"] == PRODUCER_URI, name
        assert facet["_schemaURL"] == SCHEMA_URL_TEMPLATE.format(name=name), name
        errors = [
            error.message for error in _schema_for(facet, registry).iter_errors(facet)
        ]
        assert errors == [], name
