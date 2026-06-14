# 30 — LLM Helpers: Discoverable CLI Skills for Agents

## Source Material

- **Analysis**: `analysis.md` — critical analysis and red-teaming of patterns for packaging CLI "skills" so LLM agents can discover and invoke them. Covers patterns from gws, OpenClaw, gh, kubectl, Gemini CLI extensions, and MCP.
- **Existing Skills**: `skills/` directory contains three agent-side SKILL.md bundles already in use (gaspatchio-discovery, gaspatchio-building, gaspatchio-reconciliation).

## Current State of Gaspatchio CLI (`gspio`)

### What Exists

| Capability | Implementation | Notes |
|---|---|---|
| CLI entry point | `gspio` via Typer | `pyproject.toml` entry point → `gaspatchio_core.cli:app` |
| Model execution | `run-model`, `run-single-policy` | Returns `ModelRunResult` (Pydantic). Output is Polars table to stdout |
| Data inspection | `describe` | Analyzes CSV/Parquet/XLSX structure. Output is human-readable |
| Knowledge search | `docs`, `knowledge` | JSON output via `model_dump_json()`. Pydantic response models |
| Calc graph export | `calc-graph` | JSON file output |
| Reconciliation | `reconcile-variable` (in gaspatchio-mix) | Uses DataCompy. Human-readable output |
| External MCP server | `mcp.gaspatchio.dev/sse` | Hosted in gaspatchio-mix, not local |
| LLM-friendly help | All commands | Help panels with guidance, tips for LLMs |
| Pydantic models | Throughout | `ModelRunResult`, `DocsSearchResponse`, `KnowledgeSearchResponse`, etc. |

### What's Missing

| Article Recommends | Status |
|---|---|
| `tools list --json` — machine-readable tool registry | Not implemented |
| `tools describe <id> --json` — JSON Schema for inputs/outputs | Not implemented |
| `tools run <id> --input @-` — stdin JSON invocation | Not implemented |
| `--dry-run` — safety rail for mutating operations | Not implemented |
| SKILL.md bundles with YAML frontmatter (in-repo) | Agent-side only (not in CLI repo) |
| `gemini-extension.json` / agent manifests | Not implemented |
| `gaspatchio.tool.json` canonical schema | Not implemented |
| Versioned schema contract | Not implemented |
| `gaspatchio dev skill init/validate/generate` | Not implemented |
| `gaspatchio.skills` entry point group | Not implemented |
| Local MCP server (from shared registry) | Not implemented |
| Risk metadata (`requires_confirmation`, `supports_dry_run`) | Not implemented |
| Path sandboxing / input validation | Not implemented |

### Architecture Gap

The article's key insight is **"one registry, many surfaces"**:

```
Registry (tool definitions + JSON Schemas)
  → CLI introspection (tools list/describe)
  → SKILL.md bundles (for OpenClaw / npx skills)
  → MCP server (tools/list + tools/call)
  → OpenAPI (optional HTTP server)
```

Gaspatchio has the surfaces (CLI commands, external MCP, agent skills) but **no unified registry** connecting them. Each surface is independently maintained.

## Mapping Existing Skills to Article's "First Three"

| Existing Skill | Article's Proposed Skill | Risk Level | Key Inputs | Key Outputs |
|---|---|---|---|---|
| `gaspatchio-discovery` | `project.setup` | write | path, template | created_files, warnings |
| `gaspatchio-building` | `model.build` | write (artifacts) | model name, config, output dir | artifact paths, build metadata |
| `gaspatchio-reconciliation` | `reconcile.run` | write (report) | left/right datasets, keys, output dir | report path, summary stats |

## Article's Recommended Migration Phases

### Phase 1: Stabilise I/O and Safety Rails
- Wrap each script behind a `gspio` subcommand that accepts JSON input and produces JSON output
- Add `--dry-run` for mutating operations
- Implement strict input validation (JSON Schema)
- Path sandboxing (reject `../`, control characters, absolute paths)

### Phase 2: Build the Skill Registry
- Create canonical registry objects (id, description, risk, args_schema, result_schema, examples)
- Implement `gspio tools list --json`, `gspio tools describe <id> --json`
- Add `gspio schema <id>` alias

### Phase 3: Generate Skill Bundles
- From the registry, generate `skills/<skill-name>/SKILL.md` with YAML frontmatter
- Generate a skills index (`docs/skills.md`)
- Add a context file (analogous to gws `CONTEXT.md`)
- Publish layout compatible with `npx skills add`

### Phase 4: Add MCP and/or OpenAPI Surfaces
- Implement local MCP server that lists tools from the same registry and invokes tool runners
- Choose stdio transport first (MCP spec standard)
- Optionally add local HTTP server with OpenAPI 3.1

## Recommended Canonical Schema: `gaspatchio.tool.json`

```json
{
  "schema_version": "gaspatchio.tool.v1",
  "id": "reconcile.run",
  "title": "Run reconciliation",
  "description": "Reconcile datasets and emit a reconciliation report.",
  "risk": {
    "level": "write",
    "requires_confirmation": true,
    "supports_dry_run": true
  },
  "requires": {
    "bins": ["gaspatchio"],
    "env": [],
    "os": ["darwin", "linux", "windows"]
  },
  "interfaces": {
    "cli": {
      "command": "gaspatchio reconcile run",
      "input_mode": "stdin_json",
      "output_mode": "stdout_json"
    }
  },
  "args_schema": { ... },
  "result_schema": { ... },
  "examples": [ ... ]
}
```

## Files in This Directory

```
30-llm-helpers/
├── README.md                              ← this file
└── skills/
    ├── gaspatchio-building.md              ← existing agent skill
    ├── gaspatchio-building-references/     ← reference files for building skill
    ├── gaspatchio-discovery.md             ← existing agent skill
    ├── gaspatchio-reconciliation.md        ← existing agent skill
    └── gaspatchio-reconciliation-references/ ← reference files for reconciliation skill
```
