"""Custom evaluators for gaspatchio skill evals.

Use built-in evaluators (Contains, EqualsExpected, LLMJudge) where possible.
Custom evaluators here handle domain-specific checks.
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.result_types import (
    DiscoveryResult,
    ExtendingResult,
    ReconciliationResult,
    ReviewResult,
    ScenarioResult,
)


@dataclass
class NoCodeWritten(Evaluator[str, DiscoveryResult]):
    """Discovery skill should never produce code.

    The hard gate says: DO NOT write model code until spec is approved.
    Score 1.0 if code_written is False, 0.0 if True.
    """

    def evaluate(self, ctx: EvaluatorContext[str, DiscoveryResult]) -> float:
        return 0.0 if ctx.output.code_written else 1.0


@dataclass
class SeverityClassification(Evaluator[str, ReviewResult]):
    """Check that known anti-patterns are classified at the right severity.

    Given a list of keywords expected at Critical or Important severity,
    verify the review agent placed them in the correct bucket.
    """

    expected_critical_keywords: list[str]
    expected_important_keywords: list[str]

    def evaluate(self, ctx: EvaluatorContext[str, ReviewResult]) -> float:
        critical_text = " ".join(ctx.output.critical_issues).lower()
        important_text = " ".join(ctx.output.important_issues).lower()

        critical_found = sum(
            1
            for kw in self.expected_critical_keywords
            if kw.lower() in critical_text
        )
        important_found = sum(
            1
            for kw in self.expected_important_keywords
            if kw.lower() in important_text
        )
        total_expected = len(self.expected_critical_keywords) + len(self.expected_important_keywords)
        if total_expected == 0:
            return 1.0
        return (critical_found + important_found) / total_expected


@dataclass
class NoCriticalIssues(Evaluator[str, ReviewResult]):
    """Clean model should have no critical issues.

    Score 1.0 if critical_issues is empty, 0.0 otherwise.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ReviewResult]) -> float:
        return 1.0 if len(ctx.output.critical_issues) == 0 else 0.0


@dataclass
class TwoScriptPattern(Evaluator[str, ScenarioResult]):
    """Scenarios skill must not modify model.py and must create run_scenarios.py.

    The hard gate says: model.py stays UNCHANGED, all scenario logic
    goes in run_scenarios.py.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ScenarioResult]) -> float:
        if ctx.output.model_py_modified:
            return 0.0
        if not ctx.output.run_scenarios_created:
            return 0.0
        return 1.0


@dataclass
class IdentifiesReference(Evaluator[str, ReconciliationResult]):
    """Reconciliation skill must identify or ask for a reference.

    Score 1.0 if reference_identified is non-empty (agent asked/identified a reference),
    0.0 if empty.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ReconciliationResult]) -> float:
        return 1.0 if ctx.output.reference_identified.strip() else 0.0


@dataclass
class InvestigatesMismatch(Evaluator[str, ReconciliationResult]):
    """Reconciliation skill must not accept mismatches without investigation.

    Score 1.0 if tolerance_stated is True (agent insists on precision),
    0.5 if variables_compared is non-empty (at least investigating),
    0.0 otherwise.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ReconciliationResult]) -> float:
        if ctx.output.tolerance_stated:
            return 1.0
        if len(ctx.output.variables_compared) > 0:
            return 0.5
        return 0.0


@dataclass
@dataclass
class PlacementCorrect(Evaluator[str, ExtendingResult]):
    """Extending skill must route to the correct performance ladder level.

    Compares the agent's placement_level to the expected level.
    Score 1.0 if exact match, 0.0 otherwise.
    """

    expected_level: int

    def evaluate(self, ctx: EvaluatorContext[str, ExtendingResult]) -> float:
        return 1.0 if ctx.output.placement_level == self.expected_level else 0.0


@dataclass
class NoAntiPattern(Evaluator[str, ExtendingResult]):
    """Extending skill must never produce code with anti-patterns.

    Score 1.0 if uses_antipattern is False, 0.0 if True.
    """

    def evaluate(self, ctx: EvaluatorContext[str, ExtendingResult]) -> float:
        return 0.0 if ctx.output.uses_antipattern else 1.0


@dataclass
class ListColumnHandling(Evaluator[str, ExtendingResult]):
    """Accessor extensions must handle both scalar and list columns.

    Score 1.0 if handles_list_columns is True, 0.0 if False.
    Only meaningful for accessor placements (Level 5/6).
    """

    def evaluate(self, ctx: EvaluatorContext[str, ExtendingResult]) -> float:
        return 1.0 if ctx.output.handles_list_columns else 0.0


class HasQuestionsBeforeCode(Evaluator[str, DiscoveryResult]):
    """Discovery must ask questions AND not write code.

    Score is proportion of: asked at least one question (0.5) + no code written (0.5).
    """

    def evaluate(self, ctx: EvaluatorContext[str, DiscoveryResult]) -> float:
        score = 0.0
        if len(ctx.output.questions_asked) > 0:
            score += 0.5
        if not ctx.output.code_written:
            score += 0.5
        return score
