# gspio docs - Framework Documentation Search

## Purpose

Search the Gaspatchio framework documentation to find API methods, code examples, accessor functions, and usage patterns. Use this command when building actuarial models and you need to understand how to use Gaspatchio features.

## Command Syntax

```bash
gspio docs <query> [OPTIONS]
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `query` | Yes | Natural language question or keywords to search for |

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--limit` | `-n` | 10 | Number of results to return (1-50) |
| `--search-type` | `-s` | hybrid | Search algorithm to use |
| `--content-type` | `-t` | None | Filter by content type (can specify multiple) |
| `--answer` | `-a` | False | Generate a synthesized answer instead of search results |

## Search Types (`-s`)

| Type | When to Use |
|------|-------------|
| `hybrid` | **Default. Best for most queries.** Combines semantic understanding with keyword matching. Use for general questions about features. |
| `semantic` | When searching by concept or meaning. Good for "how do I..." questions where exact terms may vary. |
| `keyword` | When searching for exact function or class names. Use when you know the specific method name like `previous_period` or `cumulative_survival`. |

## Content Types (`-t`)

Filter results to specific documentation types. You can specify multiple `-t` flags.

| Type | Description | When to Use |
|------|-------------|-------------|
| `code_example` | Working code snippets from docstrings and tests | When you need implementation patterns to copy/adapt |
| `overview` | Docstrings and method descriptions | When you need to understand what a feature does |
| `when_to_use` | Usage guidance and recommendations | When deciding which method to use for your task |
| `parameters` | Function signatures with parameter details | When you need API details: types, defaults, return values |

## Output Format

Returns JSON with this structure:

```json
{
  "results": [
    {
      "text": "The actual documentation content...",
      "score": 0.92,
      "content_type": "code_example",
      "source_file": "gaspatchio_core/accessors/projection.py",
      "object_path": "projection.ProjectionAccessor.cumulative_survival",
      "has_code": true
    }
  ],
  "query": "cumulative survival",
  "count": 3,
  "search_type": "hybrid",
  "took_ms": 42.5
}
```

### Result Fields

| Field | Description |
|-------|-------------|
| `text` | The documentation content (may contain code blocks) |
| `score` | Relevance score (higher is better) |
| `content_type` | Type of content: code_example, overview, when_to_use, parameters |
| `source_file` | Path to the source file containing this documentation |
| `object_path` | Python dotted path to the class/method (e.g., `projection.ProjectionAccessor.cumulative_survival`) |
| `has_code` | Whether the text contains executable code |

## What You Can Search For

### API Methods
- ActuarialFrame operations (`with_columns`, `select`, `filter`)
- Column operations and expressions
- Data loading and export methods

### Accessors
The framework provides domain-specific accessors:

| Accessor | Purpose | Example Methods |
|----------|---------|-----------------|
| `.projection` | Time-based projection operations | `cumulative_survival()`, `previous_period()`, `next_period()` |
| `.finance` | Financial calculations | `discount_factor()`, `pv()`, `npv()` |
| `.excel` | Excel function compatibility | `SUMIF()`, `VLOOKUP()`, `PMT()` |
| `.mortality` | Mortality/decrement operations | Life table lookups, qx calculations |
| `.date` | Date manipulations | Period calculations, date arithmetic |

### Code Examples
Working code patterns from tests and docstrings showing:
- How to initialize ActuarialFrame
- Common calculation patterns
- List column operations
- Conditional logic with `when().then().otherwise()`

### Function Signatures
Parameter details including:
- Required vs optional parameters
- Type annotations
- Default values
- Return types

## Search Strategies

### Strategy 1: Targeted Content Type Searches

Run separate searches for different content types to get comprehensive information:

```bash
# First understand what the feature does
gspio docs "cumulative survival" -t overview

# Then get code examples to implement it
gspio docs "cumulative survival" -t code_example

# Check the exact API signature
gspio docs "cumulative survival" -t parameters
```

### Strategy 2: Broad to Narrow

Start broad, then narrow with filters:

```bash
# Broad search to discover relevant methods
gspio docs "time shifting projection" -n 15

# Narrow to specific content after finding relevant methods
gspio docs "previous_period" -s keyword -t code_example
```

### Strategy 3: Keyword Search for Known Methods

When you know the exact method name:

```bash
gspio docs "discount_factor" -s keyword
gspio docs "cumulative_survival" -s keyword
```

### Strategy 4: Semantic Search for Concepts

When you're not sure of the exact terminology:

```bash
gspio docs "how to look up values from a table" -s semantic
gspio docs "apply mortality rates to projection" -s semantic
```

## Examples

### Find Code Examples for a Feature

```bash
gspio docs "cumulative survival" -t code_example -n 5
```

### Search All Projection Accessor Methods

```bash
gspio docs "projection accessor" -n 20
```

### Find Exact Function by Name

```bash
gspio docs "previous_period" -s keyword
```

### Get Usage Guidance for Excel Functions

```bash
gspio docs "excel pv npv" -t when_to_use
```

### Understand Time Shifting Concepts

```bash
gspio docs "time shifting" -t overview
gspio docs "time shifting" -t code_example
```

### Generate a Summary Answer

Use sparingly - prefer search results for evaluating multiple sources:

```bash
gspio docs "how do I discount cash flows?" --answer
```

## Common Queries

| Need | Query |
|------|-------|
| Initialize ActuarialFrame | `gspio docs "ActuarialFrame initialization" -t code_example` |
| Work with list columns | `gspio docs "list column operations" -t code_example` |
| Conditional logic | `gspio docs "when then otherwise" -t code_example` |
| Previous period values | `gspio docs "previous_period" -s keyword` |
| Discount factors | `gspio docs "discount factor" -t code_example` |
| Present value | `gspio docs "pv calculation" -t code_example` |
| Load assumption tables | `gspio docs "assumption table lookup"` |
| Debug mode | `gspio docs "debug mode tracing"` |

## Tips for LLMs

1. **Prefer search results over `--answer`**: Search results return multiple relevant excerpts you can evaluate against the current coding context. Use `--answer` only for quick summaries.

2. **Run multiple targeted searches**: Don't try to get everything in one query. Run 2-3 searches with different content types for comprehensive understanding.

3. **Use `object_path` for precise references**: The `object_path` field tells you exactly which class/method the documentation comes from, enabling precise code references.

4. **Check `has_code` field**: When you need implementable patterns, prioritize results where `has_code` is true.

5. **Combine with knowledge search**: Use `gspio docs` for framework implementation, and `gspio knowledge` for actuarial domain concepts.
