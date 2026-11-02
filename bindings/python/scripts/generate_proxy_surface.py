# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Generate the explicit column-proxy surface from operation declarations."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from types import ModuleType

    from gaspatchio._semantic.operations import ProxyOperation, ProxyOperator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "gaspatchio" / "column" / "_generated_proxy.py"
OPERATIONS_SOURCE = PROJECT_ROOT / "gaspatchio" / "_semantic" / "operations.py"
MAX_LINE_LENGTH = 88


def _declarations() -> ModuleType:
    """Load the stdlib-only declarations without importing ``gaspatchio``."""
    module_name = "_gaspatchio_proxy_operations"
    spec = importlib.util.spec_from_file_location(module_name, OPERATIONS_SOURCE)
    if spec is None or spec.loader is None:
        msg = f"Cannot load operation declarations from {OPERATIONS_SOURCE}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[module_name]
    return module


def _operations() -> tuple[ProxyOperation, ...]:
    """Return direct operations for callers checking the generated family."""
    return cast(
        "tuple[ProxyOperation, ...]", _declarations().GENERATED_PROXY_OPERATIONS
    )


def _is_positional_boolean(parameter: inspect.Parameter) -> bool:
    """Return whether Ruff needs the owned positional-Boolean exception."""
    return parameter.kind in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    } and "bool" in inspect.formatannotation(parameter.annotation).split(" | ")


def _definition(
    name: str,
    parameters: tuple[inspect.Parameter, ...],
    rendered_parameters: list[str],
) -> str:
    """Render a method definition, including parameter-level lint ownership."""
    inline_parameters = ", ".join(("self", *rendered_parameters))
    definition = f"    def {name}({inline_parameters}) -> ExpressionProxy:"
    if len(definition) <= MAX_LINE_LENGTH and not any(
        _is_positional_boolean(parameter) for parameter in parameters
    ):
        return definition

    parameter_lines = []
    for parameter, rendered in zip(parameters, rendered_parameters, strict=True):
        line = f"        {rendered},"
        if _is_positional_boolean(parameter):
            line += "  # noqa: FBT001, FBT002 - owned positional form"
        if parameter.name == "format":
            line += "  # noqa: A002 - public spelling"
        parameter_lines.append(line)
    return "\n".join(
        (
            f"    def {name}(",
            "        self,",
            *parameter_lines,
            "    ) -> ExpressionProxy:",
        )
    )


def _method(operation: ProxyOperation, namespace: str | None = None) -> str:
    """Render one explicit proxy method from its declaration."""
    signature = operation.surface_signature()
    parameters = tuple(signature.parameters.values())
    unsupported = [
        parameter
        for parameter in parameters
        if parameter.kind
        not in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]
    if unsupported:
        names = ", ".join(parameter.name for parameter in unsupported)
        msg = f"The proxy generator does not yet render parameter kind(s): {names}"
        raise ValueError(msg)

    rendered_parameters = []
    for index, parameter in enumerate(parameters):
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY and (
            index == 0
            or parameters[index - 1].kind is not inspect.Parameter.KEYWORD_ONLY
        ):
            rendered_parameters.append("*")
        rendered = parameter.name
        if parameter.annotation is not inspect.Signature.empty:
            rendered = f"{rendered}: {inspect.formatannotation(parameter.annotation)}"
        if parameter.default is not inspect.Signature.empty:
            default = (
                json.dumps(parameter.default)
                if isinstance(parameter.default, str)
                else repr(parameter.default)
            )
            rendered = f"{rendered} = {default}"
        rendered_parameters.append(rendered)
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY and (
            index == len(parameters) - 1
            or parameters[index + 1].kind is not inspect.Parameter.POSITIONAL_ONLY
        ):
            rendered_parameters.append("/")

    name = operation.identifier.rsplit(".", 1)[-1]
    qualified = name if namespace is None else f"{namespace}.{name}"
    rendered_parameters = [
        re.sub(r"\bstr\b", "builtins.str", item) for item in rendered_parameters
    ]
    definition = _definition(name, parameters, rendered_parameters)
    forwarded_parameters = tuple(
        f"{parameter.name}={parameter.name}"
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        else parameter.name
        for parameter in parameters
    )
    receiver = "self" if namespace is None else "self._parent_proxy"
    call_arguments = (json.dumps(qualified), receiver, *forwarded_parameters)
    call = f"_call_declared_method({', '.join(call_arguments)})"
    rendered_call = f"        return {call}"
    if len(rendered_call) > MAX_LINE_LENGTH:
        rendered_call = "\n".join(
            (
                "        return _call_declared_method(",
                *(f"            {argument}," for argument in call_arguments),
                "        )",
            )
        )

    doc = inspect.getdoc(operation.binder)
    if doc is None:
        msg = f"{operation.identifier!r} has no public documentation"
        raise ValueError(msg)
    rendered_doc = textwrap.indent(doc, " " * 8)
    return (
        f"    @_refuse_unsupported_form({json.dumps(qualified)})\n"
        f"{definition}\n"
        f'        """{rendered_doc[8:]}\n'
        '        """\n'
        f"{rendered_call}\n"
    )


def _operator(spelling: ProxyOperator) -> str:
    """Render one declared operator without a reflective engine lookup."""
    comparison = (
        spelling.operation is not None and spelling.operation.family == "comparison"
    )
    result = "ConditionExpression" if comparison else "ExpressionProxy"
    helper = "_call_declared_comparison" if comparison else "_call_declared_operator"
    signature = str(spelling.signature)[1:-1]
    parameters = "self" + (", " + signature if signature else "")
    suffix = (
        "  # type: ignore[override]" if spelling.name in {"__eq__", "__ne__"} else ""
    )
    definition = f"    def {spelling.name}({parameters}) -> {result}:{suffix}"
    arguments = [json.dumps(spelling.name), "self", *spelling.signature.parameters]
    doc = textwrap.indent(spelling.documentation.rstrip(), " " * 8)
    return (
        f"    @_refuse_unsupported_form({json.dumps(spelling.name)})\n"
        f"{definition}\n"
        f'        """{doc[8:]}\n'
        '        """\n'
        f"        return {helper}({', '.join(arguments)})\n"
    )


def _namespace_refusal(name: str, declared: str) -> str:
    """Render the refusal a namespace gives a name it does not declare.

    Three things are owed: which names the namespace does hold, the engine
    spelling of the one that was asked for, and what that spelling does to
    the axis. The third differs between the two namespaces, so it is written
    per namespace rather than shared.

    On ``str`` the answer is the list evaluation, because a per-period column
    holds its strings inside each policy's own list and the plain ``str``
    method does not reach them. On ``list`` it is the opposite warning: this
    namespace is already the per-policy axis, and it is the same name
    *without* it that runs down the model points -- the axis
    ``ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE`` names for the bare method
    surface, arrived at through a namespace instead.
    """
    if name == "str":
        closing = (
            '            "Where those strings sit inside each policy\'s own "\n'
            '            "list, write .polars_native().list.eval("\n'
            '            f"pl.element().str.{name}(...))."'
        )
    else:
        closing = (
            '            "which stays inside each policy\'s own periods. The "\n'
            '            "same name without the list namespace, "\n'
            '            f".polars_native().{name}(...), runs down the model "\n'
            '            "points instead, moving values between policies "\n'
            '            "rather than between periods."'
        )
    opening = (
        f'            f"{name}.{{name}} is not a declared gaspatchio operation. "\n'
        f'            "The declared {name} operations are {declared}. "\n'
        f'            f"For the Polars form use .polars_native().{name}.{{name}}(...)'
    )
    opening += '. "' if name == "str" else ', "'
    # The escape's cost, as column/_declared.py's _ESCAPE_COST says it.
    cost = (
        '            " A line written through .polars_native() records as "\n'
        '            "engine_native: it runs only on Polars, and so does every "\n'
        '            "calculation that reads it -- af.graph.tiers() (or gspio "\n'
        '            "graph tiers) names the line, and gspio validate --engine "\n'
        '            "jax names it and every calculation that reads it."'
    )
    return "        msg = (\n" + opening + "\n" + closing + "\n" + cost + "\n        )"


def _namespace(name: str, operations: tuple[ProxyOperation, ...]) -> str:
    """Render an explicit namespace containing only declared operations."""
    class_name = "StringNamespace" if name == "str" else "ListNamespace"
    methods = "\n".join(_method(operation, name) for operation in operations)
    declared = ", ".join(
        sorted(operation.identifier.rsplit(".", 1)[-1] for operation in operations)
    )
    refusal = _namespace_refusal(name, declared)
    return f'''class {class_name}:
    """Declared operations on the {name} namespace of a column or expression.

    Each method records a named operation over its receiver. Engine-specific
    namespace methods are reached through ``polars_native()``.
    """

    def __init__(self, parent: object) -> None:
        """Keep the receiver whose semantic node each operation consumes.

        Access this namespace through a column or expression's property.
        Its methods use that receiver and preserve the frame's context.
        """
        self._parent_proxy = parent

    def __getattr__(self, name: builtins.str) -> object:
        """Name the explicit engine path for undeclared namespace operations.

        String and list methods have their engine meanings on that path;
        per-period string transforms use an explicit list evaluation.
        """
{refusal}
        raise AttributeError(msg)

{methods}'''


def render_generated_proxy() -> str:
    """Return the complete checked-in proxy surface."""
    declarations = _declarations()
    methods = "\n".join(
        _method(operation) for operation in declarations.GENERATED_PROXY_OPERATIONS
    )
    operators = "\n".join(
        _operator(spelling) for spelling in declarations.GENERATED_OPERATOR_SPELLINGS
    )
    namespaces = "\n\n".join(
        _namespace(name, operations)
        for name, operations in declarations.PROXY_NAMESPACE_OPERATIONS.items()
    )
    return f'''# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# This whole file is deterministic mechanical output. The canonical
# operations.py remains under duplication measurement, while generation-drift
# tests compare every byte here, including method bodies.
# jscpd:ignore-start  # noqa: ERA001

"""Explicit proxy methods generated from the engine-neutral operation set.

Do not edit this file directly. Regenerate it from ``bindings/python`` with::

    .venv/bin/python scripts/generate_proxy_surface.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio.column._declared import (
    _call_declared_comparison,
    _call_declared_method,
    _call_declared_operator,
    _refuse_a_truth_value,
    _refuse_an_exclusive_or,
    _refuse_unsupported_form,
)

if TYPE_CHECKING:
    import builtins
    from typing import NoReturn, Self

    from gaspatchio.column.condition_expression import ConditionExpression
    from gaspatchio.column.expression_proxy import ExpressionProxy


{namespaces}

class _GeneratedProxySurface:  # noqa: PLW1641 - comparisons build predicates
    """Methods whose public spelling is declared by the operation set.

    Concrete proxies inherit this generated family so runtime behavior,
    signatures, and documentation remain sourced from one declaration.
    """

{methods}
{operators}
    def __bool__(self) -> NoReturn:  # noqa: PLE0304 - the refusal is the answer
        """Refuse ``and``, ``or``, ``not`` and a bare ``if`` on this value.

        A column answers per policy, and on a projection per period, so
        there is no single true or false for Python's Boolean keywords to
        read. ``af.a and af.b`` would quietly evaluate to ``af.b`` alone and
        carry every policy the first test excluded. The element-wise
        operators ``&``, ``|`` and ``~`` combine the tests, and
        ``when(...).then(...).otherwise(...)`` chooses the value.
        """
        _refuse_a_truth_value()

    def __xor__(self, other: object) -> NoReturn:
        """Refuse ``^``: the vocabulary's logical operations are ``&``, ``|``, ``~``.

        Python offers ``^`` to a column only as a bitwise exclusive-or of
        whole numbers. One test or the other but not both is the two tests
        compared, ``(af.a > 1) != (af.b > 2)``, which the vocabulary holds.
        """
        del other
        _refuse_an_exclusive_or()

    def __rxor__(self, other: object) -> NoReturn:
        """Refuse ``^`` with this value on its right, as ``__xor__`` does.

        ``True ^ af.in_force`` reaches here; it is the same exclusive-or,
        which the vocabulary does not hold, and the same two tests compared.
        """
        del other
        _refuse_an_exclusive_or()

    def __pos__(self) -> Self:
        """Answer ``+af.x`` with ``af.x`` itself: a sign kept changes no value.

        Nothing is recorded: the value is the operand, so the line reads as
        the column it names, as ``+x`` reads in a spreadsheet formula.
        """
        return self

    @property
    def str(self) -> StringNamespace:
        """Parse dates through the declared string operation.

        Calendar dates can arrive as text in a model-point extract or as
        one list of claim dates per policy.

        !!! note "When to use"
            Parse those dates before calculating policy durations.

        Examples
        --------
        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame({{"issue_date": ["2025-01-31"]}})
        af.parsed = af.issue_date.str.to_date("%Y-%m-%d")
        print(af.collect()["parsed"][0])
        ```

        ```text
        2025-01-31
        ```
        """
        return StringNamespace(self)

    @property
    def list(self) -> ListNamespace:
        """Read or reduce each policy's own projection values.

        Sum, mean, minimum and maximum fold the periods inside each row.
        Get selects one stored position: zero is first and minus one is last.
        Different policies may carry different numbers of periods.

        !!! note "When to use"
            Calculate a policy total or read its value at a rebase position.

        Examples
        --------
        ```python
        from gaspatchio import ActuarialFrame

        af = ActuarialFrame({{"claims": [[10.0, 20.0], [5.0]]}})
        af.total_claims = af.claims.list.sum()
        print(af.collect()["total_claims"].to_list())
        ```

        ```text
        [30.0, 5.0]
        ```
        """
        return ListNamespace(self)


__all__: list[str] = []
# jscpd:ignore-end  # noqa: ERA001
'''


def write_generated_proxy(output: Path = OUTPUT) -> None:
    """Write the complete generated surface, creating a missing artifact."""
    output.write_text(render_generated_proxy(), encoding="utf-8")


def main() -> int:
    """Write the generated surface, or report drift under ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the checked-in proxy surface is out of date",
    )
    args = parser.parse_args()
    expected = render_generated_proxy()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current == expected:
            return 0
        sys.stderr.write(
            "gaspatchio/column/_generated_proxy.py is out of date; run "
            ".venv/bin/python scripts/generate_proxy_surface.py\n"
        )
        return 1
    write_generated_proxy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
