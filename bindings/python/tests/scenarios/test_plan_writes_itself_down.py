# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario plan writes itself down, every shock kind, and reads back the same plan.

``to_yaml`` refused filtered, time-conditional, pipeline, max, min and clip
shocks, so five of seven rooms could not write their plan down and pinned a
SHA instead; and hand-written sugar parsed to a different identity from the
object it named (an inner shock gained the table, ``time_column`` reset). The
contract now is ``from_yaml(to_yaml(p)).source_sha() == p.source_sha()`` for
every plan, with targets on the outermost shock only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from gaspatchio.scenarios import (
    AdditiveShock,
    ClipShock,
    FilteredShock,
    MaxShock,
    MinShock,
    MultiplicativeShock,
    OverrideShock,
    PipelineShock,
    ScenarioRun,
    Shock,
    Sum,
    TimeConditionalShock,
    parse_shock_config,
)

_AGG = (Sum("loss").alias("loss").over("scenario_id"),)
_NUMBER = st.floats(min_value=-5.0, max_value=5.0, allow_nan=False).map(
    lambda x: round(x, 6)
)
_WHERE = st.sampled_from(
    [
        {"age": {"gte": 65}},
        {"sex": "F"},
        {"duration": {"between": [1, 5]}},
        {"product": {"in": ["A", "B"]}},
        {"sex": "M", "age": {"lt": 40}},
    ]
)
_WHEN = st.sampled_from([{"t": 0}, {"t": {"lte": 5}}, {"duration": {"gt": 2}}])


def _leaf() -> st.SearchStrategy[Shock]:
    clip = st.tuples(st.none() | _NUMBER, st.none() | _NUMBER).filter(
        lambda b: b != (None, None) and (None in b or b[0] <= b[1])
    )
    return st.one_of(
        _NUMBER.map(lambda f: MultiplicativeShock(f)),
        _NUMBER.map(lambda d: AdditiveShock(d)),
        _NUMBER.map(lambda v: OverrideShock(v)),
        clip.map(lambda b: ClipShock(min_value=b[0], max_value=b[1])),
    )


def _tree(depth: int, *, timed: bool) -> st.SearchStrategy[Shock]:
    if depth == 0:
        return _leaf()
    inner = _tree(depth - 1, timed=timed)
    wraps = [
        st.lists(inner, min_size=1, max_size=3).map(
            lambda s: PipelineShock(shocks=tuple(s))
        ),
        st.tuples(inner, inner).map(lambda ab: MaxShock(ab[0], ab[1])),
        st.tuples(inner, inner).map(lambda ab: MinShock(ab[0], ab[1])),
        st.tuples(inner, _WHERE).map(lambda sw: FilteredShock(sw[0], where=sw[1])),
    ]
    if timed:
        wraps.append(
            st.tuples(inner, _WHEN).map(
                lambda sw: TimeConditionalShock(sw[0], when=sw[1])
            )
        )
    return st.one_of(_leaf(), *wraps)


@st.composite
def _plans(draw: st.DrawFn) -> ScenarioRun:
    """A plan of up to three scenarios, each a shock tree up to depth three."""
    shocks: dict[str, list[Shock]] = {"BASE": []}
    for i in range(draw(st.integers(min_value=1, max_value=3))):
        on_column = draw(st.booleans())
        tree = draw(_tree(3, timed=not on_column))
        target = {"column": "valuation_rate"} if on_column else {"table": "mortality"}
        shocks[f"S{i}"] = [_targeted(tree, target, repeat=draw(st.booleans()))]
    return ScenarioRun(shocks=shocks, aggregations=_AGG)


def _targeted(shock: Shock, target: dict[str, str], *, repeat: bool) -> Shock:
    """Return ``shock`` with ``target`` on it, and on its inner shocks if ``repeat``.

    An inner shock may repeat its outer target or name none; the two spellings
    are one plan, so both must keep the plan's SHA.
    """
    from dataclasses import fields, replace

    changes: dict[str, object] = dict(target)
    for fld in fields(shock):  # type: ignore[arg-type]
        value = getattr(shock, fld.name)
        if isinstance(value, Shock):
            changes[fld.name] = _inner(value, target, repeat=repeat)
        elif isinstance(value, tuple) and value and isinstance(value[0], Shock):
            changes[fld.name] = tuple(_inner(v, target, repeat=repeat) for v in value)
    return replace(shock, **changes)  # type: ignore[type-var]


def _inner(shock: Shock, target: dict[str, str], *, repeat: bool) -> Shock:
    targeted = _targeted(shock, target, repeat=repeat)
    if repeat:
        return targeted
    from dataclasses import replace

    return replace(targeted, table=None, column=None)  # type: ignore[type-var]


@settings(max_examples=300, deadline=None)
@given(_plans())
def test_every_shock_tree_to_depth_three_reads_back_to_the_same_sha(
    plan: ScenarioRun,
) -> None:
    text = yaml.safe_dump(plan.to_dict(), sort_keys=True)
    reread = ScenarioRun.from_dict(yaml.safe_load(text))
    assert reread.source_sha() == plan.source_sha()
    assert reread.canonical_form() == plan.canonical_form()


def test_to_yaml_and_from_yaml_keep_the_sha_through_a_file() -> None:
    plan = ScenarioRun(
        shocks={
            "MORT_CAPPED": [
                PipelineShock(
                    (MultiplicativeShock(1.5), ClipShock(max_value=1.0)),
                    table="mortality_select",
                )
            ],
            "MASS_LAPSE_Y1": [
                TimeConditionalShock(OverrideShock(0.4), when={"t": 0}, table="lapse")
            ],
            "WORSE_OF": [
                MaxShock(
                    MultiplicativeShock(1.2), AdditiveShock(0.002), table="mortality"
                )
            ],
            "FEMALE": [
                FilteredShock(
                    MultiplicativeShock(1.1), where={"sex": "F"}, table="mortality"
                )
            ],
            "RATE_UP_100BP": [AdditiveShock(0.01, column="valuation_rate")],
        },
        aggregations=_AGG,
        master_seed=7,
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.yaml"
        plan.to_yaml(path)
        written = yaml.safe_load(path.read_text())
        assert ScenarioRun.from_yaml(path).source_sha() == plan.source_sha()
    capped = next(s for s in written["scenarios"] if s["id"] == "MORT_CAPPED")
    assert capped["shocks"] == [
        {
            "pipeline": [{"multiply": 1.5}, {"clip": {"max": 1.0}}],
            "table": "mortality_select",
        }
    ]
    rate = next(s for s in written["scenarios"] if s["id"] == "RATE_UP_100BP")
    assert rate["shocks"] == [{"add": 0.01, "column": "valuation_rate"}]


@pytest.mark.parametrize(
    ("sugar", "shock"),
    [
        (
            {"table": "lapse", "multiply": 1.25, "where": {"duration": {"lte": 3}}},
            FilteredShock(
                MultiplicativeShock(1.25), where={"duration": {"lte": 3}}, table="lapse"
            ),
        ),
        (
            {"table": "lapse", "add": 0.4, "when": {"t": {"eq": 0}}},
            TimeConditionalShock(
                AdditiveShock(0.4), when={"t": {"eq": 0}}, table="lapse"
            ),
        ),
        (
            {"table": "lapse", "multiply": 1.5, "clip": [None, 1.0]},
            PipelineShock(
                (MultiplicativeShock(1.5), ClipShock(max_value=1.0)), table="lapse"
            ),
        ),
        (
            {"table": "lapse", "max": [{"multiply": 0.5}, {"add": -0.2}]},
            MaxShock(MultiplicativeShock(0.5), AdditiveShock(-0.2), table="lapse"),
        ),
        (
            {"table": "lapse", "min": [{"multiply": 1.5}, {"set": 0.1}]},
            MinShock(MultiplicativeShock(1.5), OverrideShock(0.1), table="lapse"),
        ),
        (
            {"table": "lapse", "clip": {"min": 0.0}},
            ClipShock(min_value=0.0, table="lapse"),
        ),
        (
            {
                "table": "lapse",
                "multiply": 1.1,
                "where": {"sex": "F"},
                "when": {"t": {"lte": 5}},
            },
            TimeConditionalShock(
                FilteredShock(MultiplicativeShock(1.1), where={"sex": "F"}),
                when={"t": {"lte": 5}},
                table="lapse",
            ),
        ),
        (
            {"column": "valuation_rate", "add": 0.01},
            AdditiveShock(0.01, column="valuation_rate"),
        ),
        (
            {"param": "valuation_rate", "add": 0.01},
            AdditiveShock(0.01, column="valuation_rate"),
        ),
    ],
)
def test_hand_written_sugar_parses_to_the_objects_identity(
    sugar: dict, shock: Shock
) -> None:
    assert parse_shock_config(sugar).canonical_form() == shock.canonical_form()


def test_a_key_a_shock_does_not_take_is_refused() -> None:
    with pytest.raises(
        ValueError, match="keys a shock does not take: \\['mulitply'\\]"
    ):
        parse_shock_config({"table": "lapse", "multiply": 1.5, "mulitply": 2.0})
