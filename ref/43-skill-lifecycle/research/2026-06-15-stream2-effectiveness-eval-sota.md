# Research Stream 2 — Testing whether a skill/prompt makes an LLM behave correctly

**Date:** 2026-06-15 · primary-source brief · `VERIFIED` = official docs/papers; `INFERENCE` = labelled.

---

## 1. Eval frameworks
**Anthropic `skill-creator` (closest analogue) [VERIFIED]:** four agents — Executor (runs skill → transcript), Grader (assertions → PASS/FAIL with evidence), Comparator (blind A/B between versions), Analyzer (flags non-discriminating/flaky evals). **With-skill vs baseline ablation is core:** "spawn two subagents in the same turn — one with the skill, one without … don't spawn the with-skill runs first and then come back for baselines later." Programmatic assertions preferred ("scripts are faster, more reliable, reusable"). Aggregates pass rate + timing + tokens + delta vs baseline. Anti-overfit: identical with/baseline pass rates → "make your test cases harder." Cisco software-security skill: 1.78x improvement across 23 categories.

**Anthropic "Demystifying evals for AI agents" [VERIFIED]:** vocabulary Task/Trial/Grader/Transcript/Outcome. Grader types: code-based (fast, objective, "brittle to valid variations"), model-based (nuance, non-deterministic, "requires calibration with human graders"), human (gold, for calibration). "Grade outcomes rather than specific tool-call sequences." "A good task is one where two domain experts would independently reach the same verdict." Start with 20–50 tasks from real failures; positive + negative cases; isolate environments; read the transcripts.

**Inspect AI (UK AISI) [VERIFIED]:** Dataset → Solver(s) → Scorer(s); text-match/model-graded/custom scorers; sandboxes; 200+ evals. Strongest provenance.

**promptfoo [VERIFIED]:** declarative YAML; assertions incl. llm-rubric, g-eval, select-best, multi-judge voting; CI gates via non-zero exit; thresholds by parsing JSON pass ratio (e.g. fail <95%).

**DeepEval [VERIFIED]:** "pytest for LLMs"; `deepeval test run` native pytest/CI; G-Eval = CoT LLM-judge against NL criteria.

**Ragas [VERIFIED]:** RAG metrics (faithfulness, answer relevancy, context precision/recall) — relevant only for skills that retrieve API docs.

OpenAI Evals / LangSmith / Braintrust — same dataset+grader+CI shape [INFERENCE].

## 2. LLM-as-judge failure modes
**Zheng et al., MT-Bench, NeurIPS 2023 (arXiv 2306.05685) [VERIFIED]:** GPT-4 vs humans 85% agreement (> human–human 81%). **Position bias:** order-consistency Claude-v1 23.8%, GPT-3.5 46.2%, GPT-4 65.0% → run both orderings, accept only if consistent. **Verbosity bias:** repetitive-list attack fooled Claude-v1/GPT-3.5 91.3%, GPT-4 8.7%. **Self-enhancement:** GPT-4 ~+10pp, Claude-v1 ~+25pp toward own answers. **Math/reasoning:** default judge 14/20 wrong; CoT → 6/20; **reference-guided → 3/20**. Endorsed mitigations: swap-and-average, CoT, reference-guided, few-shot.

**Code specifically [VERIFIED]** (arXiv 2507.16587): "even … GPT-4 [is] unable to reliably determine if a piece of code works without executing it … hallucinations and poor bug detection."

## 3. Execution-based beats judge for code
**SWE-bench [VERIFIED]:** resolved iff designated fail→pass tests pass AND pass→pass tests still pass; metric = resolution rate; pass@k. **[VERIFIED]** "When correct answers are known and enumerable, such as code that must pass tests, rule-based checking is more reliable and cheaper than LLM judges." [INFERENCE, load-bearing] Our skills emit runnable code; we have a numeric oracle (`gspio run-model` → parquet → reconcile; L4 lifelib 0.0000%) — the most reliable grader class available.

## 4. Non-determinism & statistics
**Thinking Machines [VERIFIED]:** root cause is batch-invariance, not just FP/sampling; at temperature 0 Qwen3-235B gave 80 unique completions across 1000 identical requests. "A passing test is a data point, not a verdict." Push true determinism into deterministic post-processing / non-LLM rule layer.

**Anthropic "Statistical approach to model evals" [VERIFIED]:** report SEM; **clustered standard errors** on the unit of randomization (naive SEs understate >3x); **paired analysis** on the same question list slashes variance. **pass@k** (optimistic) vs **pass^k** (all k succeed — reliability). For a reliable skill, pass^k is honest; pass@1 with CI is the reportable default.

**Overfitting [VERIFIED]** ("When Better Prompts Hurt", arXiv 2601.22025): generic prompt tweaks that raise eval scores can regress production; antidotes = held-out sets, multiple eval methods, distribution-shift monitoring.

## 5. Skill effectiveness (ablation/lift)
**[VERIFIED]** with-skill vs without-skill ablation is the accepted proof (Anthropic skill-creator; tool-ablation literature: ~18% compile-success drop removing a tool). **Caveat:** lift is conditional on base-model capability (weak models can't exploit a skill). [INFERENCE] Report lift **per model**, not pooled.

## Implications
1. Adopt Task/Trial/Grader/Transcript/Outcome + Executor/Grader/Comparator/Analyzer.
2. **Execution-based scoring dominant** — numeric reconciliation oracle; fail→pass-style assertion sets + "doesn't break".
3. **Mandatory with/without paired ablation**, same turn, **lift per model** (clustered SEM); if with==without, harden the task.
4. LLM-judge **only** for subjective sub-criteria, reference-guided + position-swapped; never replaces execution for "does the math come out right."
5. **CI gate on positive significant lift / lift regression**, not raw pass-rate floor; pass^k for reliability, pass@1+SEM elsewhere.
6. Non-determinism: temperature 0 necessary not sufficient; multi-trial; determinism in the oracle.
7. Anti-overfit: held-out set; Analyzer flags always-pass assertions; monitor eval-vs-production drift.

**AVOID:** LLM-judge as primary code-correctness grader; single-sample/temp-0-reproducible assumptions; pooling lift across models; grading exact tool-call sequences/output strings; unclustered SEs; a model judging its own outputs in cross-model comparison.

### Key sources
github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md · anthropic.com/engineering/demystifying-evals-for-ai-agents · anthropic.com/research/statistical-approach-to-model-evals · arXiv 2306.05685 · SWE-bench (arXiv 2509.16941) · arXiv 2507.16587 / 2507.10535 · thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference · arXiv 2407.10457 · arXiv 2601.22025 · inspect.aisi.org.uk · promptfoo.dev/docs · deepeval.com/docs · docs.ragas.io · tessl.io (Cisco 1.78x)
