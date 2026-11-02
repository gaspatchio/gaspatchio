# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Census tripwire for expression-producing sites in ``gaspatchio``.

``gaspatchio`` builds Polars expressions from many places: operator dunders on
``ColumnProxy``/``ExpressionProxy``, the ``when``/``then``/``otherwise`` chain,
accessor methods (``projection``, ``finance``, ``date``, ``excel``, ...),
assumption-table lookups, the rollforward compiler, and a handful of raw
``pl.Expr`` construction points inside ``frame/``. Today those sites are
scattered across the package by design — each accessor owns its own
lowering. A planned rewrite consolidates expression construction behind a
single ``frame/lowering/`` package.

**That rewrite does not empty these lists, and this docstring claimed until
2026-09-07 that it would.** The target it named — "everything in the
allowlist below should have emptied out" — is unreachable, which is worse
than merely wrong: a ratchet aimed at it can never say when the work is
done. Most of what is listed is permanent, for four reasons and not one of
them a defect:

- **Surface.** The public name a user types.
  ``af.qx.projection.cumulative_survival()`` needs a
  ``def cumulative_survival`` where the user reaches it, wherever its Polars
  ends up living. Moving that body to ``frame/lowering/`` empties the file's
  *pattern* entry and leaves the *name* entry exactly where it was, because
  both name-keyed structures below are keyed on the name. This is why the
  two of them cannot fall by consolidating construction at all, and why
  neither has a single stale entry: they are exact censuses of a live
  surface, which ``test_no_entry_names_a_file_or_a_def_that_is_gone`` holds
  them to. ``accessors/projection.py`` is the proof — the fully consolidated
  accessor, with nine ``emit.call`` sites and no raw Polars left in it,
  still costs twenty name entries.
- **Ingress.** It *mints* an op-node rather than lowering one: the operator
  dunders, ``when``/``then``/``otherwise``, ``Table.lookup``, the
  rollforward builder verbs. A lowering is reached *by* an op; ingress is
  what makes one, so moving ingress into ``frame/lowering/`` inverts the
  direction of the whole layer.
- **Not an expression at all.** ``assumptions/_api.py`` contributes twenty
  names below and exactly one of them, ``lookup``, declares an
  expression-shaped return type; the other nineteen are ``Table``'s
  construction and metadata API. ``frame/graph/calc_graph.py`` contributes
  fourteen and none of them does — that is the calculation-graph query and
  export API, and ``node_values``, which answers with the frame's own
  columns paired to node ids for the engine seam's reference adapter. Both
  are here because family membership, not return type, is what puts a file in
  scope, which is a deliberate choice defended in the accessor section below.
- **Escape.** The deliberate door out: ``map_elements``, ``map_batches``,
  ``wrap``.

What genuinely burns down is the rest: raw construction whose body could be
the value of ``LOWERINGS["<op>"]``. That is what these ceilings measure
progress against. Zero would describe a package in which
``af.qx.projection.cumulative_survival`` is not a name anybody can type.

This module is a grep-driven tripwire, not a design document: it walks
``gaspatchio/`` looking for the same handful of literal patterns that mark an
"expression-producing site" (raw ``pl.col(``/``pl.when(``/``.map_batches(``/
``register_plugin_function(`` calls, operator-dunder definitions,
accessor/lookup/rollforward method definitions, expression-returning method
definitions anywhere in the package, and ``ActuarialFrame``/``__class__``
construction calls) and fails if one shows up somewhere that isn't already
accounted for.

**The six raw patterns read code, not prose.** Strings and comments are
blanked before they run (``_without_prose``). They were not, until
2026-09-07, and this project requires a runnable ``ActuarialFrame(`` example
in every public method's docstring — so 39 of the 86 ``ALLOWLIST`` entries of
that day, 45% of the list, existed to account for documentation. Twenty of
``frame_construction``'s twenty-six had no executable match at all;
``frame/base.py`` had 48 raw matches and one line of code, its own ``class``
statement. Eleven more entries matched nothing whatever, their sites long
gone: the census fails only on *unlisted* sites, so a burn-down it had
already earned was invisible to it. The blanking is scoped to these six
patterns and stops there — the two def-keyed checks read the source as
written, because this codebase annotates most accessor returns with a
*quoted* forward reference (``-> "ExpressionProxy":``) and blanking strings
before that check would drop ten real expression-producing methods.

The allowlist below is keyed on **file path, pattern category, and — for two
categories — method name too, never on line number**: refactoring a line
within an already-known file is not a tripwire event; a *new file* (or an
existing file gaining a *new pattern category*, or a *new named method*, it
didn't have before) is. This keeps the tripwire cheap to maintain across
ordinary refactors while still catching the failure mode it exists for: a
calculation somewhere in the package starts building Polars expressions
directly instead of going through the reviewed accessor/proxy surface (or,
once it exists, ``frame/lowering/``).

One tripwire here is not grep-driven, and it is here because it is the same
claim one step on. The scan says every place that builds an expression is a
place somebody reviewed; ``test_every_registered_lowering_is_classified``
says every operation those places can build is an operation the exported
calculation graph can account for. It reads the lowering registry and the
execution-tier table and fails on the difference, so an operation that
lands with a lowering and no tier is caught at the line that registered it
rather than by whoever first tries to run the model somewhere else. Both
imports are made inside the test: this module is importable on its own, and
importing the package it scans at module scope would be odd in a file whose
subject is that package's source text.

A third asks the question the other two cannot. Both of them are satisfied
by an allowlist entry, so a site that is listed is a site nobody has to
think about again, and the lists could sit at their present size forever
with the suite green. ``test_allowlist_totals_do_not_grow`` pins each
structure's entry count against ``ALLOWLIST_CEILINGS``: the lists may
shrink freely, and can only grow in a commit that also raises the number,
where the raise is visible in the diff. That makes the size of the surface
this module describes the thing the suite enforces, not just its shape.

Two directories are exempt outright, by path prefix rather than by listing
every file within them:

- ``frame/lowering/`` — the future home for all raw expression construction.
  Once it exists, everything that moves there should *stop* needing an
  allowlist entry at its old location and should never need one here.
- ``tutorials/`` — worked example models shipped for documentation. These
  legitimately use raw Polars as advanced/escape-hatch usage in example
  *model* code, the same way a user's own model might; new tutorials are
  added routinely and are not part of the framework's own DSL implementation.

## Accessor/lookup/rollforward method definitions (a second, name-keyed check)

The six patterns above catch raw expression construction *by what a line of
code does* (calls ``pl.col(``, defines a dunder, ...). None of them catch a
*new named method* that is itself expression-producing purely by composing
already-reviewed proxy calls — e.g. a new accessor method whose entire body
is ``return self.previous_period() + self.next_period()``. That method
never touches ``pl.col``/``pl.when``/a dunder/an ``ActuarialFrame(`` call, so
it is invisible to every pattern above, in an already-allowlisted file *or*
a brand-new one. Accessor methods, table lookups, and rollforward entry
points are exactly the framework's documented, actively-growing extension
surface (see ``gaspatchio-extending``'s accessor pattern), so this blind
spot matters more there than elsewhere.

``ACCESSOR_METHOD_ALLOWLIST`` closes it with a mechanism scoped to files "in
the accessor/lookup/rollforward family" and keyed on
``(file, public method/function name)``:

- **Which files are "in the family"** is decided structurally, three ways,
  so a *brand-new* file is caught the same as an existing one:
  1. Any file containing ``@register_accessor(`` — the decorator every
     ``projection``/``finance``/``date``/``excel`` accessor class uses to
     register itself (and the only way a *new* accessor namespace becomes
     reachable as ``af.column.<name>``/``af.<name>``, so a future one is
     caught automatically without adding a new marker here).
  2. Any file under the retired ``column/namespaces/`` path. Final dispatch
     removal deletes that package; keeping the structural marker makes a
     future reflective namespace proxy visible the moment it is reintroduced.
  3. An explicit, hand-curated list (``_ACCESSOR_FAMILY_FILES``) for the
     three groups that predate both mechanisms above and share no common
     base class or decorator with each other or with the accessor family:
     ``Table`` (assumptions/_api.py), the rollforward builder/compiler/
     registry modules, and the four proxy classes whose escape-hatch
     methods (``map_elements``, ``map_batches``, ``wrap``, ...) sit
     alongside their already-tracked operator dunders.
- **Within an in-scope file**, every *public* ``def`` (no leading
  underscore — this excludes both private helpers and every dunder in one
  rule, since dunders start with ``__``; the arithmetic/comparison/logical
  ones already have their own category above) is a name that must appear in
  that file's allowlist entry, whether it is a method on a class or one of
  the rollforward module's free functions (``compile_rollforward``,
  ``register``, ...) — *regardless of what it returns*. This is why the
  rollforward builder verbs (``_StateHandle.add``/``.charge``/``.grow``/...,
  which return ``_StateHandle`` for chaining, not an expression directly)
  are still covered: family membership, not return type, is the key here.
- **Granularity is (file, name), not (file, class, name)**: two different
  classes in the same file sharing a method name (several rollforward
  ``Pass`` classes each define ``name``/``apply``) collapse to one entry.
  A new class reusing an already-allowlisted name in the same file will not
  trip. This trades a small amount of precision for staying simple and
  line-churn-proof, matching the file/pattern/name-keyed rule above.

"Regardless of what it returns" reads like sloppiness, so it was attacked on
2026-09-07 and held. The narrowing on the table was the *positive* one: inside
a family file, track a public ``def`` only when its own return-type annotation
names one of the five expression-shaped types below -- the same evidence
``EXPR_RETURNING_DEF_ALLOWLIST`` runs on. It would have taken
``ACCESSOR_METHOD_ALLOWLIST`` from 147 entries to 73. Seven shapes were written
into two family files -- ``accessors/projection.py`` and
``rollforward/_builder.py`` -- and each scanned under both rules. Two were
caught by the narrowed rule, and they are the controls: a composed method
annotated ``-> "ExpressionProxy"``, and one returning a ``pl.Expr`` that a
private helper built. **Five escaped it, and the package-wide check below
caught none of them independently:**

1. the docstring's own example above -- ``return self.previous_period() +
   self.next_period()`` -- with no return annotation;
2. the same body annotated through a module-level alias that never spells any
   of the five names (``rollforward/_builder.py`` already declares
   ``ExprLike: TypeAlias = pl.Expr | ColumnProxy | ExpressionProxy``, so the
   idiom is in the codebase, not invented for the attack);
3. the same body annotated ``-> Any``;
4. a method whose expression-ness exists only at run time, annotated
   ``-> object``, returning whatever a named verb hands back;
5. **a new rollforward builder verb** -- a ``_StateHandle`` method that mints
   an op node exactly as ``add`` and ``subtract`` beside it do, and returns
   ``_StateHandle`` for chaining. This is not a synthetic shape: it is the
   family the bullet above names, and under the narrowing all thirteen of its
   verbs stop being tracked at all.

Four of the five cost nothing at the other ratchets either -- (2), (3), (4)
and (5) each left ruff 0.16.3 reading 1716, the package total that day,
unchanged, in the file they were driven in ((3) in
``column/expression_proxy.py``, whose blanket header already suppresses
``ANN401``). Only (1) raised it, by one ``ANN201``.

So the broad net is **load-bearing, not redundant**: it is the only thing in
the repository that sees any of those five. Narrowing it would have traded a
working tripwire for a smaller number.

The *inverse* narrowing was measured too, on 2026-09-08, because the sentence
above first said the positive rule was the only narrowing a text scan can
express -- a claim about every expressible narrowing, rather than about the one
tested. The inverse rule tracks every public ``def`` **except** those whose own
annotation *provably* names something that is not an expression: a scalar, a
Polars frame/series type, or a container all of whose parameters are themselves
provable, with a quoted forward reference parsed through. It is expressible,
and it keeps all seven shapes above caught -- none of "no annotation",
``ExprLike``, ``Any``, ``object`` or ``_StateHandle`` is provable.

It is still not worth taking, and the reasons are not "a text scan cannot
express it". Measured on this working tree, it removes **16 of the 147** and
**0 of the 113** -- 18 of the 147 if ``-> None`` counts as provable -- against
the 74 the positive rule offered, and it does the job unevenly: from
``assumptions/_api.py`` it drops ``source_sha`` while keeping ``dimensions``,
``schema`` and ``extend``, which are exactly as much "not an expression". It
also loses to a shape neither rule can see: a builder verb annotated
``-> bool`` that mints an op node as a *side effect* and reports success. The
op never passes through the return type, so no rule keyed on return types --
positive or inverse -- can see it, which is what "regardless of what it
returns" is for. Both rules inherit the annotations they read, and those are
unverified here: ``[tool.mypy] strict = true`` is configured in
``bindings/python/pyproject.toml`` and CI does run ``mypy gaspatchio``, but
only against a ceiling that may not rise. It reports 121 errors in 31 files on
this working tree, and a ceiling at 121 says nothing about whether the
annotation this module has just read is one of them.

Do not narrow it without re-running that attack and beating it.

## Expression-returning method definitions, anywhere in the package (a third check)

The family mechanism above only looks inside files it already recognises as
accessor/lookup/rollforward-shaped. Review found real files that are just as
expression-producing but fit none of the three structural markers:
``Schedule`` (``schedule/_schedule.py``) has seven ``*_expr`` methods that
hand back ``ProxyAwareExpr.wrap(...)`` through a private ``_emit`` helper —
the identical convention ``Table.lookup()`` and the rollforward egress
methods use — and ``Curve`` (``curves/_curve.py``) has public methods
(``spot_rate``, ``discount_factor``) that return a bare ``pl.Expr`` on a
proxy/``Expr`` input. Neither uses ``@register_accessor``, neither lives
under the retired ``column/namespaces/`` path, and neither is a good fit for
the explicit list above (they're not accessors, a table, or the rollforward
compiler — they're their own, independent families). Chasing every such
family by name, one at a time, only shrinks the blind spot to whichever
family review catches *next*.

``EXPR_RETURNING_DEF_ALLOWLIST`` instead runs on **every file in the
package** (still subject to ``EXEMPT_PREFIXES``) and keys on the thing that
is actually true of every site this whole module cares about: **a
genuinely expression-producing function or method declares one of the five
expression-shaped types as its own return type** — ``pl.Expr``,
``ExpressionProxy``, ``ProxyAwareExpr``, ``ConditionExpression``, or
``ConditionalProxy`` (exactly the types that mark a definition as
expression-producing rather than frame-producing, string-producing, or
anything else). No family membership, base class, or decorator needs to be
recognised in advance; the function's own signature is the evidence.

- **Matching the annotation, not just the line**: a return-type annotation
  sits after the parameter list's closing ``)``, which is often many lines
  below ``def name(`` for a multi-parameter or long-Union signature (both
  are common here). The pattern anchors on ``-> ... TARGET ... :`` and lets
  the ``...`` span newlines, then a second pass finds which ``def`` that
  annotation belongs to by taking the *nearest preceding* ``def`` in the
  file — public or private.
- **A match whose true owner is private is discarded, not reattributed**:
  if the nearest preceding ``def`` starts with an underscore (a private
  helper, or a dunder), the match is dropped rather than credited to
  whatever *public* name happens to precede it. Early drafts of this
  pattern attributed a private helper's own ``-> pl.Expr`` return to an
  unrelated earlier public method purely because it was the nearest name
  the (public-only) search could see — correct in the sense that the
  *file* still needed an allowlist entry, wrong about *which name*, and
  two genuinely different private sites sharing the same nearest public
  neighbour would have collapsed into one allowlist entry, silently
  covering a second, different new one. Searching for *any* preceding
  ``def`` first, then filtering, fixes both.
- **Known gap, stated rather than hidden**: this check is exactly as good
  as the codebase's own declared return types. A method that is genuinely
  expression-producing but whose signature is annotated with something
  that doesn't textually name one of the five tracked types (``Any``,
  ``object``, or a type alias/``TypeVar`` that itself resolves to one of
  them without spelling it out) will not be caught here — though the
  project's own type-hint standard (every function's return type must be
  explicit and non-``Any``) makes writing such a method, by accident,
  unusual. This is a narrower gap than "an unrecognised family": it no
  longer matters whether the site lives in a recognised family, a brand
  new file, or an existing file with no accessor shape at all — only
  whether its own signature tells the truth.
"""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

# This file lives at bindings/python/tests/graph/census.py; the package
# under test is bindings/python/gaspatchio.
PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "gaspatchio"

# Path prefixes (POSIX-style, relative to the scanned root, no leading
# slash) that are exempt from the tripwire regardless of what they contain.
EXEMPT_PREFIXES: Final[tuple[str, ...]] = (
    # These unchanged authoring bodies formerly lived below the
    # lowering exemption. Keep their existing coverage while naming their owner;
    # this relocation earns no census reduction or new semantic allowance.
    "_authoring/emit.py",
    "_authoring/escape.py",
    "_authoring/_native_docs.py",
    "frame/lowering/",
    "tutorials/",
)

# Operator dunder names that, when defined, mark a genuine expression-
# producing site on a proxy-like class (arithmetic, comparison, logical,
# unary). A handful of unrelated classes define equality/hash for plain
# value semantics and happen to match the same syntactic pattern — those
# are handled via the allowlist below, not by narrowing this pattern,
# because a text scan cannot see return types.
_DUNDER_NAMES: Final[tuple[str, ...]] = (
    "add",
    "radd",
    "sub",
    "rsub",
    "mul",
    "rmul",
    "truediv",
    "rtruediv",
    "floordiv",
    "rfloordiv",
    "mod",
    "rmod",
    "pow",
    "rpow",
    "and",
    "rand",
    "or",
    "ror",
    "xor",
    "rxor",
    "eq",
    "ne",
    "lt",
    "le",
    "gt",
    "ge",
    "neg",
    "pos",
    "abs",
    "invert",
)

PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "raw_pl_col": re.compile(r"pl\.col\("),
    "raw_pl_when": re.compile(r"pl\.when\("),
    "raw_map_batches": re.compile(r"\.map_batches\("),
    "raw_register_plugin_function": re.compile(r"register_plugin_function\("),
    "operator_dunder": re.compile(r"def __(?:" + "|".join(_DUNDER_NAMES) + r")__\("),
    "frame_construction": re.compile(r"\bActuarialFrame\(|\.__class__\("),
}

# category -> relative file paths (POSIX separators, relative to the
# scanned root) where that category's pattern is already known to appear in
# *code*: strings and comments are blanked before these patterns run (see
# _without_prose), so a docstring example is not a match and an entry here
# means executable code in that file matches that category.
ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "raw_pl_col": frozenset(
        {
            # The one place a frame-level column NAME becomes a reference to
            # that column: `column_expr` resolves the string designator the
            # date and finance frame verbs take. Shared by all of them so the
            # rule is written once, which is the direction this census wants.
            "accessors/date.py",
            "accessors/projection_frame.py",
            "assumptions/_api.py",
            "assumptions/_dimensions.py",
            "assumptions/_strategies.py",
            "assumptions/_utils.py",
            "cli.py",
            "frame/base.py",
            # Not a model expression at all: one window this build writes
            # itself, serialized so an export can ask whether the engine
            # still names windows the way this build reads them. Built out
            # of the engine's own vocabulary rather than through the
            # lowering, deliberately, because what it has to be evidence of
            # is what the engine does.
            "frame/graph/calc_graph.py",
            # Not a model expression either: the two reads that find a
            # selected row again in the frame the model handed back, by the
            # stamp this export put on the book. They are over the export's
            # own scaffolding column and the policy-id column, they build
            # no Col leaf, and doing them row by row in Python would be a
            # scan of the whole book per entry of the axis.
            "frame/graph/row_identity.py",
            "frame/graph/value_extractor.py",
            "runner.py",
            "scenarios/_aggregated.py",
            "scenarios/_aggregators.py",
            # The shared vector fold owns the former driver expression.
            "scenarios/_fold.py",
            "scenarios/_period_aggregators.py",
            "scenarios/_period_sketch.py",
            "scenarios/_stack.py",
            "scenarios/_with_scenarios.py",
            "scenarios/shocks.py",
        }
    ),
    "raw_pl_when": frozenset(
        {
            # The within-scenario ``sum`` answers null for a scenario whose
            # every value is missing, where Polars' own sum answers 0.0. It is
            # a driver reduction over the projected frame, not a model
            # expression, in the file already allowlisted for raw pl.col.
            "scenarios/_aggregators.py",
            "scenarios/shocks.py",
        }
    ),
    "raw_map_batches": frozenset(
        {
            "column/column_proxy.py",
        }
    ),
    "raw_register_plugin_function": frozenset(),
    "operator_dunder": frozenset(
        {
            "column/_generated_proxy.py",
            "column/condition_expression.py",
            "column/proxy_aware_expr.py",
            # DayCount.__eq__ is type-based value equality, not an expression
            # producer -- allowlisted because a text scan can't see the return
            # type, only the def line.
            "schedule/_day_count.py",
        }
    ),
    "frame_construction": frozenset(
        {
            "cli.py",
            # The one executable match in this file is its `class
            # ActuarialFrame(_CalculationLogMixin):` statement; the other 47
            # are the docstring examples the pattern used to count.
            "frame/base.py",
            # The scenario door builds the frame the plan is run over --
            # twice, once for the graph and once for the plan's own fold --
            # for the reason `scenarios/_aggregated.py` does: a driver that
            # runs a model needs a frame to hand it, and the book arrives as
            # a DataFrame off the disk.
            "scenarios/_graph_export.py",
            "runner.py",
            "scenarios/_aggregated.py",
            "scenarios/_spill.py",
            "scenarios/_with_scenarios.py",
        }
    ),
}


# Files in the accessor/lookup/rollforward family that share no common base
# class or registration decorator with each other, so they can't be found
# structurally through @register_accessor.
# See the module docstring's "Accessor/lookup/rollforward method
# definitions" section for what "in the family" means and why these three
# groups are listed by hand.
_ACCESSOR_FAMILY_FILES: Final[frozenset[str]] = frozenset(
    {
        "frame/graph/calc_graph.py",
        "assumptions/_api.py",
        "assumptions/_data.py",
        "rollforward/_data.py",
        "rollforward/_builder.py",
        "rollforward/_compile.py",
        "rollforward/_compiled.py",
        "rollforward/_registry.py",
        "rollforward/_passes.py",
        "column/column_proxy.py",
        "column/expression_proxy.py",
        "column/condition_expression.py",
        "column/proxy_aware_expr.py",
    }
)

# The reflective namespace-proxy package is gone. Keep its former path as a
# tripwire: a new file there is in-scope without needing a name added to
# _ACCESSOR_FAMILY_FILES.
_ACCESSOR_FAMILY_PATH_PREFIXES: Final[tuple[str, ...]] = ("column/namespaces/",)

# The accessor-registry decorator: any file using it defines a
# projection/finance/date/excel-style accessor, and any *future* accessor
# registered the same way is caught automatically, in a brand-new file,
# without adding a new marker here.
_REGISTER_ACCESSOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"@register_accessor\(")

# A public def at any indentation: a method on a class, or one of the
# rollforward module's free functions (`compile_rollforward`, `register`,
# `plugin_expr_for`, ...). Requiring the name to start with a letter
# excludes both private helpers (`_build_schedule`) and every dunder
# (`__init__`, `__getitem__`, the arithmetic/comparison set) in one rule --
# the arithmetic/comparison/logical/unary dunders already have their own
# category above, and the rest (`__init__`, `__getitem__`, `__repr__`, ...)
# are Python-mandated protocol methods, not the "add a new named verb"
# surface this category targets.
_PUBLIC_DEF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*(?:async )?def ([a-zA-Z][a-zA-Z0-9_]*)\(", re.MULTILINE
)

# Same shape as _PUBLIC_DEF_PATTERN but also matches private/dunder names.
# Used only to find which `def` a return-type annotation truly belongs to
# (see _expr_returning_def_names) -- never to decide what gets tracked.
_ANY_DEF_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*(?:async )?def ([a-zA-Z_][a-zA-Z0-9_]*)\(", re.MULTILINE
)

# The five expression-shaped return types that mark a definition as
# expression-producing. A def whose own return-type annotation names one of
# these is a site, regardless of which file, class, or family it lives in.
_EXPR_RETURN_TYPE_NAMES: Final[tuple[str, ...]] = (
    r"pl\.Expr",
    "ExpressionProxy",
    "ProxyAwareExpr",
    "ConditionExpression",
    "ConditionalProxy",
)

# Matches "-> ... TARGET ... :" -- the closing colon of a def's return-type
# annotation. `[^:]*` (not `.`) deliberately spans newlines, since a
# multi-parameter signature pushes "-> Type:" onto its own line, and a long
# Union return type can itself wrap across lines.
_RETURN_ANNOTATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"->[^:]*?\b(?:" + "|".join(_EXPR_RETURN_TYPE_NAMES) + r")\b[^:]*:"
)

# file -> every public method/function name already known for that file
# under ACCESSOR_METHOD_ALLOWLIST's family-membership rule (every public
# def, any return type). Built by running the pattern above against the
# real package and recording its output, then reviewing each name once. A
# name not in its file's set (including a file not in this dict at all) is
# a new, unreviewed expression-producing site.
ACCESSOR_METHOD_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "accessors/date.py": frozenset(
        {"add_duration", "create_timeline", "months_between", "to_period"}
    ),
    "accessors/excel.py": frozenset(
        {
            "days",
            "edate",
            "eomonth",
            "from_excel_serial",
            "irr",
            "norm_s_dist",
            "pv",
            "round",
            "yearfrac",
        }
    ),
    "accessors/finance.py": frozenset(
        {"compound", "discount", "discount_factor", "present_value", "to_monthly"}
    ),
    "accessors/projection.py": frozenset(
        {
            "accumulate",
            "at_period",
            "broadcast_to_periods",
            "cumulative_survival",
            "next_period",
            "previous_period",
            "prospective_value",
            "remaining_sum",
            "with_period",
            "with_periods",
        }
    ),
    "accessors/projection_frame.py": frozenset(
        {
            "anniversary_mask",
            "canonical_form",
            "contract_boundary",
            "is_in_force",
            "period_dates",
            "rollforward",
            "set",
            "source_sha",
            "t_years",
            "year_fractions",
        }
    ),
    "assumptions/_api.py": frozenset(
        {
            "canonical_form",
            "describe",
            "dimension_values",
            "dimensions",
            "extend",
            "fingerprint",
            "from_scenario_files",
            "from_scenario_template",
            "from_shocks",
            "get_table_metadata",
            "list_tables",
            "list_tables_with_metadata",
            "lookup",
            "metadata",
            "schema",
            "source_sha",
            "storage_mode",
            "with_shock",
        }
    ),
    "assumptions/_data.py": frozenset({"validate_lookup", "to_dataframe", "name"}),
    "column/column_proxy.py": frozenset(
        {
            "captures",
            "date",
            "excel",
            "finance",
            "increments",
            "map_batches",
            "map_elements",
            # The named escape: it hands back the escape object rather than
            # an expression, and every expression reached through it is
            # built in _authoring/escape.py, under the exempt prefix.
            "polars_native",
            "shape",
        }
    ),
    "column/condition_expression.py": frozenset(
        {"left_shape", "normalize_for_list_path", "right_shape", "shape"}
    ),
    "column/expression_proxy.py": frozenset(
        {"date", "finance", "kind", "polars_native", "shape"}
    ),
    "column/proxy_aware_expr.py": frozenset({"alias", "wrap"}),
    # ``af.graph``, the query surface over the folded calculation graph,
    # plus the exports: the one the CLI writes, the one that files the same
    # document with each assumption's values beside it, and the workbook
    # laid out from that document. In the family because the accessor
    # registers itself like every other one, and a new ``af.`` namespace is
    # worth a human noticing -- but nothing here produces an expression:
    # every one of these answers with node ids, holes, a hash, JSON or a file.
    "frame/graph/calc_graph.py": frozenset(
        {
            "affected",
            "dependents",
            "export",
            "export_with_sidecar",
            "fingerprint",
            "holes",
            "latest",
            "last_run",
            "node_accounting",
            "node_values",
            "precedents",
            "tiers",
            "to_excel",
            "trace",
            "unused",
            "versions",
        }
    ),
    "rollforward/_builder.py": frozenset(
        {
            "add",
            "apply",
            "at",
            "between",
            "charge",
            "deduct_nar",
            "floor",
            "grow",
            "grow_capped",
            "increment",
            "ratchet",
            "round",
            "subtract",
        }
    ),
    "rollforward/_compile.py": frozenset({"compile_rollforward"}),
    "rollforward/_compiled.py": frozenset(
        {
            "capture_slot_error",
            "expr_for",
            "increment_for",
            "plugin_expr",
        }
    ),
    "rollforward/_data.py": frozenset({"explain", "canonical_form", "fingerprint"}),
    "rollforward/_passes.py": frozenset({"apply", "apply_with_slots", "lower", "name"}),
    "rollforward/_registry.py": frozenset(
        {"has_entries", "hidden_column_name", "plugin_expr_for", "register"}
    ),
}

# file -> every def (method or free function) already known to declare one
# of _EXPR_RETURN_TYPE_NAMES as its own return type. Unlike
# ACCESSOR_METHOD_ALLOWLIST, this applies package-wide -- not gated behind
# family membership -- and is built the same way: run the pattern, record
# the output, review each name once.
EXPR_RETURNING_DEF_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    # `column_expr` is the shared frame-level name resolver (see raw_pl_col
    # above); `refuse_missing_column`/`refuse_bare_string_operand` next to it
    # return NoReturn/None and so are not expression-producing.
    "accessors/base.py": frozenset({"column_expr"}),
    "accessors/date.py": frozenset({"months_between", "to_period"}),
    "accessors/excel.py": frozenset(
        {
            "days",
            "edate",
            "eomonth",
            "from_excel_serial",
            "irr",
            "norm_s_dist",
            "pv",
            "round",
            "yearfrac",
        }
    ),
    "accessors/finance.py": frozenset(
        {"compound", "discount", "present_value", "to_monthly"}
    ),
    "accessors/projection.py": frozenset(
        {
            "accumulate",
            "at_period",
            "broadcast_to_periods",
            "cumulative_survival",
            "next_period",
            "previous_period",
            "prospective_value",
            "remaining_sum",
            "with_period",
            "with_periods",
        }
    ),
    # Mechanical output, but still the public expression surface: generation
    # changes who writes these definitions, not what the census measures.
    "column/_generated_proxy.py": frozenset(
        {
            "abs",
            "add",
            "cbrt",
            "ceil",
            "clip",
            "cum_prod",
            "cum_sum",
            "cut",
            "eq",
            "exp",
            "fill_nan",
            "fill_null",
            "floor",
            "floordiv",
            "ge",
            "get",
            "gt",
            "is_finite",
            "is_in",
            "is_infinite",
            "is_nan",
            "is_not_nan",
            "is_not_null",
            "is_null",
            "le",
            "log",
            "log10",
            "log1p",
            "lt",
            "max",
            "mean",
            "min",
            "mod",
            "mul",
            "ne",
            "neg",
            "norm_cdf",
            "pow",
            "replace",
            "reverse",
            "round",
            "round_sig_figs",
            "sign",
            "sqrt",
            "sub",
            "sum",
            "to_date",
            "to_float",
            "to_integer",
            "to_list",
            "to_text",
            "truediv",
        }
    ),
    "accessors/projection_frame.py": frozenset(
        {
            "anniversary_mask",
            "contract_boundary",
            "is_in_force",
            "period_dates",
            "t_years",
            "year_fractions",
        }
    ),
    "assumptions/_api.py": frozenset({"lookup"}),
    "column/column_proxy.py": frozenset({"map_batches", "map_elements"}),
    "column/condition_expression.py": frozenset({"normalize_for_list_path"}),
    "column/proxy_aware_expr.py": frozenset({"alias", "wrap"}),
    "curves/_curve.py": frozenset({"discount_factor", "spot_rate"}),
    "frame/base.py": frozenset({"fill_series"}),
    "functions/conditional.py": frozenset({"otherwise", "then", "when"}),
    "mortality/_mortality_table.py": frozenset({"at"}),
    "rollforward/_compiled.py": frozenset({"expr_for", "increment_for", "plugin_expr"}),
    "rollforward/_passes.py": frozenset({"lower"}),
    "rollforward/_registry.py": frozenset({"plugin_expr_for"}),
    "scenarios/_aggregators.py": frozenset({"within_expr"}),
    "scenarios/_metric.py": frozenset({"within_expr"}),
    "scenarios/_period_aggregators.py": frozenset({"within_expr"}),
    "scenarios/shocks.py": frozenset({"to_expression"}),
    # These seven are SURFACE and permanent, decided on 2026-09-08, not a
    # burn-down target. The file holds no `pl.col(`; its Polars is in
    # frame/lowering/rules/schedule.py, so what keeps the entry is the public
    # name. `Schedule` is exported in __all__ and `anniversary_mask_expr` is
    # taught by name in the level-3 tutorial: retiring one is a public-API
    # deprecation, argued on those terms, not a census clean-up.
    "schedule/_schedule.py": frozenset(
        {
            "anniversary_mask_expr",
            "contract_boundary_expr",
            "is_in_force_expr",
            "per_policy_period_count_expr",
            "per_policy_period_dates_expr",
            "period_dates_expr",
            "year_fractions_expr",
        }
    ),
}


# The size each allowlist above is allowed to be, and no larger. Measured
# with, from bindings/python:
#
#     .venv/bin/python -c "import sys; sys.path.insert(0, '');
#     from tests.graph.census import _allowlist_entry_counts as c; print(c())"
#
# Three separate numbers rather than one sum, because the three structures
# empty out on different work: ALLOWLIST as raw expression construction moves
# behind frame/lowering/, and the two name-keyed ones as the accessor surface
# and the expression-returning definitions consolidate. A single total would
# let one grow while another shrank.
#
# Read 86 / 147 / 114 on 2026-09-04. ALLOWLIST reads 47 on
# 2026-09-07: no source file moved, and no site stopped being a site. Eleven
# entries matched nothing at all and twenty-eight matched only prose, which
# the six patterns stopped counting the same day (see _without_prose). The
# other two are keyed on names, and a name survives its body moving, so
# consolidation is not expected to move them much.
#
# EXPR_RETURNING_DEF_ALLOWLIST reads 113 on 2026-09-08: `schedule/_schedule.py`
# lost its `wrapper` entry with the pass-through `_proxy_aware` decorator that
# owned it. That entry was the decorator's own nested wrapper, which earned it
# from a `-> pl.Expr` annotation. The seven `*_expr` methods it decorated are
# tracked by their own return types, were tracked that way before the removal,
# and are unchanged by it.
# Read 32 / 149 / 136 on 2026-09-09.
# Resolving a column name through the one `Col` lowering, where seven files
# each wrote it out, retires six raw entries (the seventh file keeps a second,
# different site); Excel/backend consolidation retires five more raw and
# twenty-one expression-definition entries; rollforward extraction retires
# three raw entries. Nine generated maths methods now have explicit
# expression-returning definitions; the first continuation added eleven more.
# The dispatch prerequisites add five direct methods, fourteen named operator
# aliases and five namespace methods. Generated dunders replace the two concrete
# proxy entries with one. No new exempt prefix or scan rule is needed.
# Final reflective-dispatch removal, 2026-09-09: 32 / 118 / 105. Deleting the
# dt and string proxy definitions retires 31 names from each name-keyed list;
# their generated replacements were already counted in _generated_proxy.py.
# The retired namespace path remains a tripwire and contributes no entries.
# Positional selection and checked integer conversion add two reviewed generated
# entry points on 2026-09-09. Both build Call nodes through lowering; neither
# adds raw engine construction or an exempt prefix. These are new capabilities,
# so their two expression definitions are explicit growth, not hidden debt.
#
# The named conversions to text, to floating point and to a list add three
# more on 2026-09-14, taking expression-definition entries from 107 to
# **110**. They are generated from the same declaration table as the rest of
# the proxy surface and lower under the existing exempt directory; no raw
# site, scan exception or new exempt prefix comes with them. Conversions are a
# family of named, checked operations rather than one generic cast, and this is
# what that capability costs on this ratchet.
#
# The scenario door adds one raw entry on 2026-09-19, taking ALLOWLIST from 32
# to **33**: frame/graph/scenario_door.py builds an ActuarialFrame, twice,
# because a driver that runs a model needs a frame to hand it and the book
# arrives off the disk as a DataFrame -- the same reason scenarios/_aggregated
# .py and runner.py are already on this list. It adds no expression site: the
# door builds no Polars expression of its own, and nothing in it is a new
# named method or a new definition that returns one, so the other two ceilings
# hold. The door is a deliberate capability, and this is what it costs here.
#
# Selection identity adds one raw entry on 2026-09-20, taking ALLOWLIST from 33 to
# **34**: frame/graph/row_identity.py filters the finished frame twice -- by
# the export's own row stamp and, where the model did not hand it back, by
# the policy-id column -- to find the row a selection named. Neither is a
# model expression: they are over a scaffolding column this export invented
# and over an identifier column, and the alternative is a Python scan of the
# book once per entry of the axis. It adds no expression site, no named
# accessor method and no definition that returns an expression, so the other
# two ceilings hold. It answers a finding of the external review of 2026-09-20.
#
# The engine seam adds one accessor-method entry on 2026-09-21, taking
# ACCESSOR_METHOD_ALLOWLIST from 118 to **119**:
# ``GraphExporter.node_values`` is the public pairing of node id to the values
# the frame finished holding, which the seam's reference adapter reads instead
# of calling three private methods of the exporter through suppressions. It
# builds no expression -- it answers with the frame's own columns, like the
# eleven names already listed for that file -- and it adds no raw construction
# and no exempt prefix, so ALLOWLIST and EXPR_RETURNING_DEF_ALLOWLIST hold. The
# file is in scope by family membership rather than by return type, which is
# the deliberate choice defended above; what this costs is one reviewed name.
# The completed-run summary adds one reviewed accessor name on 2026-09-23:
# GraphFrameAccessor.last_run reads immutable completion metadata and builds
# no expression. The accessor-family census deliberately includes such audit
# queries. This is an additive API cost (119 -> 120), not a debt reduction;
# no exemption, raw-expression count or expression-returning ceiling changes.
#
# The tier census adds one reviewed accessor name on 2026-09-30:
# GraphFrameAccessor.tiers counts each recorded calculation at the tier the
# exported document gives it, and builds no expression. It lands after the
# entries for rollforward/_collector.py came off -- a module deleted on
# 2026-09-15 that still held two names in each name-keyed list -- so the
# totals read 34 / 119 / 108, and the two name-keyed ceilings came down to
# match (120 -> 119, 110 -> 108) here and in RATCHETS.md together.
#
# The declared reversal adds one reviewed generated name on 2026-10-11:
# ListNamespace.reverse, the proxy method generated from the operation
# declaration ``list.reverse`` (section 11.1.41). It is capability growth --
# the reversal a workbook's rollback needed and could only reach through
# polars_native() -- and it builds its expression through the declared-call
# door like every other generated method, so 108 -> 109 here and in
# RATCHETS.md together; no raw site or accessor name changes.
#
# A producer's rename adds one reviewed name to each name-keyed list on
# 2026-10-13: ProxyAwareExpr.alias, which keeps the node of the read it
# renames. Polars' own alias returned a plain expression, so
# ``af.with_columns(table.lookup(age=af.age).alias("q"))`` reached the
# record as an engine fragment whose text names no table, and the model's
# fingerprint could not move when the table did (spec Annex A.2). It builds
# no expression of its own -- Polars' alias, re-wrapped with the node -- so
# 120 -> 121 and 109 -> 110 here and in RATCHETS.md together.
#
# The normal distribution function adds two reviewed names on 2026-10-19:
# the proxy method generated from the operation declaration ``norm_cdf``
# (section 11.1.12), and ExcelColumnAccessor.norm_s_dist, the Excel spelling
# that records that same node. Both build their expression through the
# declared-call door. It is capability growth -- a guarantee priced as an
# option had no N(d) outside a hand-built accessor of some 190 nested
# operations -- so 121 -> 122 and 110 -> 112 here and in RATCHETS.md
# together; no raw site changes.
#
# The declared NaN fill adds one reviewed generated name on 2026-10-19:
# fill_nan, the proxy method generated from the operation declaration
# ``fill_nan`` (section 11.1.13). It is capability growth -- the fill a
# lookup's NaN needed and could only reach through polars_native(), and on
# one line not at all once a table read inside an engine fragment was
# refused -- and it builds its expression through the declared-call door
# like every other generated method, so 112 -> 113 here and in RATCHETS.md
# together; no raw site or accessor name changes.
ALLOWLIST_CEILINGS: Final[dict[str, int]] = {
    # 34: scenarios/_aggregators.py under raw_pl_when -- the within-scenario
    # sum that answers null for a scenario with no values, where Polars' own
    # sum answers 0.0. A driver reduction, not a model expression, in a file
    # already listed for raw pl.col; no lowering exists for driver folds.
    "ALLOWLIST": 34,
    # 120: assumptions/_api.py::fingerprint -- a table's public content
    # identity, the digest spec section 15 says the record carries. It
    # returns that string and builds no expression; it is listed only
    # because every public name in an accessor-family file is.
    # 123: frame/graph/calc_graph.py::to_excel -- af.graph's workbook of the
    # exported record, a file written from the document. It builds no
    # expression; it is listed because every public name on af.graph is.
    # 124: frame/graph/calc_graph.py::unused -- af.graph's question "what
    # does nothing read?", answered with node ids under their classes. It
    # builds no expression; it is listed because every public name on the
    # af.graph accessor is.
    "ACCESSOR_METHOD_ALLOWLIST": 124,
    "EXPR_RETURNING_DEF_ALLOWLIST": 113,
}


@dataclass(frozen=True, slots=True)
class Violation:
    """A pattern match outside both the allowlist and the exempt prefixes.

    ``name`` is set for the ``accessor_method_definition`` and
    ``expr_returning_def`` categories, where the violation is a specific
    method/function name rather than "this file matched this pattern".
    """

    category: str
    relative_path: str
    name: str | None = None


def is_exempt(relative_path: str) -> bool:
    """Return whether ``relative_path`` falls under an exempt prefix."""
    return any(relative_path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _is_accessor_family_file(relative_path: str, text: str) -> bool:
    """Return whether ``relative_path`` is in the accessor/lookup/rollforward family.

    See the module docstring for the three structural checks this runs.
    """
    if relative_path in _ACCESSOR_FAMILY_FILES:
        return True
    if any(
        relative_path.startswith(prefix) for prefix in _ACCESSOR_FAMILY_PATH_PREFIXES
    ):
        return True
    return bool(_REGISTER_ACCESSOR_PATTERN.search(text))


# Token kinds that carry prose rather than code. ``FSTRING_MIDDLE`` is the
# literal text between an f-string's replacement fields (Python 3.12+, which
# this project's floor already is): without it, the ``pl.col(`` inside
# ``f"{name} = pl.col('{col}')"`` -- error-message text in
# errors/formatting_errors.py -- would read as a call.
_PROSE_TOKEN_TYPES: Final[frozenset[int]] = frozenset(
    {tokenize.STRING, tokenize.COMMENT, tokenize.FSTRING_MIDDLE}
)


def _without_prose(text: str) -> str:
    """Return ``text`` with every string literal and comment blanked to spaces.

    Blanked in place rather than deleted so nothing else moves: the result
    has the same lines, the same length, and the same offsets, and only the
    prose is gone. A file that will not tokenize is returned unchanged,
    which is the conservative direction -- more matches, never fewer.
    """
    lines = [list(line) for line in text.splitlines(keepends=True)]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, tokenize.TokenError):
        return text
    for token in tokens:
        if token.type not in _PROSE_TOKEN_TYPES:
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        for row in range(start_row, end_row + 1):
            line = lines[row - 1]
            first = start_col if row == start_row else 0
            last = end_col if row == end_row else len(line)
            for index in range(first, min(last, len(line))):
                if line[index] != "\n":
                    line[index] = " "
    return "".join("".join(line) for line in lines)


def _public_def_names(text: str) -> frozenset[str]:
    """Return every public (non-underscore, non-dunder) def name in ``text``."""
    return frozenset(_PUBLIC_DEF_PATTERN.findall(text))


def _expr_returning_def_names(text: str) -> frozenset[str]:
    """Return every def whose own return-type annotation is expression-shaped.

    For each return-type annotation matching one of the five tracked types,
    finds the nearest preceding ``def`` (public or private) in the file. If
    that def is public, its name is recorded; if it is private (or a
    dunder), the match is discarded rather than credited to some earlier,
    unrelated public name -- see the module docstring for why attribution
    has to work this way.
    """
    names: set[str] = set()
    for match in _RETURN_ANNOTATION_PATTERN.finditer(text):
        preceding = text[: match.start()]
        nearest: re.Match[str] | None = None
        for candidate in _ANY_DEF_PATTERN.finditer(preceding):
            nearest = candidate
        if nearest is not None and not nearest.group(1).startswith("_"):
            names.add(nearest.group(1))
    return frozenset(names)


def scan(root: Path) -> list[Violation]:
    """Walk ``root`` and report every pattern match outside the known surface.

    For each ``*.py`` file under ``root``: every category in ``PATTERNS`` is
    a violation unless the file's path (relative to ``root``, POSIX
    separators) is listed in that category's ``ALLOWLIST`` entry, or the
    path falls under one of ``EXEMPT_PREFIXES``. Separately, if the file is
    "in the accessor/lookup/rollforward family" (see
    ``_is_accessor_family_file``), every public method/function name it
    defines is a violation unless listed in ``ACCESSOR_METHOD_ALLOWLIST``
    for that file. Independently of family membership, every def anywhere
    in the file whose own return-type annotation is expression-shaped is a
    violation unless listed in ``EXPR_RETURNING_DEF_ALLOWLIST`` for that
    file.
    """
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        relative_path = path.relative_to(root).as_posix()
        if is_exempt(relative_path):
            continue
        text = path.read_text(encoding="utf-8")
        # The six raw patterns are matched against code only. The two
        # def-keyed checks below deliberately read the source as written --
        # see _without_prose's callers in the module docstring.
        code = _without_prose(text)

        for category, pattern in PATTERNS.items():
            if not pattern.search(code):
                continue
            if relative_path in ALLOWLIST.get(category, frozenset()):
                continue
            violations.append(Violation(category=category, relative_path=relative_path))

        if _is_accessor_family_file(relative_path, text):
            allowed_names = ACCESSOR_METHOD_ALLOWLIST.get(relative_path, frozenset())
            violations.extend(
                Violation(
                    category="accessor_method_definition",
                    relative_path=relative_path,
                    name=name,
                )
                for name in sorted(_public_def_names(text) - allowed_names)
            )

        expr_allowed_names = EXPR_RETURNING_DEF_ALLOWLIST.get(
            relative_path, frozenset()
        )
        violations.extend(
            Violation(
                category="expr_returning_def",
                relative_path=relative_path,
                name=name,
            )
            for name in sorted(_expr_returning_def_names(text) - expr_allowed_names)
        )
    return violations


def _render_violation(violation: Violation) -> str:
    if violation.name is not None:
        return f"  [{violation.category}] {violation.relative_path}::{violation.name}"
    return f"  [{violation.category}] {violation.relative_path}"


def format_violations(violations: list[Violation]) -> str:
    """Render ``violations`` as an actionable failure message."""
    lines = [
        (
            "New expression-producing site(s) outside the known surface "
            "(neither allowlisted nor under an exempt prefix):"
        ),
        *(_render_violation(v) for v in violations),
        (
            "If this is a deliberate, reviewed new site, add it to "
            "tests/graph/census.py's ALLOWLIST, ACCESSOR_METHOD_ALLOWLIST, "
            "or EXPR_RETURNING_DEF_ALLOWLIST as appropriate. If it should "
            "build its expression through frame/lowering/ instead, move it "
            "there."
        ),
    ]
    return "\n".join(lines)


def test_no_unlisted_expr_sites() -> None:
    """Every expression-producing pattern in ``gaspatchio/`` is accounted for.

    This is the "sole producer" tripwire: as long as raw expression
    construction, operator-dunder definitions, accessor/lookup/rollforward
    method definitions, expression-returning method definitions, and frame
    construction only happen in the reviewed set of files (and, for the two
    name-keyed categories, names) below — or under ``frame/lowering/`` once
    that package exists — the DSL's expression surface is exactly what this
    test says it is. A new file, an existing file growing a new pattern
    category, an existing accessor-family file growing a new public method
    name, or any file growing a new expression-returning def, all mean the
    surface grew somewhere unreviewed.
    """
    violations = scan(PACKAGE_ROOT)
    assert not violations, format_violations(violations)


def _allowlist_entry_counts() -> dict[str, int]:
    """Return each allowlist's entry total, counted the way it is keyed.

    ``ALLOWLIST`` is keyed on (category, path), so one path listed under two
    categories is two entries; the other two are keyed on (path, name), so
    the total is names, not files. Counting a structure by its own key is
    what makes the number comparable across a refactor that moves a file.
    """
    return {
        "ALLOWLIST": sum(len(paths) for paths in ALLOWLIST.values()),
        "ACCESSOR_METHOD_ALLOWLIST": sum(
            len(names) for names in ACCESSOR_METHOD_ALLOWLIST.values()
        ),
        "EXPR_RETURNING_DEF_ALLOWLIST": sum(
            len(names) for names in EXPR_RETURNING_DEF_ALLOWLIST.values()
        ),
    }


def overgrown_allowlists(
    counts: dict[str, int], ceilings: dict[str, int]
) -> list[tuple[str, int, int]]:
    """Return ``(structure, count, ceiling)`` for every allowlist over its ceiling."""
    return [
        (structure, count, ceilings[structure])
        for structure, count in sorted(counts.items())
        if count > ceilings[structure]
    ]


def format_overgrown(overgrown: list[tuple[str, int, int]]) -> str:
    """Render allowlists that grew past their ceiling as a failure message."""
    lines = [
        "Allowlist(s) larger than the ceiling recorded in ALLOWLIST_CEILINGS:",
        *(
            f"  {structure}: {count} entries, ceiling {ceiling}"
            for structure, count, ceiling in overgrown
        ),
        (
            "These allowlists are a burn-down chart, not a parking space. A "
            "site that genuinely has to be added is added together with the "
            "argument for it and a raised ceiling in the same commit — the "
            "raise is the reviewable event. Removing sites is the expected "
            "direction: lower the ceiling to the new total when you do, or "
            "the ground it recovered is silently available to the next "
            "addition."
        ),
    ]
    return "\n".join(lines)


def test_allowlist_totals_do_not_grow() -> None:
    """The three allowlists can shrink, and cannot grow unnoticed.

    ``test_no_unlisted_expr_sites`` above answers "is every site accounted
    for", which an entry silences the moment it is added. Nothing until now
    asked the second question — "how many sites are we still accounting
    for" — so the totals could sit unchanged indefinitely with the suite
    green. Pinning them makes the number the lowering consolidation is
    burning down the number this file enforces.
    """
    counts = _allowlist_entry_counts()
    assert set(counts) == set(ALLOWLIST_CEILINGS), (
        "Every allowlist counted needs a ceiling and vice versa; "
        f"counted {sorted(counts)}, pinned {sorted(ALLOWLIST_CEILINGS)}."
    )
    overgrown = overgrown_allowlists(counts, ALLOWLIST_CEILINGS)
    assert not overgrown, format_overgrown(overgrown)


def test_tripwire_detects_an_allowlist_that_grew() -> None:
    """One entry over the ceiling is reported; at or under it is not.

    The ratchet's whole value is the first case, and the first case is the
    one that never happens while the numbers are correct — so it is proved
    here against fabricated totals rather than waited for.
    """
    ceilings = {"ALLOWLIST": 86, "ACCESSOR_METHOD_ALLOWLIST": 147}

    assert overgrown_allowlists({**ceilings, "ALLOWLIST": 87}, ceilings) == [
        ("ALLOWLIST", 87, 86)
    ]
    assert overgrown_allowlists(ceilings, ceilings) == []
    assert overgrown_allowlists({**ceilings, "ALLOWLIST": 40}, ceilings) == []


def stale_entries(
    root: Path,
    *,
    raw: Mapping[str, frozenset[str]] = ALLOWLIST,
    family: frozenset[str] = _ACCESSOR_FAMILY_FILES,
    accessor_methods: Mapping[str, frozenset[str]] = ACCESSOR_METHOD_ALLOWLIST,
    expr_returning: Mapping[str, frozenset[str]] = EXPR_RETURNING_DEF_ALLOWLIST,
) -> list[str]:
    """Return every entry naming a file, or a def, that no longer exists.

    The scan reads one direction only: a site nobody listed fails it, and
    an entry that outlives its site passes forever. Each entry is a claim
    about code that is there, so this reads the other direction. Every file
    the census names has to exist, and every name in the two name-keyed
    lists has to be defined in its file under the rule that admitted it --
    a public ``def`` for an accessor-family name, and one whose own return
    annotation is expression-shaped for an expression-returning one.
    """
    named = {
        *(path for paths in raw.values() for path in paths),
        *family,
        *accessor_methods,
        *expr_returning,
    }
    found = [
        f"{path}: no such file" for path in sorted(named) if not (root / path).is_file()
    ]
    for structure, allowlist, defined in (
        ("ACCESSOR_METHOD_ALLOWLIST", accessor_methods, _public_def_names),
        ("EXPR_RETURNING_DEF_ALLOWLIST", expr_returning, _expr_returning_def_names),
    ):
        for path, names in sorted(allowlist.items()):
            source = root / path
            if not source.is_file():
                continue
            missing = names - defined(source.read_text(encoding="utf-8"))
            found.extend(
                f"{path}::{name}: not in {structure}'s sense"
                for name in sorted(missing)
            )
    return found


def test_no_entry_names_a_file_or_a_def_that_is_gone() -> None:
    """Every entry is a claim about code that is there, and each is checked.

    The two name-keyed lists are described above as exact censuses of a live
    surface. That held only while nobody deleted a listed module: a deleted
    module's entries once went on counting towards the totals, unseen,
    because nothing read the census against the package in this direction.
    """
    stale = stale_entries(PACKAGE_ROOT)

    assert stale == [], (
        "Census entries for code that no longer exists:\n  "
        + "\n  ".join(stale)
        + "\nTake each one off. A total that falls can have its ceiling "
        "lowered with it, in this file and in RATCHETS.md together."
    )


def test_tripwire_detects_a_stale_entry(tmp_path: Path) -> None:
    """A gone file, a gone def and a def that stopped returning an expression.

    Proved against a fabricated package, because the live census is clean
    and the case worth catching is the one that never happens while it is.
    """
    (tmp_path / "kept.py").write_text(
        "def lookup(self) -> pl.Expr:\n"
        "    return pl.col('x')\n"
        "\n"
        "def describe(self) -> str:\n"
        "    return 'x'\n",
        encoding="utf-8",
    )

    found = stale_entries(
        tmp_path,
        raw={"pl_col": frozenset({"kept.py", "deleted_raw.py"})},
        family=frozenset({"kept.py"}),
        accessor_methods={
            "kept.py": frozenset({"lookup", "describe", "renamed_away"}),
            "deleted_module.py": frozenset({"expr_for"}),
        },
        expr_returning={"kept.py": frozenset({"lookup", "describe"})},
    )

    assert found == [
        "deleted_module.py: no such file",
        "deleted_raw.py: no such file",
        "kept.py::renamed_away: not in ACCESSOR_METHOD_ALLOWLIST's sense",
        "kept.py::describe: not in EXPR_RETURNING_DEF_ALLOWLIST's sense",
    ]


def format_unclassified(identifiers: list[str]) -> str:
    """Render unclassified operation identifiers as an actionable failure message."""
    lines = [
        (
            "Operation(s) that can be lowered but that nothing has classified "
            "into an execution tier:"
        ),
        *(f"  {identifier}" for identifier in identifiers),
        (
            "An exported node reaching one of these reports tier 'opaque', "
            "which tells a reader the format cannot account for a calculation "
            "it can perfectly well account for. The fix is one line per "
            "identifier in gaspatchio/frame/graph/tiers.py's TIERS, and a "
            "matching row in the vocabulary table of "
            "spec/graph-artifact/v0-preview.md."
        ),
    ]
    return "\n".join(lines)


def test_every_registered_lowering_is_classified() -> None:
    """A new lowering that lands untiered fails here, not silently in an artifact.

    The sibling of the scan above, and the same kind of claim: that one is
    "every place that builds an expression is a place somebody reviewed",
    this one is "every operation those places can build is an operation the
    exported graph can account for". A lowering registered without a tier
    would not break a single calculation -- it would quietly downgrade every
    node that reaches it, and the first person to notice would be whoever
    tried to run the model on something other than this package.
    """
    # Imported here rather than at module scope: this module is importable
    # on its own and reads the package as source text, so importing that
    # package to run it would be an odd thing for it to do on the way in.
    from gaspatchio.frame.graph.tiers import TIERS
    from gaspatchio.frame.lowering.polars import LOWERINGS, ensure_rules_loaded

    # The registry is populated by the rule modules, not by importing it.
    ensure_rules_loaded()
    unclassified = sorted(set(LOWERINGS) - set(TIERS))

    assert not unclassified, format_unclassified(unclassified)


def test_tripwire_detects_unlisted_site(tmp_path: Path) -> None:
    """A fresh file with an unlisted raw ``pl.col(`` call is reported.

    The fixture's own return type (``-> pl.Expr``) also makes it a new,
    unlisted expression-returning def, so both categories fire -- this is
    realistic layered detection, not a test artifact.
    """
    target = tmp_path / "reports" / "summary.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import polars as pl\n\n\ndef total(name: str) -> pl.Expr:\n"
        "    return pl.col(name).sum()\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(category="raw_pl_col", relative_path="reports/summary.py"),
        Violation(
            category="expr_returning_def",
            relative_path="reports/summary.py",
            name="total",
        ),
    ]


def test_tripwire_ignores_allowlisted_path(tmp_path: Path) -> None:
    """The identical pattern at an allowlisted path, under an allowlisted name.

    ``fill_series`` is ``frame/base.py``'s real, already-known
    expression-returning method name, so reusing it here keeps this test
    isolated to proving allowlisted things stay quiet under both the
    raw-pattern and expression-returning-def checks at once.
    """
    target = tmp_path / "frame" / "base.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import polars as pl\n\n\ndef fill_series(name: str) -> pl.Expr:\n"
        "    return pl.col(name).sum()\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == []


def test_tripwire_exempts_frame_lowering_prefix(tmp_path: Path) -> None:
    """A raw site under ``frame/lowering/`` is exempt without an allowlist entry."""
    target = tmp_path / "frame" / "lowering" / "polars.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import polars as pl\n\n\ndef total(name: str) -> pl.Expr:\n"
        "    return pl.col(name).sum()\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == []


def test_tripwire_exempts_tutorials_prefix(tmp_path: Path) -> None:
    """A raw site under ``tutorials/`` is exempt (example model code)."""
    target = tmp_path / "tutorials" / "level-9-new" / "model.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import polars as pl\n\n\ndef total(name: str) -> pl.Expr:\n"
        "    return pl.col(name).sum()\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == []


def test_a_raw_pattern_inside_prose_is_not_a_finding(tmp_path: Path) -> None:
    """A ``pl.col(`` that only ever appears in a docstring or comment is prose.

    The six raw patterns are a text scan, and this project requires a
    runnable example in every public method's docstring -- so
    ``ActuarialFrame(`` and ``pl.col(`` appear in the documentation of files
    that construct neither. Counting those made 39 of the 86 ``ALLOWLIST``
    entries measure documentation rather than code, including entries whose
    own comment said so by hand. Prose is blanked before the raw patterns
    run, so an entry on that list now means executable code matches there.
    """
    target = tmp_path / "reports" / "summary.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def describe(name: str) -> str:\n"
        '    """Summarise a column.\n\n'
        "    Example:\n"
        "        >>> af = ActuarialFrame(data)\n"
        '        >>> af.total = pl.col("x").sum()\n'
        '    """\n'
        "    # A caller writes pl.when(...) here, not this function.\n"
        "    return name\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == []


def test_a_quoted_return_annotation_is_still_counted(tmp_path: Path) -> None:
    """Blanking prose stops at the raw patterns; the def checks read the source.

    This codebase annotates most accessor returns with a *quoted* forward
    reference (``-> "ExpressionProxy":``), so a string literal is the
    annotation. Blanking strings before the expression-returning-def check
    would have silently dropped ten real, expression-producing methods --
    ``accessors/date.py``'s ``months_between`` and ``to_period`` and all
    eight of ``accessors/excel.py``'s -- which is why the blanking is scoped
    to the six raw patterns and this test stands guard over that scoping.
    """
    target = tmp_path / "reports" / "shaped.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "class Shaper:\n"
        '    def net_of_neighbours(self) -> "ExpressionProxy":\n'
        "        return self.previous_period() + self.next_period()\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == [
        Violation(
            category="expr_returning_def",
            relative_path="reports/shaped.py",
            name="net_of_neighbours",
        )
    ]


def test_tripwire_detects_new_pattern_category_on_known_file(tmp_path: Path) -> None:
    """A known file gaining a pattern category it isn't allowlisted for still trips.

    ``frame/base.py`` is allowlisted for ``raw_pl_col`` but not for
    ``raw_pl_when`` -- if it grows a raw ``pl.when(`` call, that is a new
    category on an existing file, and must still be reported. Named
    ``fill_series`` (a real, already-known name for this file) so the
    unrelated ``expr_returning_def`` check stays quiet and this test keeps
    proving only the one thing it's named for.
    """
    target = tmp_path / "frame" / "base.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import polars as pl\n\n\ndef fill_series(name: str) -> pl.Expr:\n"
        "    return pl.when(pl.col(name) > 0).then(1).otherwise(0)\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(category="raw_pl_when", relative_path="frame/base.py")
    ]


def test_tripwire_detects_new_method_on_known_accessor_file(tmp_path: Path) -> None:
    """A new, unlisted method on an already-known accessor file trips.

    ``accessors/finance.py`` is a real accessor file (its own
    ``@register_accessor`` decorator puts it in the family); its allowlist
    entry does not include ``brand_new_verb``. The method's body composes
    only already-reviewed proxy calls and has no return-type annotation,
    matching none of the six raw patterns nor the expression-returning-def
    check -- this is exactly the blind spot the accessor-family category
    exists to close.
    """
    target = tmp_path / "accessors" / "finance.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from gaspatchio.frame.registry import register_accessor\n\n\n"
        '@register_accessor("finance", kind="column")\n'
        "class FinanceColumnAccessor:\n"
        "    def brand_new_verb(self):\n"
        "        return self.previous_period() + self.next_period()\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(
            category="accessor_method_definition",
            relative_path="accessors/finance.py",
            name="brand_new_verb",
        )
    ]


def test_tripwire_detects_new_accessor_file_via_register_accessor(
    tmp_path: Path,
) -> None:
    """A brand-new file using @register_accessor trips on its own methods.

    The file's path has no entry in ``ACCESSOR_METHOD_ALLOWLIST`` at all --
    every public method it defines is unreviewed.
    """
    target = tmp_path / "accessors" / "discounting.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from gaspatchio.frame.registry import register_accessor\n\n\n"
        '@register_accessor("discounting", kind="column")\n'
        "class DiscountingColumnAccessor:\n"
        "    def shiny_new_method(self):\n"
        "        return self.previous_period()\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(
            category="accessor_method_definition",
            relative_path="accessors/discounting.py",
            name="shiny_new_method",
        )
    ]


def test_tripwire_detects_new_namespace_proxy_file(tmp_path: Path) -> None:
    """A file recreating column/namespaces/ trips without @register_accessor.

    The retired reflective-proxy path remains a structural tripwire.
    """
    target = tmp_path / "column" / "namespaces" / "struct_proxy.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "class StructNamespaceProxy:\n"
        "    def field(self, name):\n"
        "        return self._get_base_expr().struct.field(name)\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(
            category="accessor_method_definition",
            relative_path="column/namespaces/struct_proxy.py",
            name="field",
        )
    ]


def test_tripwire_ignores_known_accessor_method(tmp_path: Path) -> None:
    """A method already in ACCESSOR_METHOD_ALLOWLIST for its file is not reported."""
    target = tmp_path / "accessors" / "date.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from gaspatchio.frame.registry import register_accessor\n\n\n"
        '@register_accessor("date", kind="column")\n'
        "class DateColumnAccessor:\n"
        "    def to_period(self, freq: str = 'M'):\n"
        "        return self._get_base_expr().dt.truncate(freq)\n",
        encoding="utf-8",
    )

    assert scan(tmp_path) == []


def test_tripwire_detects_schedule_shaped_expr_returning_method(
    tmp_path: Path,
) -> None:
    """A Schedule-shaped method trips via return type alone, no family needed.

    Reproduces the real gap: a local wrapper decorator (not
    ``@register_accessor``), a file that isn't under the retired
    ``column/namespaces/`` path or on the explicit family list, and one new
    method whose own signature is annotated ``-> pl.Expr``. Nothing here
    matches any of the six raw patterns or the accessor-family check; only the
    expression-returning-def check -- keyed on the declared return type,
    not on recognising the file at all -- sees it.
    """
    target = tmp_path / "schedule" / "_new_schedule_helper.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import functools\n\n"
        "import polars as pl\n\n\n"
        "def _proxy_aware(fn):\n"
        "    @functools.wraps(fn)\n"
        "    def _wrapper(*args, **kwargs):\n"
        "        return fn(*args, **kwargs)\n\n"
        "    return _wrapper\n\n\n"
        "class ScheduleLikeHelper:\n"
        "    @_proxy_aware\n"
        "    def brand_new_timeline_expr(self) -> pl.Expr:\n"
        "        return pl.lit(1)\n",
        encoding="utf-8",
    )

    violations = scan(tmp_path)

    assert violations == [
        Violation(
            category="expr_returning_def",
            relative_path="schedule/_new_schedule_helper.py",
            name="brand_new_timeline_expr",
        )
    ]
