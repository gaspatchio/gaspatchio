# Plugin-packaging verification gates — findings

Task 0 of the plugin-packaging plan. Schemas confirmed against LIVE post-cutoff sources
on 2026-06-27 (training memory treated as stale; everything below re-verified). Where a
doc page was unreachable, the answer is grounded in a real repo we could read.

Tooling context: local `claude --version` = **2.1.193**; `skills-ref` on npm = **0.1.5**.

---

## Gate 1 — Claude `marketplace.json` + `plugin.json` schema

**Sources fetched**
- Docs: `https://code.claude.com/docs/en/plugin-marketplaces` (full schema tables + examples)
- Docs: `https://code.claude.com/docs/en/plugins-reference` (plugin manifest schema)
- Live: `repos/anthropics/claude-plugins-official/.claude-plugin/marketplace.json`
  (download_url `https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json`),
  decoded via `gh api ... --jq .content | base64 -d`. 243 plugins; top keys
  `["$schema","name","description","owner","plugins"]`; **51 plugins use same-repo
  relative-path `source` strings** (e.g. `"./plugins/agent-sdk-dev"`).

### `marketplace.json` (`.claude-plugin/marketplace.json`)

```jsonc
{
  // REQUIRED
  "name": "gaspatchio",                 // kebab-case, public-facing; one marketplace per name per user
  "owner": { "name": "Opio", "email": "matt@opioinc.com" }, // name required, email optional
  "plugins": [ /* see plugin entry */ ],

  // OPTIONAL top-level
  "$schema": "https://json.schemastore.org/...",   // ignored at load time
  "description": "...",
  "version": "0.1.0",
  "metadata": { "pluginRoot": "./plugins" },       // prepended to relative source paths
  "allowCrossMarketplaceDependenciesOn": []
  // ("description"/"version" also accepted under "metadata" for back-compat)
}
```

**Plugin entry** (inside `plugins[]`):

```jsonc
{
  // REQUIRED
  "name": "gaspatchio",                 // kebab-case
  "source": "./",                       // string | object — see below

  // OPTIONAL (any plugin.json field is also accepted here, plus marketplace-only fields)
  "description": "...",
  "version": "0.1.0",                   // omit -> git commit SHA is the version
  "author": { "name": "Opio", "email": "matt@opioinc.com" },
  "homepage": "https://...",
  "repository": "https://github.com/opioinc/gaspatchio-core",
  "license": "Apache-2.0",
  "keywords": ["actuarial", "..."],
  "category": "...",                    // marketplace-only
  "tags": ["..."],                      // marketplace-only
  "strict": true,                       // marketplace-only; default true
  "displayName": "Gaspatchio",          // v2.1.143+
  "defaultEnabled": true,               // v2.1.154+
  // component-path fields: skills | commands | agents | hooks | mcpServers | lspServers
  "skills": ["./skills/"]
}
```

**`source` forms (all confirmed valid):**
- Relative path `string`, **must start with `./`**, resolves to marketplace **root** (the dir
  containing `.claude-plugin/`), NOT the `.claude-plugin/` dir. No `..`.
- `{ "source": "github", "repo": "owner/repo", "ref"?, "sha"? }`
- `{ "source": "url", "url": "...", "ref"?, "sha"? }`
- `{ "source": "git-subdir", "url": "...", "path": "...", "ref"?, "sha"? }`
- `{ "source": "npm", "package": "...", "version"?, "registry"? }`

### Same-repo `source: "./"` entry — CONFIRMED VALID

The docs explicitly document the marketplace-root pattern for a plugin that lives in the same
repo as its marketplace (plugins-reference + plugin-marketplaces "Advanced plugin entries"):

```jsonc
// marketplace.json plugin entry — plugin == the repo root
"source": "./",
"skills": ["./skills/code-review", "./skills/docs"]
```

Key rule for `source: "./"`: when `skills` lists specific subdirs, **those listed paths are
the COMPLETE set** for that entry — sibling dirs under `skills/` do NOT load. To keep the full
auto-scan, list `"./skills/"` itself (or the plugin root), or omit `skills` entirely.

### `plugin.json` (`.claude-plugin/plugin.json`)

```jsonc
{
  // REQUIRED — name is the ONLY required key (manifest itself is optional)
  "name": "gaspatchio",                 // kebab-case, used for component namespacing

  // OPTIONAL metadata
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json", // ignored at load
  "displayName": "Gaspatchio",          // v2.1.143+
  "version": "0.1.0",                   // omit -> git SHA; plugin.json wins over marketplace entry
  "description": "...",
  "author": { "name": "Opio", "email": "matt@opioinc.com" },
  "homepage": "https://...",
  "repository": "https://...",
  "license": "Apache-2.0",
  "keywords": ["actuarial"],            // MUST be an array — string is a load error
  "defaultEnabled": true,               // v2.1.154+

  // OPTIONAL component-path fields (string | array; some accept object)
  "skills": "./skills/",                // string | array — see below
  "commands": "./commands/",
  "agents": "./agents/",
  "hooks": "./hooks/hooks.json",        // string | array | object
  "mcpServers": "./.mcp.json",          // string | array | object
  "outputStyles": "./output-styles/",
  "lspServers": "./.lsp.json"           // string | array | object
}
```

**`"skills": "./skills/"` dir-glob — CONFIRMED VALID.** `skills` is `string | array`
("Custom skill directories containing `<name>/SKILL.md`"). It **ADDS to** the default
`skills/` scan rather than replacing it (exception: the `source: "./"` marketplace-root case
above, where listing subdirs replaces the scan). **If `skills` is omitted, Claude Code
auto-scans the `skills/` directory by default** — so a plugin whose skills live in `./skills/`
needs no `skills` field at all. Confirmed in the wild: `obra/superpowers`
`.claude-plugin/plugin.json` omits `skills` and relies on the root `skills/` auto-scan.

**Contradiction vs. plan's best-known shapes:** none for Gate 1. Note two refinements the
generator should honor: (a) `keywords` must be an array (string = hard load error, not a
warning); (b) for a `source: "./"` entry, listing specific `skills` subdirs is exhaustive —
to keep all skills either omit `skills` or list `"./skills/"`.

---

## Gate 2 — In-place discovery: do we need `.agents/skills/` copies?

### VERDICT: **NO.** Manifests/locations point at ONE skills tree. No physical copies required.

**Deciding evidence (live repos + docs):**

1. **`obra/superpowers` — the canonical multi-tool pattern.** ONE physical `skills/` tree at
   repo root (brainstorming, test-driven-development, …). Each tool gets a thin per-tool
   manifest that POINTS at that one tree; there is **no `.agents/skills/` and no per-tool
   skills copy**:
   - `.cursor-plugin/plugin.json` → `"skills": "./skills/"` (+ `"hooks": "./hooks/hooks-cursor.json"`)
   - `.codex-plugin/plugin.json`  → `"skills": "./skills/"` (+ `hooks-codex.json`)
   - `.kimi-plugin/`, `.claude-plugin/` present; `.claude-plugin/plugin.json` **omits** `skills`
     (relies on Claude's root `skills/` auto-scan).
   - `gh api repos/obra/superpowers/contents/.agents` → **404** (it does NOT use `.agents/skills/`).

2. **GitHub Copilot accepts `.claude/skills` directly.** Copilot scans **three alternative**
   project-skill locations — `.github/skills`, `.claude/skills`, `.agents/skills` — "none is
   mandatory; Copilot checks all three." So pointing Copilot at our existing `.claude/skills`
   (or root `skills/` via its plugin) needs **no `.agents/skills/` duplicate**.

3. **Cursor** reads `skills` as a manifest path field (`"skills": "./skills/"`, string|array) —
   a pointer, not a fixed physical location.

4. `flutter/devtools` DOES use `.agents/skills/` — but that is the generic `AGENTS.md`/`.agents/`
   convention for tools with no plugin manifest, NOT a requirement imposed on tools that have a
   manifest pointer. It is an option, not an obligation.

**So:** keep a single `skills/` tree; let each tool's manifest (or accepted location) point at
it. Only generate an `.agents/skills/` if we deliberately target a manifest-less consumer — and
even then prefer a symlink over a copy.

---

## Gate 3 — Cursor + Copilot manifest schemas (with exact paths)

### Cursor — `.cursor-plugin/plugin.json`

**Source:** `https://cursor.com/docs/plugins` and `https://cursor.com/docs/reference/plugins`;
live `repos/obra/superpowers/.cursor-plugin/plugin.json`.

```jsonc
{
  // REQUIRED — name only
  "name": "gaspatchio",                 // lowercase kebab-case

  // OPTIONAL metadata
  "displayName": "Gaspatchio",
  "description": "...",
  "version": "0.1.0",
  "author": { "name": "Opio", "email": "matt@opioinc.com" },
  "homepage": "https://...",
  "repository": "https://...",
  "license": "Apache-2.0",
  "keywords": ["actuarial"],
  "logo": "./assets/logo.png",          // relative path or absolute URL

  // OPTIONAL component-path fields (string | array unless noted)
  "rules": "./rules/",
  "agents": "./agents/",
  "skills": "./skills/",                // "Path(s) to skill directories" — CONFIRMED
  "commands": "./commands/",
  "hooks": "./hooks/hooks-cursor.json", // string | object
  "mcpServers": "./.mcp.json"           // string | object | array
}
```

Live confirmation (superpowers `.cursor-plugin/plugin.json`): keys present =
`name, displayName, description, version, author, homepage, repository, license, keywords,
skills, hooks`; `skills` value = the **string** `"./skills/"`.

### GitHub Copilot — `.github/plugin/marketplace.json`

**Source:** `https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-marketplace`;
Changelog `https://github.blog/changelog/2025-12-18-github-copilot-now-supports-agent-skills/`;
live `repos/Azure/agentops/.github/plugin/marketplace.json` (official Microsoft repo).

- **Path:** `.github/plugin/marketplace.json`. (Copilot CLI **also** reads
  `.claude-plugin/marketplace.json` — so one Claude marketplace file can double for Copilot.)
- **`marketplace.json` is the only required component** of a Copilot plugin marketplace.
  Docs mention **no separate per-plugin `plugin.json`**; the live Azure repo has none under
  `.github/plugin/` (its plugin body lives at `plugins/agentops/` with its own `plugin.json`
  + a physical `skills/` subdir, referenced by `source`).

```jsonc
// .github/plugin/marketplace.json — schema mirrors Claude's marketplace.json
{
  "name": "gaspatchio",
  "owner": { "name": "Opio", "email": "matt@opioinc.com" },
  "metadata": { "description": "...", "version": "0.1.0" },  // also accepts top-level description/version
  "plugins": [
    {
      "name": "gaspatchio",
      "description": "...",
      "version": "0.1.0",
      "source": "./"            // path to plugin dir, RELATIVE TO REPO ROOT;
                                 // "./plugins/x" and "plugins/x" are equivalent (leading ./ optional)
    }
  ]
}
```

Live shape (Azure/agentops, verbatim keys): top = `name, metadata{description,version},
owner{name,email}, plugins[]`; plugin entry = `name, source, description, version, keywords,
license, repository`, with `source: "../../plugins/agentops"`.

> Note on `source` paths: Azure resolves `source` **relative to the marketplace file** and
> uses `../../` to escape `.github/plugin/`. The Copilot docs instead state `source` is
> **relative to the repo root** (and `./` optional). These differ; the docs are authoritative —
> prefer a **repo-root-relative** `source` (e.g. `"./"` for a root plugin). This is a place
> where a real repo and the docs disagree; the generator should follow the docs.

**Copilot skills physical locations** (any one, no copies needed): `.github/skills`,
`.claude/skills`, **or** `.agents/skills`. Our existing `.claude/skills` / root `skills/` is
directly acceptable.

---

## Gate 4 — Validators

**`claude plugin validate <path>` — EXISTS and runs locally.** Verified `claude --version`
= 2.1.193; `claude plugin validate --help` prints:

```
Usage: claude plugin validate [options] <path>
Validate a plugin or marketplace manifest
Options:
  --strict   Treat warnings as errors (exit 1). Use in CI to fail on unrecognized
             fields, missing metadata, and other issues the runtime tolerates.
```

- Pointed at a marketplace dir → checks `marketplace.json`: schema, duplicate plugin names,
  source path-traversal, version mismatch vs each referenced `plugin.json`.
- Pointed at a plugin dir → checks `plugin.json` + skill/agent/command/hook frontmatter.
- `--strict` turns unrecognized-field / missing-metadata WARNINGS into errors (CI gate).
- Use it as the **primary** Claude-side CI gate: `claude plugin validate . --strict`.

**`skills-ref validate` — EXISTS (third-party, not official Anthropic).** npm `skills-ref@0.1.5`
(MIT, "Reference library for Agent Skills", bin `skills-ref`). The published `dist/cli.js`
registers subcommands `read-properties`, `to-prompt`, **`validate`**. Install:
`npm i -D skills-ref` (or `npx skills-ref validate <path>`). Validates SKILL.md
frontmatter/structure — complements `claude plugin validate` (which validates manifests).

- No `@agentskills/cli` or `skills-ref-validate` package exists (both npm 404).

**Recommendation:** gate manifests with `claude plugin validate . --strict` in CI; optionally
add `npx skills-ref validate skills/` for SKILL.md structure; keep the pytest structural guards
as the always-available fallback (no network / no npm needed).

---

## Source URLs actually fetched

- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/plugins-reference
- `gh api repos/anthropics/claude-plugins-official/contents/.claude-plugin/marketplace.json`
  (raw: https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json)
- `gh api repos/obra/superpowers/contents/{.cursor-plugin,.codex-plugin,.claude-plugin}/plugin.json`,
  `.../contents/skills`, `.../contents/.agents` (404)
- `gh api repos/flutter/devtools/contents/.agents/skills`
- `gh api repos/Azure/agentops/contents/.github/plugin/marketplace.json`,
  `.../contents/plugins/agentops`, `.../contents/plugins/agentops/skills`
- https://cursor.com/docs/plugins , https://cursor.com/docs/reference/plugins
- https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-marketplace
- https://docs.github.com/en/copilot/concepts/agents/about-agent-skills
- https://github.blog/changelog/2025-12-18-github-copilot-now-supports-agent-skills/
- npm: `skills-ref@0.1.5` (inspected published `dist/cli.js`); local `claude` 2.1.193
