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
| `--tag` | `-T` | None | Filter by tag (can specify multiple) |
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

## Tags (`-T`)

Filter results by topic tags. You can specify multiple `-T` flags.

### Regulatory Framework Tags

| Tag | Description |
|-----|-------------|
| `IFRS17` | International Financial Reporting Standard 17 - Insurance Contracts |
| `SolvencyII` | European Union insurance regulation framework |
| `USGAAP` | United States Generally Accepted Accounting Principles |
| `LDTI` | Long-Duration Targeted Improvements (US GAAP) |

### Topic Tags

| Tag | Description |
|-----|-------------|
| `mortality` | Mortality tables, improvement factors, life contingencies |
| `morbidity` | Disability, sickness, and health-related decrements |
| `lapse` | Policy lapse and surrender assumptions |
| `reserving` | Reserve calculations and methodologies |
| `pricing` | Product pricing and rate-setting |
| `valuation` | Actuarial valuation methods |
| `risk_adjustment` | Risk adjustment calculations (IFRS 17) |
| `CSM` | Contractual Service Margin (IFRS 17) |
| `discount_rates` | Interest rate and discounting methodology |
| `capital` | Capital requirements and modeling |
| `solvency` | Solvency assessment and requirements |

## Jurisdictions (`-j`)

Filter results by geographic jurisdiction.

| Jurisdiction | Description |
|--------------|-------------|
| `international` | IASB, IAA, and other international standards |
| `EU` | European Union (EIOPA, European regulations) |
| `US` | United States (FASB, state insurance regulations, NAIC) |
| `UK` | United Kingdom (PRA, FCA, UK-specific requirements) |
| `AU` | Australia (APRA, Australian regulations) |
| `CA` | Canada (OSFI, Canadian regulations) |

## Document Types (`-d`)

Filter results by type of source document.

| Type | Description | When to Use |
|------|-------------|-------------|
| `standard` | Official standards and regulations (IFRS 17 text, Solvency II Directive) | When you need authoritative regulatory requirements |
| `guidance` | Implementation guides and practice notes | When you need practical implementation advice |
| `educational` | Learning materials, tutorials, explanations | When you need conceptual understanding |
| `regulatory` | Regulatory communications, letters, FAQs | When you need regulatory interpretations |

## Output Format

Returns JSON with this structure:

```json
{
  "results": [
    {
      "text": "The Contractual Service Margin (CSM) represents...",
      "score": 0.88,
      "doc_id": "ifrs17-standard",
      "tags": ["IFRS17", "CSM"],
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
  "took_ms": 125.5
}
```

### Result Fields

| Field | Description |
|-------|-------------|
| `text` | The knowledge content extracted from the document |
| `score` | Relevance score (higher is better) |
| `doc_id` | Unique identifier for the source document |
| `tags` | Topic tags associated with this content |
| `jurisdiction` | Geographic jurisdiction (may be null for international) |
| `doc_type` | Type of document: standard, guidance, educational, regulatory |
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
gspio knowledge "CSM amortization" -T IFRS17
gspio knowledge "risk adjustment confidence level" -T IFRS17 -T risk_adjustment
gspio knowledge "PAA eligibility criteria" -T IFRS17 -d standard
```

### Solvency II

Key topics:
- **Technical Provisions**: Best estimate liabilities, risk margin
- **Capital Requirements**: SCR, MCR, internal models
- **Own Funds**: Tiering, eligibility
- **ORSA**: Own Risk and Solvency Assessment

```bash
gspio knowledge "technical provisions best estimate" -T SolvencyII -j EU
gspio knowledge "SCR calculation" -T SolvencyII -T capital
gspio knowledge "risk margin cost of capital" -T SolvencyII
```

### US GAAP / LDTI

Key topics:
- **LDTI**: Long-Duration Targeted Improvements
- **Net Premium Ratio**: Calculation and assumptions
- **Market Risk Benefits**: Fair value measurement
- **DAC**: Deferred Acquisition Costs

```bash
gspio knowledge "net premium ratio" -T USGAAP -j US
gspio knowledge "market risk benefits" -T LDTI
```

### Mortality and Decrements

Key topics:
- **Mortality Tables**: Standard tables, selection factors
- **Improvement Factors**: Mortality improvement scales
- **Morbidity**: Disability inception and termination rates
- **Lapse**: Surrender and lapse assumptions

```bash
gspio knowledge "mortality improvement factors" -T mortality
gspio knowledge "lapse assumptions setting" -T lapse
```

## Search Strategies

### Strategy 1: Jurisdiction Comparison

Compare requirements across different jurisdictions:

```bash
gspio knowledge "discount rates" -j EU      # EU approach under Solvency II
gspio knowledge "discount rates" -j US      # US approach under GAAP
gspio knowledge "discount rates" -j international  # IFRS 17 approach
```

### Strategy 2: Standard vs Guidance

Get authoritative requirements then practical guidance:

```bash
# Official requirement
gspio knowledge "risk adjustment" -T IFRS17 -d standard

# Implementation guidance
gspio knowledge "risk adjustment" -T IFRS17 -d guidance
```

### Strategy 3: Tag Combination

Combine tags for precise filtering:

```bash
gspio knowledge "valuation" -T IFRS17 -T CSM
gspio knowledge "capital requirements" -T SolvencyII -T capital -j EU
```

### Strategy 4: Summaries for Overview

Start with summaries to understand document landscape:

```bash
gspio knowledge "IFRS 17" -r summaries -n 10
```

Then drill into specific chunks:

```bash
gspio knowledge "CSM unlocking" -r chunks -T IFRS17
```

### Strategy 5: Educational Content for Understanding

When you need conceptual explanation:

```bash
gspio knowledge "what is contractual service margin" -d educational
gspio knowledge "difference between BBA and PAA" -d educational
```

## Examples

### IFRS 17 CSM Guidance

```bash
gspio knowledge "CSM amortization pattern" -T IFRS17 -n 5
```

### EU Solvency II Technical Provisions

```bash
gspio knowledge "technical provisions calculation" -j EU -T SolvencyII
```

### Mortality Table Information

```bash
gspio knowledge "mortality improvement CMI" -T mortality -n 10
```

### Compare Risk Adjustment Approaches

```bash
gspio knowledge "risk adjustment methods" -T IFRS17 -d guidance
```

### Get Official Standard Text

```bash
gspio knowledge "insurance contract definition" -T IFRS17 -d standard
```

### Document Summaries for Topic Overview

```bash
gspio knowledge "Solvency II" -r summaries -j EU -n 10
```

### Generate a Summary Answer

Use sparingly - prefer search results for regulatory content:

```bash
gspio knowledge "what is the difference between BBA and PAA?" --answer
```

## Common Queries

| Need | Query |
|------|-------|
| CSM calculation | `gspio knowledge "CSM calculation" -T IFRS17` |
| Risk adjustment methods | `gspio knowledge "risk adjustment" -T IFRS17 -T risk_adjustment` |
| Discount rate methodology | `gspio knowledge "discount rates" -T IFRS17 -d guidance` |
| Solvency capital | `gspio knowledge "SCR" -T SolvencyII -j EU` |
| Mortality tables | `gspio knowledge "mortality tables" -T mortality` |
| Lapse assumptions | `gspio knowledge "lapse assumptions" -T lapse` |
| PAA eligibility | `gspio knowledge "PAA eligibility" -T IFRS17 -d standard` |
| Transition requirements | `gspio knowledge "IFRS 17 transition" -T IFRS17` |

## Tips for LLMs

1. **Prefer search results over `--answer`**: Regulatory content requires careful interpretation. Search results let you evaluate multiple sources and cross-reference requirements.

2. **Use jurisdiction filters**: Actuarial requirements vary significantly by jurisdiction. Always filter by jurisdiction when looking for specific regulatory requirements.

3. **Combine tags strategically**: Use multiple `-T` flags to narrow results. For example, `-T IFRS17 -T CSM` is more precise than just `-T IFRS17`.

4. **Check `doc_type` for authority level**: Results from `standard` documents are authoritative requirements; `guidance` documents show implementation approaches; `educational` explains concepts.

5. **Use `doc_id` for citation**: When referencing regulatory content, include the `doc_id` to enable traceability back to source documents.

6. **Compare jurisdictions**: When implementing models that may be used internationally, run parallel searches across jurisdictions to understand differences.

7. **Combine with docs search**: Use `gspio knowledge` for actuarial domain knowledge, and `gspio docs` for Gaspatchio framework implementation patterns.
