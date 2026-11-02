# gspio knowledge - Actuarial Knowledge Base Search

## Purpose

Search the actuarial knowledge base to find information about insurance regulations, accounting standards, mortality tables, valuation methods, and actuarial concepts. Use this command when you need domain knowledge to inform your actuarial model implementation.

## Command Syntax

```bash
gspio knowledge <query> [OPTIONS]
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
| `--retrieval-mode` | `-r` | chunks | How to retrieve content |
| `--tag` | `-T` | None | Filter by tag (can specify multiple; a result with any one matches) |
| `--jurisdiction` | `-j` | None | Filter by jurisdiction |
| `--doc-type` | `-d` | None | Filter by document type |
| `--answer` | `-a` | False | Generate a synthesized answer instead of search results |

## Search Types (`-s`)

| Type | When to Use |
|------|-------------|
| `hybrid` | **Default. Best for most queries.** Combines semantic understanding with keyword matching. |
| `semantic` | When searching by concept or meaning. Good for conceptual questions like "what is the purpose of risk adjustment?" |
| `keyword` | When searching for specific regulatory terms, acronyms, or paragraph references like "IFRS 17.44" or "SCR". |

## Retrieval Modes (`-r`)

| Mode | Description | When to Use |
|------|-------------|-------------|
| `chunks` | **Default.** Returns specific document sections with full detail. | When you need detailed information about a specific topic. |
| `summaries` | Returns document-level summaries. | When you want an overview of what documents exist on a topic. |
| `hierarchical` | Returns parent context with child details. | When you need context around a specific requirement. |

## Filters

The knowledge index stores every filter value in lower case; the CLI sends what
you type in lower case, so `-T IFRS17` and `-T ifrs17` are the same filter. The
values below are the ones the index uses. A value it does not use matches
nothing: the CLI then says so on stderr, puts the same note in the JSON
`note` field, and lists the values that exist. Run the search without the
filter to see each result's own `tags`, `jurisdiction` and `doc_type`.

Topics such as mortality, lapse, CSM, risk adjustment or LDTI are **not** tags.
Put them in the query, and use a tag to narrow the framework or line of
business.

## Tags (`-T`)

Filter results by tag. You can give `-T` more than once; a result carrying
**any one** of the tags matches, so a second tag widens the search rather than
narrowing it.

| Tag | Covers |
|-----|--------|
| `ifrs17` | IFRS 17 Insurance Contracts: CSM, risk adjustment, measurement models, transition |
| `ifrs` | IFRS material more broadly, IFRS 17 included |
| `gaap` | US GAAP, including LDTI |
| `solvency` | Solvency II and solvency regimes |
| `capital` | Capital requirements and capital modelling |
| `naic` | NAIC material: model laws, Valuation Manual, RBC |
| `reserve` | Reserving and reserve valuation |
| `life` | Life insurance and annuities, including mortality and lapse |
| `health` | Health insurance |
| `property` | Property and casualty insurance |
| `general` | Material not specific to one line or framework |

## Jurisdictions (`-j`)

Filter results by jurisdiction. Many documents carry no jurisdiction, and a
jurisdiction filter leaves those out.

| Jurisdiction | Covers |
|--------------|--------|
| `international` | IASB, IAA and other international material |
| `eu` | European Union (EIOPA, Solvency II) |
| `us` | United States (NAIC, state regulation, US GAAP) |
| `uk` | United Kingdom |
| `au` | Australia |

## Document Types (`-d`)

Filter results by type of source document. Many documents carry no type, and a
type filter leaves those out. All IFRS 17 material in the index is filed as
`standard`.

| Type | Description | When to Use |
|------|-------------|-------------|
| `standard` | Standards, and educational notes on them | When you need authoritative requirements |
| `regulation` | Regulatory text | When you need the rule itself |
| `guidance` | Guidelines and implementation guidance | When you need practical implementation advice |
| `practice-note` | Practice notes | When you need how practitioners apply a requirement |
| `comment` | Comment letters and consultation responses | When you need the debate behind a requirement |

## Output Format

Returns JSON with this structure:

```json
{
  "results": [
    {
      "text": "The Contractual Service Margin (CSM) represents...",
      "score": 0.88,
      "doc_id": "ifrs17-standard",
      "tags": ["ifrs17", "ifrs"],
      "jurisdiction": "international",
      "doc_type": "standard",
      "chunk_id": "ifrs17-standard-chunk-42",
      "chunk_index": 42,
      "page_number": 15,
      "title": "IFRS 17 Insurance Contracts"
    }
  ],
  "query": "CSM amortization",
  "count": 5,
  "search_type": "hybrid",
  "retrieval_mode": "chunks",
  "took_ms": 125.5,
  "note": null
}
```

`note` is null unless something needs saying: where the filters matched
nothing, it names them and lists the values the index uses.

### Result Fields

| Field | Description |
|-------|-------------|
| `text` | The knowledge content extracted from the document |
| `score` | Relevance score (higher is better) |
| `doc_id` | Unique identifier for the source document |
| `tags` | Topic tags associated with this content |
| `jurisdiction` | Jurisdiction (null where the document carries none) |
| `doc_type` | Type of document: standard, regulation, guidance, practice-note, comment (null where none) |
| `chunk_id` | Unique identifier for this specific chunk |
| `chunk_index` | Position of this chunk within the document |
| `page_number` | Page number in source document (if available) |
| `title` | Document title (if available) |

## Knowledge Domains

### IFRS 17 - Insurance Contracts

Key topics:
- **Measurement Models**: General Measurement Model (GMM/BBA), Premium Allocation Approach (PAA), Variable Fee Approach (VFA)
- **CSM**: Contractual Service Margin calculation, amortization, unlocking
- **Risk Adjustment**: Confidence levels, methods, disclosure
- **Discount Rates**: Bottom-up vs top-down approaches, locked-in rates
- **Transition**: Modified retrospective, fair value approach

```bash
gspio knowledge "CSM amortization" -T ifrs17
gspio knowledge "risk adjustment confidence level" -T ifrs17
gspio knowledge "PAA eligibility criteria" -T ifrs17 -d standard
```

### Solvency II

Key topics:
- **Technical Provisions**: Best estimate liabilities, risk margin
- **Capital Requirements**: SCR, MCR, internal models
- **Own Funds**: Tiering, eligibility
- **ORSA**: Own Risk and Solvency Assessment

```bash
gspio knowledge "technical provisions best estimate" -T solvency -j eu
gspio knowledge "SCR calculation" -T solvency -T capital
gspio knowledge "risk margin cost of capital" -T solvency
```

### US GAAP / LDTI

Key topics:
- **LDTI**: Long-Duration Targeted Improvements
- **Net Premium Ratio**: Calculation and assumptions
- **Market Risk Benefits**: Fair value measurement
- **DAC**: Deferred Acquisition Costs

```bash
gspio knowledge "net premium ratio" -T gaap -j us
gspio knowledge "market risk benefits" -T gaap
```

### Mortality and Decrements

Key topics:
- **Mortality Tables**: Standard tables, selection factors
- **Improvement Factors**: Mortality improvement scales
- **Morbidity**: Disability inception and termination rates
- **Lapse**: Surrender and lapse assumptions

```bash
gspio knowledge "mortality improvement factors" -T life
gspio knowledge "lapse assumptions setting" -T life
```

## Search Strategies

### Strategy 1: Jurisdiction Comparison

Compare requirements across different jurisdictions:

```bash
gspio knowledge "discount rates" -j eu      # EU approach under Solvency II
gspio knowledge "discount rates" -j us      # US approach
gspio knowledge "discount rates" -j international  # IFRS 17 approach
```

### Strategy 2: Rule vs Guidance

Get the rule, then the guidance on applying it:

```bash
# The regulation itself
gspio knowledge "principle-based reserves" -j us -d regulation

# Guidance on applying a requirement
gspio knowledge "technical provisions" -j eu -d guidance
```

### Strategy 3: Combining Filters

Tags widen, other filters narrow: a result with any one of the tags matches,
and must then also match the jurisdiction and document type given.

```bash
gspio knowledge "valuation" -T ifrs17 -T gaap          # IFRS 17 or US GAAP
gspio knowledge "capital requirements" -T solvency -T capital -j eu
```

### Strategy 4: Summaries for Overview

Start with summaries to understand document landscape:

```bash
gspio knowledge "IFRS 17" -r summaries -n 10
```

Then drill into specific chunks:

```bash
gspio knowledge "CSM unlocking" -r chunks -T ifrs17
```

### Strategy 5: Practice Notes for Applied Understanding

When you need how practitioners apply a requirement:

```bash
gspio knowledge "what is contractual service margin" -d practice-note
gspio knowledge "difference between BBA and PAA" -d practice-note
```

## Examples

### IFRS 17 CSM Guidance

```bash
gspio knowledge "CSM amortization pattern" -T ifrs17 -n 5
```

### EU Solvency II Technical Provisions

```bash
gspio knowledge "technical provisions calculation" -j eu -T solvency
```

### Mortality Table Information

```bash
gspio knowledge "mortality improvement CMI" -j uk -n 10
```

### Compare Risk Adjustment Approaches

```bash
gspio knowledge "risk adjustment methods" -T ifrs17
```

### Get Official Standard Text

```bash
gspio knowledge "insurance contract definition" -T ifrs17 -d standard
```

### Document Summaries for Topic Overview

```bash
gspio knowledge "Solvency II" -r summaries -j eu -n 10
```

### Generate a Summary Answer

Use sparingly - prefer search results for regulatory content:

```bash
gspio knowledge "what is the difference between BBA and PAA?" --answer
```

## Common Queries

| Need | Query |
|------|-------|
| CSM calculation | `gspio knowledge "CSM calculation" -T ifrs17` |
| Risk adjustment methods | `gspio knowledge "risk adjustment" -T ifrs17` |
| Discount rate methodology | `gspio knowledge "discount rates" -T ifrs17` |
| Solvency capital | `gspio knowledge "SCR" -T solvency -j eu` |
| Mortality tables | `gspio knowledge "mortality tables" -T life` |
| Lapse assumptions | `gspio knowledge "lapse assumptions" -T life` |
| PAA eligibility | `gspio knowledge "PAA eligibility" -T ifrs17 -d standard` |
| Transition requirements | `gspio knowledge "IFRS 17 transition" -T ifrs17` |

## Tips for LLMs

1. **Prefer search results over `--answer`**: Regulatory content requires careful interpretation. Search results let you evaluate multiple sources and cross-reference requirements.

2. **Use jurisdiction filters**: Actuarial requirements vary significantly by jurisdiction. Filter by jurisdiction when looking for specific regulatory requirements, and remember that documents carrying no jurisdiction drop out.

3. **Tags widen, other filters narrow**: a second `-T` adds results carrying that tag; it does not narrow to results carrying both. Put the topic (CSM, mortality, lapse) in the query and use a tag for the framework or line of business.

4. **Check `doc_type` for authority level**: Results from `standard` and `regulation` documents are authoritative requirements; `guidance` and `practice-note` documents show implementation approaches; `comment` documents record the debate around them.

5. **When a filter matches nothing, read the note**: it names the filter values the index does not use and lists the ones it does. Re-run without the filter and read each result's `tags`, `jurisdiction` and `doc_type` to choose one that exists.

6. **Use `doc_id` for citation**: When referencing regulatory content, include the `doc_id` to enable traceability back to source documents.

7. **Compare jurisdictions**: When implementing models that may be used internationally, run parallel searches across jurisdictions to understand differences.

8. **Combine with docs search**: Use `gspio knowledge` for actuarial domain knowledge, and `gspio docs` for Gaspatchio framework implementation patterns.
