# CLI Knowledge Discovery Design

This document describes the design for adding knowledge discovery commands to the gspio CLI, enabling LLMs (and humans) to search Gaspatchio framework documentation and actuarial knowledge bases while building models.

## Goals

1. Make gspio discoverable by LLMs through rich `--help` output
2. Provide access to two knowledge stores via simple CLI commands
3. Keep gspio as a thin client - API handles embeddings and search
4. Guide LLMs to prefer search results over generated answers

## Commands

### `gspio docs <query>`

Search Gaspatchio framework documentation for API methods, accessors, code patterns, and examples.

**Use cases:**
- Finding how to use ActuarialFrame methods
- Discovering accessor methods (.projection, .excel, .finance, .mortality)
- Finding code examples from working models
- Looking up function signatures and parameters

### `gspio knowledge <query>`

Search the actuarial knowledge base for regulatory frameworks, concepts, and standards.

**Use cases:**
- Understanding IFRS 17, Solvency II, US GAAP requirements
- Looking up actuarial concepts (CSM, risk adjustment, PAA, BBA)
- Finding mortality, morbidity, and lapse assumption guidance
- Researching industry standards

## Options

| Flag | Description |
|------|-------------|
| `--answer`, `-a` | Return RAG-generated answer instead of search results. Use sparingly - prefer search results. |
| `--limit`, `-n` | Maximum number of results to return (default: 5) |

## Architecture

```
┌─────────────────┐     HTTP/JSON      ┌─────────────────────────────┐
│     gspio       │ ─────────────────► │          API                │
│  (thin client)  │                    │  - Embeddings               │
│                 │ ◄───────────────── │  - Vector search            │
│  - Sends query  │     JSON response  │  - Optional LLM generation  │
│  - Sends version│                    │  - LanceDB backend          │
└─────────────────┘                    └─────────────────────────────┘
```

### Key architectural decisions:

1. **gspio is a thin client** - only HTTP calls and JSON responses, no local embeddings or LanceDB dependency
2. **API handles everything** - embeddings, search, optional LLM generation
3. **Version-aware** - gspio automatically passes its version to API for version-specific docs
4. **Fail fast** - on API unavailable, return error immediately; LLM handles retries

## Output Format

Always JSON with typed schema from API.

### Search results (default)

```json
{
  "results": [
    {
      "text": "cumulative_survival() calculates the cumulative survival probability...",
      "source": "gaspatchio_core/accessors/projection.py",
      "content_type": "code_example",
      "score": 0.92
    },
    {
      "text": "The projection accessor provides actuarial-friendly methods...",
      "source": "docs/api/projection.md",
      "content_type": "markdown",
      "score": 0.87
    }
  ],
  "query": "cumulative survival",
  "version": "0.4.2"
}
```

### Generated answer (with --answer flag)

```json
{
  "answer": "To calculate cumulative survival probability, use the `.projection.cumulative_survival()` method on a decrement column...",
  "sources": [
    {"source": "gaspatchio_core/accessors/projection.py", "score": 0.92}
  ],
  "query": "how do I calculate cumulative survival?",
  "version": "0.4.2"
}
```

## LLM Discoverability

The primary mechanism for LLM discovery is rich `--help` output. LLMs will run `gspio --help` as their first discovery action.

### Discoverability strategies

1. **Direct instructions** - "IMPORTANT: Prefer search results over --answer" in command descriptions
2. **Reframe --answer as exception** - "(Use sparingly)" prefix on flag description
3. **Guidance in main --help** - Explain the preference at the top level
4. **Example annotations** - Mark preferred patterns with "← preferred" comments

### Main help output

```
 Usage: gspio [OPTIONS] COMMAND [ARGS]...

 Gaspatchio CLI for running actuarial models and discovering knowledge.

 This CLI serves two purposes:
 1. Execute actuarial models (run-model, run-single-policy)
 2. Search documentation and actuarial knowledge (docs, knowledge)

 When building a model and you need to find:
 • How to use a Gaspatchio feature → gspio docs "your question"
 • Actuarial concepts or regulations → gspio knowledge "your question"

 IMPORTANT: Always prefer search results (default) over --answer.
 Search returns multiple excerpts you can evaluate against your
 current context. Reserve --answer for quick summaries only when
 you don't need to weigh multiple options.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --version  -v   Show version and exit                                        │
│ --help          Show this message and exit                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Model Execution ────────────────────────────────────────────────────────────╮
│ run-model          Run actuarial model across all policies                   │
│ run-single-policy  Run model for one policy (debugging)                      │
│ calc-graph         Export calculation dependency graph as JSON               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Knowledge Discovery ────────────────────────────────────────────────────────╮
│ docs        Search Gaspatchio framework documentation                        │
│             (API methods, accessors, code patterns, examples)                │
│ knowledge   Search actuarial knowledge base                                  │
│             (IFRS 17, Solvency II, mortality tables, regulations)            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Data Inspection ────────────────────────────────────────────────────────────╮
│ describe    Analyze structure of assumption data files                       │
╰──────────────────────────────────────────────────────────────────────────────╯

Examples:
  gspio docs "cumulative survival probability"              # ← preferred
  gspio docs "projection accessor methods"                  # ← preferred
  gspio docs "how do I shift time?" --answer                # ← only for quick summaries
  gspio knowledge "IFRS 17 contractual service margin"      # ← preferred
  gspio knowledge "what is risk adjustment?" --answer       # ← only for quick summaries
  gspio run-model model.py data.parquet --mode debug
  gspio run-single-policy model.py data.parquet "POL001"
```

### docs command help output

```
 Usage: gspio docs [OPTIONS] QUERY

 Search Gaspatchio framework documentation.

 IMPORTANT: Prefer search results (default) over --answer.
 Search returns multiple relevant excerpts that you can evaluate
 in context. Only use --answer when you need a quick summary and
 don't have specific context requirements.

 Use this command when you need to find:
 • API methods on ActuarialFrame (e.g., "how to add a column")
 • Accessor methods (.projection, .excel, .finance, .mortality)
 • Code patterns and examples from working models
 • Function signatures and parameters

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *  QUERY  The search query - can be a question or keywords                   │
│           Examples:                                                          │
│             "cumulative survival"                                            │
│             "how do I calculate present value?"                              │
│             "when().then().otherwise() examples"                             │
│             "projection.previous_period"                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --answer  -a   (Use sparingly) Return a generated answer instead of          │
│                search results. Prefer default search - it returns            │
│                multiple results you can evaluate with your context.          │
│ --limit   -n   Maximum number of results to return (default: 5)              │
│ --help         Show this message and exit                                    │
╰──────────────────────────────────────────────────────────────────────────────╯

Examples:
  gspio docs "ActuarialFrame"                               # ← preferred
  gspio docs "how do I shift values by one period?"         # ← preferred
  gspio docs "projection accessor methods"                  # ← preferred
  gspio docs "excel pv function" -n 10                      # ← preferred
  gspio docs "what is when then otherwise?" --answer        # ← only for quick summaries
```

### knowledge command help output

```
 Usage: gspio knowledge [OPTIONS] QUERY

 Search the actuarial knowledge base.

 IMPORTANT: Prefer search results (default) over --answer.
 Search returns multiple relevant excerpts from regulatory documents
 that you can evaluate in context. Only use --answer when you need
 a quick conceptual summary.

 Use this command when you need to understand:
 • Regulatory frameworks (IFRS 17, Solvency II, US GAAP)
 • Actuarial concepts (CSM, risk adjustment, PAA, BBA)
 • Industry standards and guidance
 • Mortality, morbidity, and lapse assumptions

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *  QUERY  The search query - can be a question or keywords                   │
│           Examples:                                                          │
│             "IFRS 17 contractual service margin"                             │
│             "what is the risk adjustment?"                                   │
│             "Solvency II SCR calculation"                                    │
│             "mortality improvement factors"                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --answer  -a   (Use sparingly) Return a generated answer instead of          │
│                search results. Prefer default search - it returns            │
│                multiple excerpts you can evaluate with your context.         │
│ --limit   -n   Maximum number of results to return (default: 5)              │
│ --help         Show this message and exit                                    │
╰──────────────────────────────────────────────────────────────────────────────╯

Examples:
  gspio knowledge "IFRS 17 CSM"                             # ← preferred
  gspio knowledge "Solvency II technical provisions"        # ← preferred
  gspio knowledge "lapse rate assumptions" -n 10            # ← preferred
  gspio knowledge "risk adjustment calculation methods"     # ← preferred
  gspio knowledge "what is BBA vs PAA?" --answer            # ← only for quick summaries
```

## API Configuration

The API endpoint will need to be configurable. Options:

1. **Environment variable**: `GASPATCHIO_API_URL`
2. **Config file**: `~/.gaspatchio/config.toml`
3. **Default**: Production API URL as fallback

## Error Handling

**Fail fast approach:**
- If API is unavailable, return error message with status and exit non-zero
- LLM handles retries - no retry logic in gspio
- Clear error messages that LLM can interpret

```json
{
  "error": "API unavailable",
  "status": 503,
  "message": "Knowledge API is temporarily unavailable. Please retry."
}
```

## Implementation Notes

### Typer features to use

1. **Rich help panels** - `rich_help_panel` parameter for command grouping
2. **Epilog** - For examples section in help output
3. **Argument/Option help** - Detailed descriptions with examples
4. **Callbacks** - For version injection

### Files to modify

- `gaspatchio_core/cli.py` - Add `docs` and `knowledge` commands
- New: `gaspatchio_core/api_client.py` - Thin HTTP client for API calls

### Dependencies

- `httpx` for HTTP client (already in project via pydantic-ai)
- No new dependencies required
