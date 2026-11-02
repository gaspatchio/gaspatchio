# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table, mortality, curve or schedule read is its own node, never engine text.

``table.lookup(age=af.age).fill_nan(0.0)`` used to reach the record as one
engine-native fragment identified by Polars' display of its plan, which names
the lookup plugin and not the table. Two models reading two different tables
then exported one ``graph_fingerprint``: a false identity, not a partial
account (spec Annex A.2). Every way of putting a read inside a fragment -- an
undeclared method, a Polars free function, the explicit escape, a producer
with no frame -- is now refused at the frame's door, naming the read; a
rename keeps the node; a compiled rollforward, whose fragment reads its
hidden column by name, is exempt; and a raw Polars frame is untouched.
``fill_nan`` is now a declared operation (section 11.1.13), so on a producer
with a frame it is a core node over the read and moves with its base, as
every declared name does.

Each case builds the same model twice over two bases that differ in name and
content, and asserts the line is refused or the fingerprint moves -- never
that both models export one identity.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio.assumptions import Table
from gaspatchio.curves import Curve
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.mortality import MortalityTable
from gaspatchio.schedule import Actual360, Actual365Fixed, Schedule

if TYPE_CHECKING:
    from collections.abc import Callable

_REFUSED = "inside a Polars expression the framework cannot see into"
_DAY_COUNTS = (Actual365Fixed(), Actual360())


def _frame(variant: int = 0) -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "age": [40, 41],
                "av0": [100.0, 200.0],
                "issue_date": [date(2020, 1, 31), date(2021, 6, 30)],
            }
        )
    )
    af = af.projection.set(
        schedule=Schedule.from_calendar_grid(
            start_date=date(2026, 1, 31),
            n_periods=3,
            frequency="1M",
            day_count=_DAY_COUNTS[variant],
        )
    )
    af.attained_age = af.age + af.month // 12
    af.t = af.projection.t_years()
    af.prem = af.av0 * 0.0 + af.t * 0.0 + 10.0
    return af


def _table(variant: int) -> Table:
    return Table(
        name=f"value_read_{variant}",
        source=pl.DataFrame(
            {
                "age": list(range(30, 60)),
                "rate": [0.01 * k + 0.001 * variant for k in range(30)],
            }
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _rollforward(af: ActuarialFrame, variant: int) -> object:
    rf = af.projection.rollforward(states={"av": af["av0"]})
    rf["av"].add(af["prem"], label="premium").floor(5.0 * variant)
    return compile_rollforward(rf)


_LIST = pl.List(pl.Float32)

# name, producer(af, variant), the dtype a cast of it lands on, whether it has
# a frame (the escape is a frame's door), and whether it is a value object.
_PRODUCERS: list[
    tuple[str, Callable[[ActuarialFrame, int], pl.Expr], pl.DataType, bool, bool]
] = [
    (
        "Table.lookup, per-policy key",
        lambda af, i: _table(i).lookup(age=af.age),
        pl.Float32(),
        True,
        True,
    ),
    (
        "Table.lookup, per-period key",
        lambda af, i: _table(i).lookup(age=af.attained_age),
        _LIST,
        True,
        True,
    ),
    (
        "Table.lookup, literal key (no frame)",
        lambda _af, i: _table(i).lookup(age=40),
        pl.Float32(),
        False,
        True,
    ),
    (
        "MortalityTable.at",
        lambda af, i: MortalityTable(
            table=_table(i), age_basis="age_last_birthday", structure="aggregate"
        ).at(age=af.attained_age),
        _LIST,
        True,
        True,
    ),
    (
        "Curve.spot_rate",
        lambda af, i: Curve.from_zero_rates(
            tenors=[1.0, 5.0], rates=[0.03 + 0.01 * i, 0.04]
        ).spot_rate(af.t),
        _LIST,
        True,
        True,
    ),
    (
        "Curve.discount_factor",
        lambda af, i: Curve.from_zero_rates(
            tenors=[1.0, 5.0], rates=[0.03 + 0.01 * i, 0.04]
        ).discount_factor(af.t),
        _LIST,
        True,
        True,
    ),
    (
        "Schedule.year_fractions_expr (no frame, day count)",
        lambda _af, i: Schedule.from_inception(
            inception_column="issue_date",
            n_periods=3,
            frequency="1M",
            day_count=_DAY_COUNTS[i],
        ).year_fractions_expr(),
        _LIST,
        False,
        True,
    ),
    (
        "af.projection.year_fractions (the frame's schedule)",
        lambda af, _i: af.projection.year_fractions(),
        _LIST,
        True,
        True,
    ),
    (
        "CompiledRollforward.expr_for (exempt)",
        lambda af, i: _rollforward(af, i).expr_for("av"),  # type: ignore[attr-defined]
        _LIST,
        True,
        False,
    ),
]


def _frame_for(name: str, variant: int) -> ActuarialFrame:
    # The frame's own schedule is the base of the projection producer; every
    # other producer reads a base of its own over one and the same frame.
    return _frame(variant if "frame's schedule" in name else 0)


def _paths(
    to: pl.DataType, *, has_frame: bool
) -> list[tuple[str, Callable[[ActuarialFrame, pl.Expr], ActuarialFrame], bool]]:
    """Return each path, its build, and whether it is a declared operation."""

    def assign(af: ActuarialFrame, value: object) -> ActuarialFrame:
        af.q = value
        return af

    paths: list[
        tuple[str, Callable[[ActuarialFrame, pl.Expr], ActuarialFrame], bool]
    ] = [
        ("an undeclared method", lambda af, e: assign(af, e.cast(to)), False),
        (
            "a Polars free function",
            lambda af, e: assign(af, pl.when(pl.lit(value=True)).then(e).otherwise(e)),
            False,
        ),
        # Declared since the vocabulary gained it (11.1.13). With no frame in
        # sight the method stays Polars' own, as every declared name does.
        ("the declared fill_nan", lambda af, e: assign(af, e.fill_nan(0.0)), True),
    ]
    if has_frame:
        paths.append(
            (
                "the explicit escape",
                lambda af, e: assign(af, e.polars_native().cast(to)),  # type: ignore[attr-defined]
                False,
            )
        )
    return paths


def _cases() -> list[object]:
    cases: list[object] = []
    for name, producer, to, has_frame, is_value_object in _PRODUCERS:
        for path, build, declared in _paths(to, has_frame=has_frame):
            refused = is_value_object and not (declared and has_frame)
            cases.append(
                pytest.param(name, producer, build, refused, id=f"{name} | {path}")
            )
    return cases


def _identity(af: ActuarialFrame) -> tuple[str, str]:
    document = json.loads(GraphExporter(af).export(include_source=False))
    node = next(node for node in document["nodes"] if node["column"] == "q")
    return document["graph_fingerprint"], node["fingerprint"]


@pytest.mark.parametrize(("name", "producer", "build", "refused"), _cases())
def test_a_read_in_a_fragment_is_refused_or_moves_never_blind(
    name: str,
    producer: Callable[[ActuarialFrame, int], pl.Expr],
    build: Callable[[ActuarialFrame, pl.Expr], ActuarialFrame],
    refused: bool,  # noqa: FBT001 -- a parametrised flag
) -> None:
    """Two bases differing in name and content never share one identity."""
    if refused:
        af = _frame_for(name, 0)
        with pytest.raises(ValueError, match=_REFUSED):
            build(af, producer(af, 0))
        return

    identities = []
    for variant in (0, 1):
        af = _frame_for(name, variant)
        identities.append(_identity(build(af, producer(af, variant))))
    (graph_a, node_a), (graph_b, node_b) = identities
    assert node_a != node_b, name
    assert graph_a != graph_b, name


@pytest.mark.parametrize(
    ("name", "producer"), [(case[0], case[1]) for case in _PRODUCERS]
)
def test_a_renamed_read_keeps_its_node_and_moves(
    name: str, producer: Callable[[ActuarialFrame, int], pl.Expr]
) -> None:
    """``alias`` is a name, not a calculation: the read stays the node it was."""
    identities = []
    for variant in (0, 1):
        af = _frame_for(name, variant)
        af = af.with_columns(producer(af, variant).alias("q"))
        identities.append(_identity(af))
    (graph_a, node_a), (graph_b, node_b) = identities
    assert node_a != node_b, name
    assert graph_a != graph_b, name


def test_the_refusal_names_the_table_and_both_moves() -> None:
    """The message says what was read and the two ways to keep it a node."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    with pytest.raises(ValueError, match=_REFUSED) as refusal:
        af.q = _table(0).lookup(age=af.age).cast(pl.Float32)

    message = str(refusal.value)
    assert "the assumption table 'value_read_0' (sha256:" in message
    assert "to_float(), to_integer(), to_text() or to_list()" in message
    # The declared fill, not the three-part conditional it used to spell out.
    assert "a NaN fill is fill_nan(0.0)" in message
    assert "is_nan()" not in message
    assert "af.q_read = <the read>" in message
    assert "af.q = af.q_read.polars_native().<method>(...)" in message


def test_the_two_line_form_moves_with_the_table() -> None:
    """Stored first, the read is a node the fragment reaches through ``reads``."""
    identities = []
    for variant in (0, 1):
        af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
        af.q_read = _table(variant).lookup(age=af.age)
        af.q = af.q_read.polars_native().cast(pl.Float32)
        identities.append(_identity(af))
    assert identities[0][1] != identities[1][1]
    assert identities[0][0] != identities[1][0]


def test_a_raw_polars_frame_is_untouched() -> None:
    """A producer's expression on a plain Polars frame keeps Polars' meaning."""
    table = _table(0)
    out = pl.DataFrame({"age": [40, 41]}).with_columns(
        (table.lookup(age=pl.col("age")).fill_nan(0.0) * 2.0).alias("q"),
        pl.max_horizontal(table.lookup(age=pl.col("age")), pl.lit(0.0)).alias("m"),
    )
    assert out["q"].to_list() == pytest.approx([0.2, 0.22])
    assert out["m"].to_list() == pytest.approx([0.1, 0.11])


# The repro the defect was reported with, kept as it was written: every line
# either moves with the table or is refused.
_PROBE: dict[str, Callable[[pl.Expr], object]] = {
    "plain": lambda x: x,
    "x*2": lambda x: x * 2,
    "fill_nan": lambda x: x.fill_nan(0.0),
    "fill_null": lambda x: x.fill_null(0.0),
    "clip": lambda x: x.clip(0.0, 1.0),
    "round": lambda x: x.round(4),
    "abs": lambda x: x.abs(),
    "cast": lambda x: x.cast(pl.Float32),
}


@pytest.mark.parametrize("case", sorted(_PROBE))
def test_the_reported_repro_never_exports_one_identity_for_two_tables(
    case: str,
) -> None:
    """``t.lookup(age=af.age).fill_nan(0.0)`` exported sha256:45ff39c1... twice."""
    fingerprints: list[str] = []
    for variant, rate in enumerate((0.01, 0.05)):
        table = Table(
            name=f"m_{case}_{variant}",
            source=pl.DataFrame({"age": [40, 41], "rate": [rate, 0.02]}),
            dimensions={"age": "age"},
            value="rate",
        )
        af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
        if case == "cast":
            with pytest.raises(ValueError, match=_REFUSED):
                af.q = _PROBE[case](table.lookup(age=af.age))
            return
        af.q = _PROBE[case](table.lookup(age=af.age))
        fingerprints.append(af.graph.fingerprint())
    assert fingerprints[0] != fingerprints[1]


def test_a_lookup_filled_on_one_line_is_one_core_node_naming_its_table() -> None:
    """``lookup(...).fill_nan(0.0)`` is a fill over the read, not engine text."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    af.q = _table(0).lookup(age=af.age).fill_nan(0.0)

    document = json.loads(GraphExporter(af).export(include_source=False))
    node = next(node for node in document["nodes"] if node["column"] == "q")
    assert node["tier"] == "core"
    assert node["engines"] == []
    assert node["reads_assumptions"] == ["value_read_0"]
    assert [entry["name"] for entry in document["assumptions"]] == ["value_read_0"]


def test_a_stored_read_filled_on_the_next_line_is_core_and_moves() -> None:
    """``af.q0.fill_nan(0.0)`` was refused as undeclared; it is the operation now."""
    identities = []
    for variant in (0, 1):
        af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
        af.q0 = _table(variant).lookup(age=af.age)
        af.q = af.q0.fill_nan(0.0)
        document = json.loads(GraphExporter(af).export(include_source=False))
        node = next(node for node in document["nodes"] if node["column"] == "q")
        assert node["tier"] == "core"
        identities.append(_identity(af))
    assert identities[0][0] != identities[1][0]
