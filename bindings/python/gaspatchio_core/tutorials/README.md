# Gaspatchio Tutorial

A progressive tutorial for building actuarial models with gaspatchio. Each level introduces new concepts while producing a working model you can run and inspect.

The tutorial is designed for actuaries who know Excel and are learning Python-based modeling. The models themselves teach the Python -- you don't need prior Python experience to start.

## How to use this tutorial

**Levels** increase in model complexity: from a minimal projection to a production-quality reconciled model. Each level is self-contained -- you can start at any level that matches your experience.

**Base models** are the simplest working version of each level. Start here to understand the structure before adding complexity.

**Steps** (within Level 3) add one feature at a time to the base model. Each step changes only one section of the model, so you can see exactly what changed and why. Steps are cumulative: Step 03 includes everything from Steps 01 and 02.

Every model follows the same section structure (time setup, mortality, lapse, account value, policy counts, claims, premiums, expenses, discounting), so concepts transfer directly between levels.

## Levels

| Level | Name | What you'll learn | Prerequisites | Status |
|---|---|---|---|---|
| 1 | Hello World | Create an ActuarialFrame, run a 1-variable projection, inspect output | None | Ready |
| 2 | Assumptions | Load assumption tables, `Table.lookup()`, `when/then/otherwise` | Level 1 | Ready |
| 3 | Mini Variable Annuity | Full VA projection: mortality, lapse, AV, claims, discounting. 6 incremental steps from inline data to rate-curve discounting | None (base model is self-contained) | Ready |
| 4 | Reconciled Lifelib Model | Production model reconciled against lifelib IntegratedLife at 0.0000% across 1,016 model points (IF + NB), 35 variables, ~9M data points. Uses `accumulate()` for AV rollforward. | Level 3 Steps 01-05 | Ready |
| 5 | Scenarios | Deterministic scenario analysis: interest rate scenarios, parameter shocks, sensitivity sweeps, regulatory-style reports with Altair charts | Level 4 | Ready |
| 6 | Monte Carlo & Performance | Stochastic scenarios, risk metrics (VaR, CTE), batching, performance at scale | Level 5 | Coming soon |

## Quick start

**Start with Level 1 base** if you're new to gaspatchio, or **Level 3 base** if you want a complete VA model to study.

The Level 1 base model (`level-1-hello-world/base/model.py`) is about 60 lines and covers the four core concepts: ActuarialFrame, column arithmetic, `when/then/otherwise`, and `.collect()`. Work through Steps 01-03 in order to add projections, survival, and per-period cashflows.

```bash
# Run the Level 1 base model
uv run python tutorial/level-1-hello-world/base/model.py
```

The Level 3 base model (`level-3-mini-va/base/model.py`) is a complete variable annuity projection in a single file with inline data -- no external files needed. The docstring at the top of the file explains every gaspatchio concept you need.

```bash
# Run the Level 3 base model
uv run python tutorial/level-3-mini-va/base/model.py
```

Read the docstring, read the code section by section, then run it. Once you understand the base, work through the steps in order (01 through 06) to see how each feature is added.

## Level 3 steps

| Step | Name | What it adds |
|---|---|---|
| 01 | From Files | Load data from parquet files instead of inline dicts |
| 02 | Select Mortality | Select/ultimate mortality tables, multi-key lookup, mortality scalars |
| 03 | Guarantees | GMDB, GMAB guarantees, surrender charges, nested conditionals |
| 04 | Dynamic Lapse | ITM ratio, dynamic lapse formula, duration-based lapse tables |
| 05 | Rate Curves | Risk-free rate curve discounting, term-structure lookup |
| 06 | Reconcile | Bridge to Level 4 -- 4 actuarial gaps discovered and fixed via reconciliation against lifelib |

## Level 5 steps

| Step | Name | What it adds |
|---|---|---|
| Base | Interest Rate Scenarios | `with_scenarios()` for BASE/UP/DOWN, grouped bar + waterfall charts |
| 01 | Parameter Shocks | Declarative JSON shocks, `Table.with_shock()`, tornado chart |
| 02 | Conditional Shocks | `where` filters, `when` time conditions, `pipeline` chains, cashflow line charts |
| 03 | Sensitivity Analysis | 1D sweeps via `sensitivity_analysis()`, 2D heatmap interaction grid |
| 04 | Scenario Comparison | Named regulatory scenarios, audit trail, full stress test report |

## Running models

There are three ways to run any tutorial model.

**Standalone Python** -- run the model directly. Good for a quick check.

```bash
uv run python tutorial/level-3-mini-va/base/model.py
```

**Single policy** -- run one policy through the CLI and see every computed variable. This is the primary debugging tool.

```bash
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/01-from-files/model.py \
    tutorial/level-3-mini-va/steps/01-from-files/data/model_points.parquet 1
```

Add `--output-file /tmp/result.parquet` to save the output for further analysis.

**All policies** -- run the full model point set.

```bash
uv run gspio run-model tutorial/level-3-mini-va/steps/01-from-files/model.py \
    tutorial/level-3-mini-va/steps/01-from-files/data/model_points.parquet
```

The base model uses inline data, so it only needs the first form. Steps 01 onward load data from files and can use all three forms.

## On-ramps

Each level can be started independently if you have the right background:

- **New to gaspatchio?** Start at Level 1 base. It's 60 lines and covers the four core concepts. Then work through Steps 01-03 before moving to Level 2.
- **Know DataFrames but not gaspatchio Tables?** Start at Level 2 base. It adds `Table.lookup()` to Level 1's projection. Steps 01-04 build to multi-dimension Tables, external files, and conditionals.
- **Want the full picture first?** Start at Level 3 base. The docstring teaches every gaspatchio concept in detail.
- **Comfortable with ActuarialFrame and `Table.lookup()`?** Jump to any Level 3 step that covers the feature you need.
- **Ready to build a production model?** Go to Level 4. It applies everything from Level 3 with real assumption data.
- **Know lifelib's appliedlife model?** Level 4 maps 1:1 to IntegratedLife. Compare the gaspatchio and lifelib implementations side by side.
- **Need scenario analysis?** Level 5 covers deterministic scenarios, parameter shocks, sensitivity sweeps, and regulatory-style reports with Altair charts.

## AI-assisted model building

gaspatchio includes skills for AI coding assistants (Claude Code, Copilot, Cursor). Each skill can be used independently:

| Skill | What it does |
|---|---|
| **quickstart** | Get from zero to running model in 10 minutes |
| **model-discovery** | Socratic method to understand what to build before writing code |
| **model-building** | Write model code with gaspatchio best practices and incremental validation |
| **model-review** | Review model changes — gaspatchio code quality + actuarial standards (ASOP 56) |
| **model-reconciliation** | Match a model against a reference implementation (Excel, lifelib, etc.) |
| **model-scenarios** | Run scenarios, shocks, sensitivity analysis with professional reports |

Skills are in the `skills/` directory at the repo root.

## Directory structure

```
tutorial/
├── README.md                    <- this file
├── level-1-hello-world/
│   ├── README.md                <- overview and quick-start
│   ├── base/model.py            <- 3 policies, scalar arithmetic, no projections
│   └── steps/
│       ├── 01-projections/      <- add time dimension (list columns)
│       ├── 02-survival/         <- add cumulative survival
│       └── 03-time-shifting/    <- add previous_period, per-period deaths
├── level-2-assumptions/
│   ├── README.md                <- overview and quick-start
│   ├── base/model.py            <- mortality from Table (age lookup)
│   └── steps/
│       ├── 01-multi-dimension/  <- age × sex mortality Table
│       ├── 02-from-files/       <- load data from parquet files
│       ├── 03-lapse/            <- lapse rate Table, combined decrements
│       └── 04-conditionals/     <- when/then/otherwise on list columns
├── level-3-mini-va/
│   ├── base/model.py            <- inline data, simplest VA model
│   └── steps/
│       ├── 01-from-files/       <- data from parquet files
│       ├── 02-select-mort/      <- select/ultimate mortality + scalars
│       ├── 03-guarantees/       <- GMDB, GMAB, surrender charges
│       ├── 04-dynamic-lapse/    <- ITM ratio, dynamic lapse formula
│       ├── 05-rate-curves/      <- risk-free rate curve discounting
│       └── 06-reconcile/        <- bridge to Level 4
└── level-4-lifelib/
    ├── README.md
    ├── reconcile.py             <- verify model matches lifelib
    ├── reference/
    │   └── lifelib_reference.parquet  <- lifelib PV output for comparison
    └── base/                    <- 860-line reconciled appliedlife model
        ├── model.py
        ├── model_points.parquet
        └── assumptions/         <- 14 parquet files
└── level-5-scenarios/
    ├── README.md
    ├── charts.py                <- shared Altair chart helpers
    ├── base/
    │   ├── model.py             <- scenario-ready L4 model
    │   ├── run_scenarios.py     <- BASE/UP/DOWN rate scenarios
    │   └── assumptions/         <- full copy from L4
    └── steps/
        ├── 01-parameter-shocks/ <- declarative JSON shocks, tornado chart
        ├── 02-conditional-shocks/ <- where/when/pipeline shocks
        ├── 03-sensitivity/      <- 1D sweep + 2D heatmap
        └── 04-scenario-comparison/ <- regulatory stress test report
```
