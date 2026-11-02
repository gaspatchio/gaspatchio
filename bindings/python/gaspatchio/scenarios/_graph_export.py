# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario run's way into an artifact, over the plan the modeller wrote.

A scenario axis is not the model's doing. The model reads ``scenario_id``
and dispatches on it; the *plan* is what cross-joins the axis on, stacks
the shocked bases and folds each scenario's total. So a command that runs
the model alone can produce no account of a scenario run at all -- no
scenario on the context, one assumption entry where there are three curves,
and a lookup proof naming a table nobody discounted with.

**The door is on the exporter, over the plan.** ``--scenarios
run_scenarios.py`` hands the exporter the script the modeller already
writes, and the exporter runs the plan the way that script would. The
alternative -- a method on the run result, ``result.export_graph(...)`` --
was rejected because it puts a producer door inside user code: every other
export in this framework is a command, and a model file that has to call
the exporter to be exportable is a model file that has been changed for the
exporter's benefit.

**What the script declares, and what this reads.** The same shape the
portfolio fold took: the module declares, the door reads. Two names beside
the script's own code --

    SCENARIO_RUN = ScenarioRun(shocks=..., aggregations=...)
    MODEL_FN = model.main

-- and a script declaring neither is refused by name rather than guessed
at. ``SCENARIO_RUN`` may be the plan itself or a callable that returns one,
so a script that builds its plan inside a function has a door too; a
plan the exporter had to find by rummaging for the only ``ScenarioRun`` in
the module would mean something different on the next script, which
declares two.

**The script is imported, so whatever it does at import happens.** There is
no way to get a plan out of a Python file without executing it. A script
that runs its own sweep at module level therefore runs it once more before
the exporter starts; putting that under ``if __name__ == "__main__":``
leaves the declarations where this reads them and costs the export nothing.
The refusals say so.

**The model runs twice, as it does for a portfolio fold, and for the same
reason.** Once here, composed into one frame carrying every policy against
every scenario -- that frame is what the artifact is an account of, and
every value in it is a quotation of it. Once through ``plan.run``, which is
where the per-scenario totals come from: those are the plan's own fold over
the whole book, not a re-summation of the handful of policies the document
samples, and they are the numbers the modeller's own script prints.
``plan.run`` is also what writes the run's ``*.audit.json``, so the two
records of one run are written by one call and the artifact names the file.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from gaspatchio._beside import importable_beside
from gaspatchio.frame.graph.row_identity import (
    pin_each_entry,
    stamp_the_book,
    without_the_stamp,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    import polars as pl

    from gaspatchio.frame import ActuarialFrame
    from gaspatchio.frame.calculations import SourceSpan
    from gaspatchio.frame.graph.policies import SelectedPolicy
    from gaspatchio.frame.graph.portfolio import PortfolioFold

__all__ = [
    "DECLARED_MODEL_FN",
    "DECLARED_PLAN",
    "SCENARIO_COLUMN",
    "ScenarioDoorError",
    "ScenarioPlan",
    "ScenarioRunExport",
    "each_entry_names_its_scenario",
    "open_the_script",
    "run_the_plan",
    "the_grid",
]

# The two module-level names a run script declares, and this reads. Spelled
# as declarations rather than found by type, so that one script's door and
# the next one's are the same door: a module holding two plans -- a
# one-dimensional sweep and a two-dimensional one, which is exactly what the
# sensitivity tutorial holds -- would otherwise be refused or, worse,
# resolved to whichever came first.
DECLARED_PLAN: Final[str] = "SCENARIO_RUN"
DECLARED_MODEL_FN: Final[str] = "MODEL_FN"

# How the loaded script is named in ``sys.modules`` while it runs. Prefixed
# so that a script called ``model`` or ``json`` cannot displace a module the
# framework itself is holding.
_LOADED_AS: Final[str] = "gaspatchio._scenario_script_"


class ScenarioDoorError(ValueError):
    """A run script this exporter cannot honestly run a plan out of."""


# The name the cross-join puts the axis under. It is ``with_scenarios``'s
# own default and the one every batch of every run uses, so the selector's
# view of the frame is built under it too rather than under a second
# spelling nothing else would agree with.
SCENARIO_COLUMN: Final[str] = "scenario_id"


@dataclass(frozen=True, slots=True)
class ScenarioPlan:
    """What a run script declares, read once and held.

    Attributes:
        plan: The ``ScenarioRun`` the script declares.
        model_fn: The function the plan is run against.
        site: The line of the script that declares the plan, which is
            where the record says the scenario axis arrived.
        scenario_ids: The axis, in the order the plan declares it.

    """

    plan: Any
    model_fn: Callable[..., ActuarialFrame]
    site: SourceSpan | None
    scenario_ids: tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class ScenarioRunExport:
    """One scenario run, as the exporter needs to hold it.

    Attributes:
        frame: The cross-joined frame the model built -- every policy
            against every scenario, run once. It carries the calculation
            log the artifact is folded out of.
        values: That frame collected. The artifact's samples are read off
            it, and ``--output-file`` writes it.
        folds: The plan's own per-scenario totals, one axis entry per fold
            and cut, keyed the way a portfolio fold's entries are.
        audit_path: The run's own ``*.audit.json``, which the artifact
            names by path and digest.
        plan_sha: The plan's published identity, for the console.

    """

    frame: ActuarialFrame
    values: pl.DataFrame
    folds: tuple[PortfolioFold, ...]
    audit_path: Path
    plan_sha: str


def open_the_script(script: Path) -> ScenarioPlan:
    """Return the plan and the model function a run script declares.

    Separate from running it because the selection comes first: a reader
    is told which rows the artifact will carry values for before a run of
    a thousand policies over three scenarios starts, not after it.

    Args:
        script: The run script -- the file that declares the plan.

    Returns:
        The plan, the model function, the axis and the declaration site.

    Raises:
        ScenarioDoorError: If the script declares no plan or no model
            function, declares either as the wrong sort of thing, or could
            not be imported at all.

    """
    module = _loaded(script)
    plan = _the_plan(module, script)
    return ScenarioPlan(
        plan=plan,
        model_fn=_the_model_fn(module, script),
        site=_where_the_plan_is_declared(module, script),
        scenario_ids=tuple(plan.shocks),
    )


def the_grid(declared: ScenarioPlan, book: pl.DataFrame) -> pl.DataFrame:
    """Return the rows the run will have, for the selector to choose among.

    The policy axis is an axis of *rows of the frame the model ran*, and on
    a scenario run that frame is the cross-join: policy 7 is on one row per
    scenario, which is why naming it by id is refused there and why a row
    position reaches a scenario. Built here from the book and the plan
    alone -- the same cross-join, in the same order -- so the selection is
    made and announced before the model starts rather than after.

    Built over the **stamped** book, because the stamp is what carries a
    selected row through the run and the grid is where the selector reads
    it. One book row is one row of the book and three of the grid, so on a
    scenario run the stamp alone names three rows: the scenario column is
    the second half of the key, and :func:`each_entry_names_its_scenario`
    names it to the pin for exactly that reason.
    """
    import polars as pl  # noqa: PLC0415 — the frame types are only needed here

    axis = pl.DataFrame({SCENARIO_COLUMN: list(declared.scenario_ids)})
    return stamp_the_book(book).join(axis, how="cross", maintain_order="left_right")


def each_entry_names_its_scenario(
    selection: Sequence[SelectedPolicy], grid: pl.DataFrame
) -> tuple[SelectedPolicy, ...]:
    """Return the selection with every entry stating the scenario it sits in.

    A cross-joined frame names each policy once per scenario, so three
    entries selected by ``:3`` off a three-scenario run all read
    ``policy_id: "1"`` and differ in nothing a reader can see. The cut is
    what tells them apart, and it is the member section 7 already defines
    for *which rows are behind this value*.

    Read off the grid by row rather than derived from the row number and
    the axis length, because the arithmetic would be a second statement
    about how a cross-join orders its output -- and the one place that is
    decided is the join itself.

    The same reading pins each entry to its row of the frame the model will
    run: a book row and a scenario together are what name one row of the
    grid, and the cross-join is what made them so. Nothing in
    :mod:`~gaspatchio.frame.graph.row_identity` guesses that -- the door
    that multiplied the book says which column it multiplied it by, because
    it is the only thing that knows.
    """
    from dataclasses import replace  # noqa: PLC0415 — one call, on one path

    from gaspatchio.frame.graph.portfolio import written_cut  # noqa: PLC0415 — cycle

    pinned = pin_each_entry(selection, grid, axis_columns=(SCENARIO_COLUMN,))
    column = grid[SCENARIO_COLUMN]
    return tuple(
        replace(entry, cut=written_cut(SCENARIO_COLUMN, column[entry.row]))
        for entry in pinned
    )


def run_the_plan(  # noqa: PLR0913 — one parameter per thing the run or a sentence has to be able to name
    declared: ScenarioPlan,
    *,
    book: pl.DataFrame,
    audit_path: Path,
    retain_superseded: bool,
    source: str,
    period: int | None,
    versions: Literal["recorded", "withheld"] = "recorded",
) -> ScenarioRunExport:
    """Run the declared plan and hand back what an export needs.

    **The frame the document is an account of is stamped and the plan's own
    run is not.** The stamp is how a selected row is found again after the
    model has had the frame, and it belongs to this export; the plan's run
    writes an audit record of its own, which a column this exporter
    invented has no business in, and the folds are read off that run.

    Args:
        declared: What :func:`open_the_script` read out of the script.
        book: The model points as they arrive, every row of them, carrying
            the export's row stamp where the caller put one on.
        audit_path: Where the run's own record is written. It is the
            artifact's sibling, so the two records of one run are found
            together.
        retain_superseded: Whether a column the model writes twice keeps
            what the replaced definition produced, as everywhere else.
        source: The model-point file's own name, for the fold's sentences.
        period: The projection period the document is pinned to, or None.
        versions: What the run's own record states about the library, as
            :meth:`ScenarioRun.run` takes it: the document's own setting,
            so ``calc-graph --no-versions`` withholds them in both of the
            run's records.

    Returns:
        The composed frame, its values, the plan's folds, and the run's
        own record.

    """
    from gaspatchio.frame.base import (  # noqa: PLC0415 — CLI startup cost
        _frame_over_the_book,
    )

    frame = _composed(
        declared,
        _frame_over_the_book(
            stamp_the_book(book), mode="debug", retain_superseded=retain_superseded
        ),
    )
    values = frame.collect()

    # The plan's own run, which is the script's: the per-scenario totals
    # come off it rather than out of the frame above, because a fold is a
    # statement about the whole book while this document samples a handful
    # of its rows. It writes the audit record on the way through, so the
    # two records of one run are written by one call.
    plain = without_the_stamp(book)
    result = declared.plan.run(
        _frame_over_the_book(plain, mode="debug"),
        declared.model_fn,
        audit=audit_path,
        versions=versions,
    )
    return ScenarioRunExport(
        frame=frame,
        values=values,
        folds=_folds_of(
            result,
            declared.plan,
            book=plain,
            counted_on=values,
            source=source,
            period=period,
        ),
        audit_path=result.audit_path or audit_path,
        plan_sha=result.plan_sha,
    )


def _composed(declared: ScenarioPlan, af: ActuarialFrame) -> ActuarialFrame:
    """Return the frame the plan builds with every scenario in one batch.

    The run's own batching exists to bound memory, and it produces several
    frames where a document needs one: an artifact is an account of a
    calculation, and a calculation cut into three pieces is three accounts.
    So the grid is composed once here, through the same recipe every batch
    of every run goes through -- not a second composition beside it that
    could drift from the one the numbers came out of.
    """
    from gaspatchio.scenarios._for_each import (  # noqa: PLC0415 — would cycle
        _BatchRecipe,
        _classify,
    )

    plan = declared.plan
    recipe = _BatchRecipe(
        scenarios=plan.shocks,
        shape=_classify(plan.shocks),
        base_tables=plan.base_tables,
        master_seed=plan.master_seed,
        site=declared.site,
        axis=tuple(declared.scenario_ids),
    )
    return recipe.compose(af, list(declared.scenario_ids), declared.model_fn)


def _folds_of(  # noqa: PLR0913 — passed straight through to axis_entries, whose list it is
    result: Any,  # noqa: ANN401 — a ScenarioResult, imported where the driver is
    plan: Any,  # noqa: ANN401 — a ScenarioRun, likewise
    *,
    book: pl.DataFrame,
    counted_on: pl.DataFrame,
    source: str,
    period: int | None,
) -> tuple[PortfolioFold, ...]:
    """Return the plan's aggregations as entries on the artifact's policy axis.

    The same entries a portfolio fold writes, built by the same code: a
    scenario sweep's ``Sum(...).over("scenario_id")`` is one fold of
    several cuts, which is what section 7.4's ``filter`` already says. The
    count in each entry's sentence is the policies its cut holds, counted
    on ``counted_on`` -- the cross-joined frame the model returned, so a cut
    by ``("scenario_id", "policy_id")`` says one policy, a cut by a column
    the model computes is counted too, and a cut spanning the scenarios
    says how many it spans.
    """
    from gaspatchio.frame.graph.portfolio import axis_entries  # noqa: PLC0415 — cycle

    return axis_entries(
        result,
        plan.aggregations,
        book=book,
        source=source,
        period=period,
        counted_on=counted_on,
        scenario_column=SCENARIO_COLUMN,
    )


def _loaded(script: Path) -> Any:  # noqa: ANN401 — the caller's own module
    """Return the run script, imported, with its own directory importable.

    The script's directory goes on the path first because a run script
    imports the model beside it -- ``import model`` -- exactly as it does
    when the modeller runs it themselves. Without that the import fails on
    a line the script has always had, and the refusal would be about the
    wrong thing entirely.
    """
    name = _LOADED_AS + script.stem
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise ScenarioDoorError(_not_importable(script, "it is not a Python file"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        with importable_beside(script):
            spec.loader.exec_module(module)
    except Exception as failure:
        del sys.modules[name]
        raise ScenarioDoorError(_not_importable(script, str(failure))) from failure
    return module


def _the_plan(module: Any, script: Path) -> Any:  # noqa: ANN401 — the caller's own module and its plan
    """Return the plan the script declares, called where it declares a maker."""
    from gaspatchio.scenarios import ScenarioRun  # noqa: PLC0415 — CLI startup cost

    declared = getattr(module, DECLARED_PLAN, None)
    if declared is None:
        raise ScenarioDoorError(_no_plan(script))
    plan = declared() if callable(declared) else declared
    if not isinstance(plan, ScenarioRun):
        raise ScenarioDoorError(_not_a_plan(script, plan))
    return plan


def _the_model_fn(module: Any, script: Path) -> Callable[..., ActuarialFrame]:  # noqa: ANN401 — the caller's own module
    """Return the model function the script declares, refusing anything else."""
    declared = getattr(module, DECLARED_MODEL_FN, None)
    if declared is None:
        raise ScenarioDoorError(_no_model_fn(script))
    if not callable(declared):
        raise ScenarioDoorError(_not_a_model_fn(script, declared))
    return declared  # type: ignore[no-any-return]


def _where_the_plan_is_declared(module: Any, script: Path) -> SourceSpan | None:  # noqa: ANN401 — the caller's own module
    """Return the line of the script that binds the plan, as a source span.

    Read off the script's own text rather than walked off the live stack,
    and it has to be: by the time the cross-join happens, the exporter
    stands between it and every line the modeller wrote, so a stack walk
    would leave this framework into whichever library called the exporter
    and locate a scenario axis in the command-line parser.

    A module-level assignment is found in the syntax tree. A plan declared
    as a function is located at its ``def``. Anything else -- a name bound
    inside a conditional, an import from elsewhere -- has no line this can
    honestly name, and the record then carries none rather than a guess.
    """
    from gaspatchio.frame.calculations import SourceSpan  # noqa: PLC0415 — CLI cost

    declared = getattr(module, DECLARED_PLAN, None)
    if inspect.isfunction(declared):
        _, line = inspect.getsourcelines(declared)
        statement = f"def {DECLARED_PLAN}(...)"
        return SourceSpan(
            file=str(script),
            line=line,
            end_line=line,
            function=None,
            statement=statement,
            rhs=None,
            target_literal=True,
        )
    bound = _assignment_line(script)
    if bound is None:
        return None
    return SourceSpan(
        file=str(script),
        line=bound,
        end_line=bound,
        function=None,
        statement=f"{DECLARED_PLAN} = ...",
        rhs=None,
        target_literal=True,
    )


def _assignment_line(script: Path) -> int | None:
    """Return the line of the last module-level binding of the declared name."""
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None
    found: int | None = None
    for statement in tree.body:
        targets: list[ast.expr] = []
        if isinstance(statement, ast.Assign):
            targets = list(statement.targets)
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == DECLARED_PLAN:
                found = statement.lineno
    return found


def _no_plan(script: Path) -> str:
    """Return the refusal for a script that declares no plan."""
    return (
        f"{script.name} declares no {DECLARED_PLAN}, and a scenario export is "
        "an account of a plan being run. Which scenarios, which shocked "
        "bases and which totals is the modeller's decision, so nothing here "
        "picks them for you. Declare the plan beside the script's own code, "
        "as the name this reads:\n\n"
        f"    {DECLARED_PLAN} = ScenarioRun(shocks=..., aggregations=...)\n"
        f"    {DECLARED_MODEL_FN} = model.main\n\n"
        "A function returning the plan is read the same way. The script is "
        "imported to reach those names, so anything it does at module level "
        "happens before the export starts; put its own run under "
        'if __name__ == "__main__": and the export costs one run of the model.'
    )


def _not_a_plan(script: Path, declared: object) -> str:
    """Return the refusal for a declared name that is not a plan."""
    return (
        f"{script.name} declares {DECLARED_PLAN} as "
        f"{type(declared).__name__}, and this door runs a ScenarioRun. A "
        "plan carries the scenarios, the base tables the run shocks and the "
        "aggregations it folds, which is what the export needs to name the "
        "scenario on every entry and one assumption per scenario curve. "
        "Build one with ScenarioRun(...) and declare it under that name, or "
        "declare a function of no arguments that returns one."
    )


def _no_model_fn(script: Path) -> str:
    """Return the refusal for a script that declares no model function."""
    return (
        f"{script.name} declares no {DECLARED_MODEL_FN}. A plan is run "
        "against a model function -- the model this script already passes "
        "to .run(), the frame-only main(af) you reconciled -- and the "
        "exporter has no way to guess which of the script's functions that "
        f"is. Declare it beside the plan:\n\n    {DECLARED_MODEL_FN} = model.main"
    )


def _not_a_model_fn(script: Path, declared: object) -> str:
    """Return the refusal for a declared model function that is not callable."""
    return (
        f"{script.name} declares {DECLARED_MODEL_FN} as "
        f"{type(declared).__name__}, which cannot be run. It is the function "
        "the plan is run against, the frame-only main(af), taking the "
        "frame and "
        "returning the frame the model built."
    )


def _not_importable(script: Path, why: str) -> str:
    """Return the refusal for a run script that would not import."""
    return (
        f"{script.name} could not be imported, so the plan it declares could "
        f"not be reached: {why}. The script is imported rather than read, "
        "because a plan is a Python object and there is no way to have one "
        "without running the line that builds it. Everything the script does "
        "at module level runs too -- including its own sweep, if that is not "
        'under if __name__ == "__main__":.'
    )
