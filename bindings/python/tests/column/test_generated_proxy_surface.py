# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The explicit proxy surface is generated from its operation declarations."""

from __future__ import annotations

import inspect
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio._semantic.ir import Call, EngineNative
from gaspatchio._semantic.operations import GENERATED_PROXY_OPERATIONS
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame import ActuarialFrame
from scripts.generate_proxy_surface import (
    OUTPUT,
    render_generated_proxy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_METHODS = tuple(operation.identifier for operation in GENERATED_PROXY_OPERATIONS)


def test_the_checked_in_surface_matches_the_operation_set() -> None:
    """Generation drift fails without rewriting the reviewable artifact."""
    assert OUTPUT.read_text(encoding="utf-8") == render_generated_proxy()


def test_generation_bootstraps_a_missing_output(tmp_path: Path) -> None:
    """A clean interpreter can check and create an absent generated module."""
    project = Path(__file__).parents[2]
    script = tmp_path / "scripts" / "generate_proxy_surface.py"
    operations = tmp_path / "gaspatchio" / "_semantic" / "operations.py"
    output = tmp_path / "gaspatchio" / "column" / "_generated_proxy.py"
    script.parent.mkdir()
    operations.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    shutil.copyfile(project / "scripts" / script.name, script)
    shutil.copyfile(project / "gaspatchio" / "_semantic" / operations.name, operations)

    command = [sys.executable, "-I", "-S", str(script)]
    absent = subprocess.run(  # noqa: S603 - fixed interpreter and local script
        [*command, "--check"], capture_output=True, text=True, check=False
    )
    assert absent.returncode == 1
    assert not output.exists()

    generated = subprocess.run(  # noqa: S603 - fixed interpreter and local script
        command, capture_output=True, text=True, check=False
    )
    assert generated.returncode == 0, generated.stderr
    assert output.read_text(encoding="utf-8") == OUTPUT.read_text(encoding="utf-8")

    current = subprocess.run(  # noqa: S603 - fixed interpreter and local script
        [*command, "--check"], capture_output=True, text=True, check=False
    )
    assert current.returncode == 0, current.stderr


@pytest.mark.parametrize("proxy_type", [ColumnProxy, ExpressionProxy])
def test_each_declared_operation_is_an_explicit_generated_method(
    proxy_type: type,
) -> None:
    """The family no longer depends on a descriptor copied from ``pl.Expr``."""
    for name in _METHODS:
        method = inspect.getattr_static(proxy_type, name)
        assert inspect.isfunction(method)
        assert method.__module__ == "gaspatchio.column._generated_proxy"


def test_the_generated_signatures_are_the_declared_signatures() -> None:
    """Runtime introspection and the neutral declarations expose one contract."""
    for operation in GENERATED_PROXY_OPERATIONS:
        method = getattr(ColumnProxy, operation.identifier)
        generated = inspect.signature(method)
        generated_parameters = tuple(generated.parameters.values())[1:]
        declared_parameters = tuple(operation.surface_signature().parameters.values())
        assert tuple(
            (parameter.name, parameter.kind, parameter.default)
            for parameter in generated_parameters
        ) == tuple(
            (parameter.name, parameter.kind, parameter.default)
            for parameter in declared_parameters
        )
        assert inspect.getdoc(method) == inspect.getdoc(operation.binder)

    assert tuple(inspect.signature(ColumnProxy.log).parameters) == ("self",)
    assert tuple(inspect.signature(ColumnProxy.round_sig_figs).parameters) == (
        "self",
        "digits",
    )
    round_parameters = inspect.signature(ColumnProxy.round).parameters
    assert tuple(round_parameters) == ("self", "decimals", "mode")
    assert round_parameters["decimals"].default == 0
    assert round_parameters["mode"].default == "half_to_even"
    assert round_parameters["mode"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_round_sig_figs_keyword_uses_the_declared_attribute_name() -> None:
    """``digits`` is the supported keyword at both proxy entry points."""
    frame = ActuarialFrame(pl.DataFrame({"value": [1234.567]}))

    column_node = frame.value.round_sig_figs(digits=3)._node  # noqa: SLF001
    expression_node = (frame.value + 0).round_sig_figs(digits=3)._node  # noqa: SLF001

    for node in (column_node, expression_node):
        assert isinstance(node, Call)
        assert node.name == "round_sig_figs"
        assert node.attrs == (("digits", 3),)


def test_round_preserves_defaults_none_and_a_positional_mode() -> None:
    """Every form the previous recognizer recorded keeps the same attributes."""
    frame = ActuarialFrame(pl.DataFrame({"value": [2.5]}))

    cases = (
        (frame.value.round(), (("decimals", 0), ("mode", "half_to_even"))),
        (frame.value.round(None, None), (("decimals", 0), ("mode", "half_to_even"))),
        (
            (frame.value + 0).round(2, "half_away_from_zero"),
            (("decimals", 2), ("mode", "half_away_from_zero")),
        ),
        (
            frame.value.round(decimals=1, mode="half_to_even"),
            (("decimals", 1), ("mode", "half_to_even")),
        ),
    )

    for expression, attrs in cases:
        node = expression._node  # noqa: SLF001
        assert isinstance(node, Call)
        assert node.name == "round"
        assert node.attrs == attrs


@pytest.mark.parametrize(
    "call",
    [
        lambda frame: frame.value.log(2),
        lambda frame: frame.value.round_sig_figs(digits=True),
        lambda frame: (frame.value + 0).log(base=2),
        lambda frame: frame.value.is_null(1),
        lambda frame: frame.value.round(True),  # noqa: FBT003
        lambda frame: frame.value.round(2, []),
        lambda frame: frame.value.round(2, mode={}),
        lambda frame: frame.value.clip(),
        lambda frame: frame.value.cut(range(1, 3)),
        lambda frame: frame.value.fill_null(strategy="forward"),
        lambda frame: frame.value.is_in({1.0, 2.0}),
        lambda frame: frame.value.replace([1.0], [2.0], default=0.0),
    ],
)
def test_a_form_outside_the_declaration_names_the_escape(
    call: Callable[[ActuarialFrame], object],
) -> None:
    """A generated method refuses rather than falling through to Polars."""
    frame = ActuarialFrame(pl.DataFrame({"value": [8.0]}))

    with pytest.raises(TypeError, match=r"polars_native\(\)"):
        call(frame)


def test_the_logarithm_escape_keeps_only_the_form_the_vocabulary_declines() -> None:
    """Natural log is core; an explicitly based logarithm is Polars-native."""
    frame = ActuarialFrame(pl.DataFrame({"value": [8.0]}))

    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.value.polars_native().log()

    escaped = frame.value.polars_native().log(2)
    assert isinstance(escaped._node, EngineNative)  # noqa: SLF001


def test_direct_method_defaults_and_positional_forms_reach_the_declarations() -> None:
    """Generated forwarding keeps every form the recognizers already admitted."""
    frame = ActuarialFrame({"value": [[1.0, None, 3.0]]})
    expressions = (
        frame.value.clip(None, 2.0),
        frame.value.cut([1.0, 2.0], None, True, True),  # noqa: FBT003
        frame.value.fill_null(0.0, None, None),
        frame.value.is_in([1.0, 3.0], True),  # noqa: FBT003
        frame.value.replace([1.0], [2.0], None, None),
    )
    nodes: list[Call] = []
    for expression in expressions:
        node = expression._node  # noqa: SLF001
        assert isinstance(node, Call)
        nodes.append(node)

    assert [node.name for node in nodes] == [
        "clip",
        "cut",
        "fill_null",
        "is_in",
        "replace",
    ]
    assert nodes[0].attrs == (("bounds", "upper"),)
    assert nodes[1].attrs == (
        ("left_closed", True),
        ("include_breaks", True),
    )
    assert nodes[3].attrs == (("nulls_equal", True),)


@pytest.mark.parametrize("expression_receiver", [False, True])
@pytest.mark.parametrize(
    ("name", "reverse", "expected"),
    [
        ("cum_sum", False, [[2, 5, 9], [5, 7]]),
        ("cum_sum", True, [[9, 7, 4], [7, 2]]),
        ("cum_prod", False, [[2, 6, 24], [5, 10]]),
        ("cum_prod", True, [[24, 12, 4], [10, 2]]),
    ],
)
def test_generated_accumulations_fold_each_policy_in_the_declared_direction(
    *,
    name: str,
    reverse: bool,
    expected: list[list[int]],
    expression_receiver: bool,
) -> None:
    """Keyword-only forwarding preserves independent ragged policy timelines."""
    frame = ActuarialFrame({"value": [[2, 3, 4], [5, 2]]})
    receiver = frame.value + 0 if expression_receiver else frame.value
    result = getattr(receiver, name)(reverse=reverse)
    node = result._node  # noqa: SLF001
    assert isinstance(node, Call)
    assert node.name == name
    assert node.attrs == (("reverse", reverse),)
    frame.result = result
    assert frame.collect()["result"].to_list() == expected


@pytest.mark.parametrize(
    ("name", "expected"), [("cum_sum", [2, 5, 9]), ("cum_prod", [2, 6, 24])]
)
def test_row_accumulations_require_the_explicit_engine_spelling(
    name: str, expected: list[int]
) -> None:
    """A row fold cannot silently claim to fold the periods within a policy."""
    frame = ActuarialFrame({"value": [2, 3, 4]})
    with pytest.raises(TypeError, match="folds projection periods"):
        getattr(frame.value, name)()
    running = getattr(frame.value.polars_native(), name)()
    assert isinstance(running._node, EngineNative)  # noqa: SLF001
    frame.running = running
    assert frame.collect()["running"].to_list() == expected

    periods = ActuarialFrame({"value": [[2, 3, 4]]})
    with pytest.raises(TypeError, match=r"polars_native\(\)"):
        getattr(periods.value, name)(True)  # noqa: FBT003 - forbidden positional form
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        getattr(periods.value.polars_native(), name)()


def test_operators_and_namespaces_are_declared_without_engine_reflection() -> None:
    """Operators and namespace methods have the same source as direct methods."""
    from gaspatchio._semantic.operations import (  # noqa: PLC0415
        GENERATED_OPERATOR_SPELLINGS,
        PROXY_NAMESPACE_OPERATIONS,
    )

    frame = ActuarialFrame({"values": [[1.0, 2.0]]})
    for proxy in (frame.values, frame.values + 1):
        for spelling in GENERATED_OPERATOR_SPELLINGS:
            method = inspect.getattr_static(type(proxy), spelling.name)
            assert method.__module__ == "gaspatchio.column._generated_proxy"
            actual = tuple(inspect.signature(method).parameters.values())[1:]
            expected = tuple(spelling.signature.parameters.values())
            assert [(p.name, p.kind, p.default) for p in actual] == [
                (p.name, p.kind, p.default) for p in expected
            ]
        for name, operations in PROXY_NAMESPACE_OPERATIONS.items():
            namespace = getattr(proxy, name)
            for operation in operations:
                method = getattr(namespace, operation.identifier.rsplit(".", 1)[-1])
                assert method.__module__ == "gaspatchio.column._generated_proxy"


def test_boolean_lists_and_scalar_predicates_keep_the_policy_axis() -> None:
    """Ragged Boolean inputs combine with scalar and computed predicates."""
    frame = ActuarialFrame(
        {
            "eligible": [[True, False, None], [False, True]],
            "selected": [True, False],
            "amount": [[10.0, 0.0, 5.0], [20.0, 0.0]],
        }
    )
    frame.both = frame.eligible & frame.selected
    frame.either = frame.eligible | (frame.amount > 0)
    frame.inverse = ~frame.eligible
    frame.nested = ((frame.amount > 0) & frame.selected) | frame.eligible
    result = frame.collect()
    assert result["both"].to_list() == [[1.0, 0.0, None], [0.0, 0.0]]
    assert result["either"].to_list() == [[1.0, 0.0, None], [1.0, 1.0]]
    assert result["inverse"].to_list() == [[0.0, 1.0, None], [1.0, 0.0]]
    assert result["nested"].to_list() == [[1.0, 0.0, None], [0.0, 1.0]]


def test_numeric_flags_are_explicit_and_native_bit_operations_remain_available() -> (
    None
):
    """Numeric data is not silently interpreted as a predicate mask."""
    frame = ActuarialFrame({"flag": [1, 2, 3]})
    with pytest.raises(TypeError, match="Compare numeric flags explicitly"):
        _ = frame.flag & True
    with pytest.raises(TypeError, match="Compare numeric flags explicitly"):
        _ = ~frame.flag
    with pytest.raises(TypeError, match="Compare numeric flags explicitly"):
        _ = (frame.flag > 1) | frame.flag
    frame.bits = frame.flag.polars_native().and_(2)
    frame.inverted_bits = frame.flag.polars_native().not_()
    result = frame.collect()
    assert result["bits"].to_list() == [0, 2, 2]
    assert result["inverted_bits"].to_list() == [-2, -3, -4]


def test_native_namespaces_preserve_lineage_and_refuse_owned_forms() -> None:
    """A native namespace is one explicit engine expression with honest reads."""
    frame = ActuarialFrame({"code": [" ab "], "codes": [["a", "b"]]})
    cleaned = frame.code.polars_native().str.strip_chars()
    upper = frame.codes.polars_native().list.eval(pl.element().str.to_uppercase())
    assert isinstance(cleaned._node, EngineNative)  # noqa: SLF001
    assert isinstance(upper._node, EngineNative)  # noqa: SLF001
    frame.cleaned = cleaned
    frame.upper = upper
    assert frame.collect()["cleaned"].to_list() == ["ab"]
    assert frame.collect()["upper"].to_list() == [["A", "B"]]
    assert frame.graph.holes() == []
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.code.polars_native().str.to_date()
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.codes.polars_native().list.sum()
    with pytest.raises(TypeError, match="not a Polars expression"):
        frame.code.polars_native().meta.root_names()


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("reflected", [False, True])
def test_boolean_expression_lists_combine_with_column_masks(
    native: bool,
    reflected: bool,
) -> None:
    """Absence predicates and native Boolean lists use the same mask conversion."""
    frame = ActuarialFrame(
        {"value": [[1.0, None, 2.0]], "eligible": [[True, False, None]]}
    )
    missing = (
        frame.value.polars_native().list.eval(pl.element().is_null())
        if native
        else frame.value.is_null()
    )
    frame.either = frame.eligible | missing if reflected else missing | frame.eligible
    frame.both_calls = missing | frame.value.is_not_null()
    result = frame.collect()
    assert result["either"].to_list() == [[1.0, 1.0, None]]
    assert result["both_calls"].to_list() == [[1.0, 1.0, 1.0]]


@pytest.mark.parametrize("as_list", [False, True])
def test_raw_boolean_expression_operands_keep_their_engine_dependency(
    as_list: bool,
) -> None:
    """Raw Boolean ingress is accepted without guessing numeric flags."""
    values = [[True, False]] if as_list else [True, False]
    frame = ActuarialFrame({"a": values, "b": values})
    frame.both = frame.a & pl.col("b")
    frame.either = frame.a | pl.lit(True)
    result = frame.collect()
    assert result["both"].to_list() == ([[1.0, 0.0]] if as_list else [True, False])
    assert result["either"].to_list() == ([[1.0, 1.0]] if as_list else [True, True])
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.a.polars_native().and_(pl.col("b"))
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.a.polars_native().or_(False)
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        frame.a.polars_native().not_()


def test_refused_native_operator_does_not_retain_an_engine_operand() -> None:
    """An unsuccessful spelling check must not grow the runtime node table."""
    from gaspatchio.frame.lowering.ingress import NATIVE_REFS

    af = ActuarialFrame(pl.DataFrame({"x": [1, 2], "y": [3, 4]}))
    before = set(NATIVE_REFS)
    with pytest.raises(ValueError, match="already in gaspatchio's vocabulary"):
        af.x.polars_native().add(pl.col("y"))
    assert set(NATIVE_REFS) == before


def test_native_boolean_alias_advice_names_a_callable_owned_spelling() -> None:
    """The engine's logical method aliases must point to our operators."""
    af = ActuarialFrame(pl.DataFrame({"flag": [True, False]}))
    for method, args, remedy in (
        ("and_", (True,), "af.<column> & other"),
        ("or_", (False,), "af.<column> | other"),
        ("not_", (), "~af.<column>"),
    ):
        with pytest.raises(ValueError) as caught:
            getattr(af.flag.polars_native(), method)(*args)
        assert remedy in str(caught.value)
