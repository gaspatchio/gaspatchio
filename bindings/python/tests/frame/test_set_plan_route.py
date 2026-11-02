# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The package sets a frame's query plan through ``_set_plan``, and only there.

``af._df = plan`` is the route a model's own write takes, past the frame's
recording doors. The frame reads every write that comes that way for the
columns it defined over the frame's own account of them, so a door of the
framework's own that set the plan the same way would be read as a model's
write: a scenario axis handed its whole plan reads as a rewrite of every
column it carries. Every door sets the plan with ``_set_plan``; this holds the
package, the second engine and the viewer to it.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Classes that keep a ``_df`` of their own, which is not a frame's plan: an
# aggregation's one-row result and an assumption table's processed data.
_OWN_DF: frozenset[tuple[str, str]] = frozenset(
    {
        ("gaspatchio/frame/base.py", "_AggregationResult"),
        ("gaspatchio/assumptions/_api.py", "Table"),
    }
)


class _PlanWrites(ast.NodeVisitor):
    """Find each write to an attribute ``_df`` in one module, by line.

    An assignment, augmented or annotated, a tuple target, and the same
    attribute set by name through ``setattr`` or ``__setattr__``. A write
    inside a class that keeps a ``_df`` of its own is not a frame's plan.
    """

    def __init__(self, where: str) -> None:
        self.where = where
        self.classes: list[str] = []
        self.found: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._note(node, target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._note(node, node.target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._note(node, node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        named = (isinstance(func, ast.Name) and func.id == "setattr") or (
            isinstance(func, ast.Attribute) and func.attr == "__setattr__"
        )
        if (
            named
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "_df"
        ):
            self._record(node)
        self.generic_visit(node)

    def _note(self, node: ast.stmt, target: ast.expr) -> None:
        if isinstance(target, ast.Tuple | ast.List):
            for element in target.elts:
                self._note(node, element)
        elif isinstance(target, ast.Attribute) and target.attr == "_df":
            self._record(node)

    def _record(self, node: ast.stmt | ast.expr) -> None:
        owner = self.classes[-1] if self.classes else None
        if (self.where, owner) not in _OWN_DF:
            self.found.append(f"{self.where}:{node.lineno}")


def _writes_to_df(root: Path, label: Path) -> list[str]:
    """Return every write to an attribute ``_df`` under ``root``, by line."""
    found: list[str] = []
    for source in sorted(root.rglob("*.py")):
        visitor = _PlanWrites((label / source.relative_to(root)).as_posix())
        visitor.visit(ast.parse(source.read_text(), filename=str(source)))
        found.extend(visitor.found)
    return found


def test_the_package_sets_a_frame_s_plan_through_set_plan() -> None:
    """``af._df = ...`` is the route a model's own write takes, and only that.

    The setter reads every write that passes through it for columns it
    overwrote. A door of the framework's own that set the plan that way would
    be read as a model's write -- a with_scenarios frame handed its whole plan
    reads as a rewrite of every column -- so the package sets a frame's plan
    with ``_set_plan`` and nowhere else.
    """
    package = Path(__file__).resolve().parents[2]
    roots = {
        package / "gaspatchio": Path("gaspatchio"),
        package.parents[1] / "engines" / "jax" / "src": Path("engines/jax/src"),
        package.parents[1] / "viewer" / "python": Path("viewer/python"),
    }
    assert all(root.is_dir() for root in roots), roots

    writes = [
        hit for root, label in roots.items() for hit in _writes_to_df(root, label)
    ]

    assert writes == [], (
        "Set a frame's plan with frame._set_plan(plan), not frame._df = plan: "
        "the _df setter is the route a model's own write takes, and it reads "
        "every write for columns it overwrote. Found: " + ", ".join(writes)
    )
