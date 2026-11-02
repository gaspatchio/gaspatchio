# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every method the proxy stubs declare has to exist at runtime.

``column_proxy.pyi`` and ``expression_proxy.pyi`` are what an editor reads
when it completes ``af.pols_if.``, so a name declared there is a promise
that calling it works. stubtest cannot keep that promise here: its
allowlist excuses every member of ``ColumnProxy`` and ``ExpressionProxy``
wholesale, and a stub-only method is excused along with the rest. This is
the narrow check that survives the allowlist.
"""

import ast
from pathlib import Path

import pytest

import gaspatchio  # noqa: F401 -- import for the side effect: registers the accessors
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.registry import _ACCESSOR_REGISTRY

_STUBS = Path(__file__).parent.parent / "gaspatchio" / "column"


def _declared_methods(stub_path: Path, class_name: str) -> list[str]:
    """Return the method names declared under *class_name* in *stub_path*."""
    tree = ast.parse(stub_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
    msg = f"{stub_path.name} declares no class {class_name}"
    raise AssertionError(msg)


@pytest.mark.parametrize(
    ("stub_name", "cls"),
    [
        ("column_proxy.pyi", ColumnProxy),
        ("expression_proxy.pyi", ExpressionProxy),
    ],
)
def test_stub_methods_resolve_at_runtime(stub_name: str, cls: type) -> None:
    """Every name the stub declares is reachable on a proxy.

    The check is ``getattr`` on the **class**, not on an instance:
    ``__getattr__`` is defined for instances, so an instance lookup would be
    answered by the dynamic accessor path rather than by the attribute
    itself, and this test would then be measuring the fallback instead of
    the class. The declared operations are defined on the generated surface
    both proxies inherit, so they still pass.

    A handful of names resolve only through that dynamic path -- the
    accessor namespaces reached by name from ``_ACCESSOR_REGISTRY``, which
    is why they are not class attributes. Those are accepted only when the
    registry really holds a column accessor under the name, so the
    exception is checked rather than excused.
    """
    declared = _declared_methods(_STUBS / stub_name, cls.__name__)
    assert declared, f"{stub_name} declares no methods -- parse failure?"

    unresolved = [name for name in declared if not hasattr(cls, name)]
    phantom = [
        name for name in unresolved if "column" not in _ACCESSOR_REGISTRY.get(name, {})
    ]

    assert not phantom, (
        f"{stub_name} declares {phantom} on {cls.__name__}, which resolves "
        f"neither as an attribute of the class nor as a registered column "
        f"accessor. An editor offers it and the call raises AttributeError."
    )
