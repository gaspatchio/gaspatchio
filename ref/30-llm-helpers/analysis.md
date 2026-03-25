# Critical Analysis: LLM Helpers for Gaspatchio Onboarding

## The Actual Goal

**Help people go from zero to minimum value using an LLM-first approach.** This is about onboarding and getting value from gaspatchio, not building generic infrastructure.

The ChatGPT article focuses on making CLIs discoverable by agents. That's a means, not the end. The end is: a new user opens Claude Code / Cursor / Gemini in a gaspatchio project and can build their first working actuarial model without reading a manual.

---

## Red-Teaming the ChatGPT Article

### What the Article Gets Right

1. **Structured JSON output matters.** If an LLM calls `gspio describe data.parquet` and gets a pretty-printed table, it has to parse prose. If it gets JSON, it can reason about the structure directly. This is the single highest-leverage change — Justin Poehnelt's article confirms this is step 1.

2. **SKILL.md + lazy loading is the real pattern emerging.** Vercel Skills (`npx skills add`) has 185K installs on its top skill, supports 27 agents. OpenClaw has 13,700+ community skills. This is not theoretical — it's the de facto standard for packaging agent context. The key insight: SKILL.md is *on-demand* context (loaded when relevant), not *always-on* context (like CLAUDE.md).

3. **Self-describing CLIs reduce hallucination.** When an agent can query `gspio docs "cumulative_survival"` at runtime instead of guessing method signatures, it gets the right answer ~95% of the time instead of ~30%. Gaspatchio already has this with `gspio docs` — that's a genuine advantage.

4. **`--dry-run` for mutating operations is genuine safety.** When an agent writes files or modifies model state, showing what *would* happen before doing it prevents costly mistakes.

### What the Article Gets Wrong (or Overstates)

1. **`tools list / tools describe / tools run` is over-engineered for gaspatchio's scale.** Gaspatchio has ~6 CLI commands, not 600. The gws CLI needs runtime introspection because it dynamically generates commands from Google's Discovery Service. Gaspatchio's commands are static and well-known. Building a formal tool registry with JSON Schema for 6 commands is ceremony that doesn't serve onboarding.

2. **`gaspatchio.tool.json` canonical schema is premature.** The article proposes a schema with `risk`, `requires`, `interfaces`, `args_schema`, `result_schema`, `examples`. This is designed for an ecosystem with third-party plugin authors. Gaspatchio doesn't have that — it has three internal skills. The schema adds maintenance burden without serving users.

3. **MCP as a local transport is actively losing ground.** Perplexity's CTO publicly moved away from MCP. Benchmarks show MCP agents need ~44K tokens vs ~1.4K for CLI agents — because MCP injects all tool schemas into every conversation. For a domain-specific tool like gaspatchio, an MCP server that lists all actuarial methods would overwhelm the context window. The existing external MCP server at `mcp.gaspatchio.dev` is the right approach — it's optional, not primary.

4. **"Phase 1: Stabilise I/O" misses the actual first problem.** New users don't struggle with I/O formats. They struggle with: "I have an Excel model and some data. How do I even start?" The article assumes users already know what commands to run and just need better input/output formatting. The real gap is upstream of that.

5. **Package-manager plugin registration (`gaspatchio.skills` entry points) is YAGNI.** Python entry points are great when third parties publish plugins. Gaspatchio's skills are first-party. Shipping them in the repo (or via `npx skills add`) is simpler and more discoverable.

6. **Agent-host extension manifests (`gemini-extension.json`) are host-specific maintenance burden.** The article suggests maintaining manifests for each agent host. Vercel Skills solved this better — one SKILL.md format works across 27 agents because hosts converge on the format, not the other way around.

### What the Article Misses Entirely

1. **The onboarding problem is a knowledge problem, not a tooling problem.** A new actuary doesn't need `gspio tools list --json`. They need the agent to know: "You're building a term life model. Start with mortality assumptions. Here's how Table and MeltDimension work. Here's what a complete 100-line model looks like." That's SKILL.md content, not CLI infrastructure.

2. **The three existing skills ARE the product.** `gaspatchio-discovery`, `gaspatchio-building`, and `gaspatchio-reconciliation` encode real workflow knowledge from actual model-building sessions. Making these discoverable and installable is higher value than any registry infrastructure.

3. **Example models are the missing onboarding asset.** The codebase has example models in `tests/scratch/models/` but they're hidden from users. A new user's agent can't find `intro_docs_example.py` unless it knows to look in scratch directories. Surfacing these as part of the skill bundles is high leverage.

4. **The `gspio docs` command is already the killer feature — but it requires an API connection.** If the API is down or the user is offline, the agent falls back to guessing. A local fallback (even a bundled snapshot of common method signatures) would make onboarding resilient.

---

## Independent Research Findings

### What's Actually Being Adopted (March 2026)

| Pattern | Adoption | Relevance to Gaspatchio |
|---|---|---|
| **SKILL.md + Vercel `npx skills add`** | 185K installs, 27 agents, Stripe shipped skills day 1 | **High** — direct path to making gaspatchio skills installable |
| **CONTEXT.md / CLAUDE.md** | Universal — every agent host supports it | **Already done** — gaspatchio has comprehensive CLAUDE.md |
| **`--output json` on CLIs** | Becoming standard practice | **Medium** — `docs`/`knowledge` already do this; `describe` and `run-model` don't |
| **`gws schema` runtime introspection** | gws only (20K stars, 3 weeks old) | **Low** — gaspatchio has 6 commands, not 600 |
| **MCP for remote services** | Broad vendor adoption (Linux Foundation) | **Already done** — external MCP server exists |
| **MCP for local CLI wrapping** | Facing backlash (Perplexity moved away) | **Low** — not needed; CLI + SKILL.md is simpler |
| **OpenClaw skill marketplace** | 13.7K skills, but security issues | **Low** — gaspatchio skills are first-party |

### The Emerging Consensus

The industry is converging on a pragmatic stack:
- **SKILL.md** for agent-side workflow knowledge (on-demand, lazy-loaded)
- **CLAUDE.md / CONTEXT.md** for always-on project context
- **Structured JSON output** from CLI commands
- **CLI tools** for local operations (not MCP)
- **Remote APIs / MCP** only for services that genuinely need dynamic discovery

---

## What Will Actually Work for Gaspatchio Onboarding

### High Value, Low Effort

1. **Package the three skills as installable Vercel Skills.** Create a `skills/` directory at the repo root with proper SKILL.md format. Users run `npx skills add gaspatchio/gaspatchio-core` and their agent immediately knows how to discover, build, and reconcile models. Works across Claude Code, Cursor, Codex, Gemini CLI.

2. **Bundle example models with the skills.** The building skill should reference concrete examples — not just patterns, but actual runnable models that the agent can copy and adapt. `intro_docs_example.py` (100 lines) is the perfect "hello world".

3. **Add `--json` flag to `gspio describe` and `gspio run-single-policy`.** These are the two commands agents call most during model building. JSON output lets the agent reason about data structure and model results programmatically.

4. **Create a "gaspatchio quick start" skill.** None of the three existing skills covers the very first step: "I just installed gaspatchio, I have some data, what do I do?" A lightweight skill that walks through installation verification, data inspection, and running the first example model.

### Medium Value, Medium Effort

5. **Add `--dry-run` to model execution.** Show what the model *would* compute (column names, shapes, assumption tables loaded) without actually running the projection. Useful for agents validating their generated model code.

6. **Local docs fallback.** Bundle a static snapshot of the most common method signatures and patterns so `gspio docs` works without the API. Even a JSON file with the top 50 methods would cover 90% of agent queries during model building.

7. **Publish as Vercel Skills package.** Once skills are in the right format, register with the Vercel skills registry so they appear in `npx skills search gaspatchio`.

### Low Value for Onboarding (Do Later or Skip)

8. **`tools list / tools describe` introspection commands.** Only useful if gaspatchio grows to 20+ commands or third-party plugins emerge. Not needed for 6 commands.

9. **`gaspatchio.tool.json` canonical schema.** Maintenance overhead without clear user benefit. The SKILL.md files + CLI help text already serve this purpose.

10. **Local MCP server from shared registry.** The external MCP server at `mcp.gaspatchio.dev` already exists. A local one adds complexity without serving the onboarding goal.

11. **`gemini-extension.json` and host-specific manifests.** Vercel Skills format works across all hosts. Don't maintain per-host manifests.

12. **Python entry points for `gaspatchio.skills` group.** No third-party plugin ecosystem to support. First-party skills ship in the repo.

---

## What Won't Work

1. **Building registry infrastructure before content.** The three existing skills contain genuine workflow knowledge from real model-building sessions. Making them discoverable is 10x more valuable than building a formal registry to describe them.

2. **Treating this as a tooling problem.** The ChatGPT article frames everything as "make the CLI machine-readable." But the actual blocker for new users is "I don't know what to do." That's a knowledge problem solved by good SKILL.md content and examples, not by JSON Schema.

3. **MCP-first approach.** MCP's token overhead (~44K tokens for tool schemas) would eat into the context window needed for actual model-building reasoning. SKILL.md's lazy loading is a better fit — load the reconciliation skill only when reconciling, not every conversation.

4. **Over-engineering versioning.** `schema_version`, `skill_version`, SemVer contracts — this matters for ecosystems with independent publishers. Gaspatchio's skills are co-versioned with the framework. Git commits are the version history.

---

## Recommended Approach

**Do the simple things that directly serve onboarding:**

1. Package existing skills as Vercel Skills (installable via `npx skills add`)
2. Bundle example models as skill reference material
3. Add `--json` to `describe` and `run-single-policy`
4. Create a "quick start" skill for the very first session
5. Add `--dry-run` to model execution

**Skip the infrastructure that serves imagined future needs:**

- Tool registries, canonical schemas, entry point groups
- Local MCP server, host-specific manifests
- Versioning contracts, plugin systems

The goal is: an actuary opens Claude Code, the agent has the gaspatchio skills loaded, and within 30 minutes they have a running model. Everything should serve that outcome.
