"""Custom evaluators for gaspatchio skill evals.

Use built-in evaluators (Contains, EqualsExpected, LLMJudge) where possible.
Custom evaluators here handle domain-specific checks.
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.result_types import DiscoveryResult, ReviewResult, ScenarioResult


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
