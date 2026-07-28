# Principles

> **Published version:** <https://gaspatchio.dev/principles/>
>
> This file is the in-repo copy, kept so that contributors and AI coding agents load the
> north star with the rest of the repository rules. The published page is canonical for
> wording; if the two drift, update both. Every design decision, API addition, and
> bug-triage verdict in this repository should be justifiable against the positions below.

These are the positions the framework takes. They are not features and not selling points — they are the choices we made and the alternatives we rejected. If you disagree with one of these, the framework will feel wrong in ways no tutorial will fix. If you agree, you'll find the framework gets out of your way.

## Meet you where you are

You arrive at any new modelling tool with a working setup: tables in the shape someone published them in, formulas you know from spreadsheets, a Python skill you didn't pick up to use this framework specifically. The framework that demands you reshape your inputs before it'll talk to you, learn its proprietary DSL, or build an ETL pipeline before you write a single line of model code is the framework that gets shelved. We accept wide mortality tables, select-ultimate tables with "Ult." columns, registry conventions you didn't invent. Formulas read like spreadsheets or pure mathematical expressions, not like programs. The framework reshapes itself to you, not the other way round.

## Closed-form by default, escalation when state demands it

Recursive cell-graphs — function calling function with time offsets, evaluation order resolved at run time — were the answer when actuarial modelling first landed in Python. They are not the answer now. Most accumulations you care about have a closed form: survival probabilities are a cumulative product, discount factors are a power, account value with pre-computable charges is a linear recurrence. These run faster, read clearer, and don't require you to mentally unwind a recursion to verify a single line. We reach for the state-machine rollforward only when within-period charges actually depend on the running balance — COI on net amount at risk, IUL floor/cap, GMDB ratchet. The escalation is deliberate and explicit, not the default.

## Optimize for the laptop, not the cluster

Most actuarial modelling stacks scale by running somewhere else — overnight on a vendor batch, on a cluster IT provisioned six months ago, in a "production environment" you don't develop in. Gaspatchio targets the machine on your desk. A 100,000-policy run with monthly projections over 30 years finishes in seconds on a laptop; a million-policy run is minutes. That isn't a marketing claim about scaling up — it's a constraint we work to. The edit-run-refine loop slipping past a few seconds is the failure mode we treat as broken, and we would rather drop a capability than loosen the loop to add it.

## Audit by default, not by request

Governance is what someone bolts on after the framework is chosen, the model is built, the regulator has asked a question. We invert that order. Every output column carries expression lineage that traces back through every intermediate step. Every Schedule, Table, Curve, MortalityTable, and compiled rollforward carries an identity stamp — `source_sha()` or `fingerprint()` — that changes the moment the underlying source does. The model is auditable because we built it that way, not because you ran a separate workflow to make it so. Quarter-over-quarter drift becomes visible the moment it appears, not on page seventeen of an experience study, not in the meeting where everyone has already left.

## LLM-shaped from the inside out

You and an LLM working together is the design target, not a retrofit. The shape of the documentation — structured, executable, with a "When to use" section in actuarial language tied to runnable scalar and vector examples — exists because that's what makes retrieval hit the right answer. The shape of the error messages — actuarial concept, next move, in plain English — exists because that's what lets the next attempt converge. The shape of the retrieval surface — `gspio docs` and `gspio knowledge` as CLI commands, not an MCP server — was chosen for token efficiency, error handling, and the LLM's training data on standard CLI conventions. The agentic plugins for Claude Code, Cursor, and VS Code are the surface that uses this stack from inside the editor. Every choice points at the same target.

## Sharp knives, no magic

Frameworks that wrap calculations in decorators, DSL macros, or magic class-attribute resolution save typing but cost transparency. The reviewer or the regulator who asks "where exactly is this calculation defined?" needs an answer that isn't "it's derived from the framework's behaviour around this field name." We expose primitives; you compose them. The composition is in the code, in plain Python, with the columns visible. When the composition is wrong, the framework refuses to run rather than silently filling in a fallback that looks right until the regulator asks. Sharp knives in a competent hand are safer than blunt knives that pretend not to cut.

## No vendor lock-in, by construction

The model you build in this framework is not a hostage. Open source isn't a tagline we use because it polls well — it's a structural commitment to your professional independence. The calculation is in the code. The data is in Polars and Parquet. The model file is Python. When you move between employers, audit firms, regulators, or consultancies, the model moves with you. There is no proprietary file format that requires a licensed reader. There is no run-time on a vendor's server that disappears when the contract lapses. There is no commercial decision in someone else's boardroom that ends the ability to run last year's valuation.

---

## Using these principles

**For contributors and AI agents.** When a change is proposed — an API addition, a bug fix, a
"convenience" that saves the user some typing — name the principle it serves and the principle
it strains. Most good changes serve one and strain none. The ones worth arguing about serve one
and strain another, and those arguments should happen against these positions, in the open, not
be settled implicitly in a pull request.

**The tension you will hit most.** *Meet you where you are* pulls toward accepting whatever the
user wrote and reshaping around it. *Sharp knives, no magic* pulls toward refusing anything
ambiguous rather than guessing. They are both correct and they disagree at the boundary. The
resolution this framework uses: **be liberal about the shapes you accept, be strict about the
meanings you infer.** Accepting a wide mortality table is meeting the user where they are.
Guessing which column is the rate is magic. A clear error naming the ambiguity and the fix is
almost always better than either silently picking one or failing opaquely.

**Superseded material.** `ref/21-kaizen/01-rails-inspired-principles.md` is an earlier
Rails-doctrine exploration retained for historical context. Where it conflicts with this
document — notably its "Magic That Makes Sense" section — **this document wins.**
