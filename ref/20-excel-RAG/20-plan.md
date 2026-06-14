# Gaspatchio Documentation RAG Pipeline & MCP Server Plan

## Executive Summary

This document outlines the architecture and implementation plan for a Retrieval Augmented Generation (RAG) pipeline that will enable actuaries to write "Gaspatchio style" code through an MCP (Model Context Protocol) server. The system will index Gaspatchio docstrings, code examples, and Excel-namespace function examples to provide contextual assistance.

## Goals & Objectives

1. **Primary Goal**: Enable actuaries to write idiomatic Gaspatchio code by providing relevant examples and documentation through an MCP extension
2. **Secondary Goals**:
   - Reduce onboarding time for new Gaspatchio users
   - Capture and surface Excel-equivalent function patterns
   - Provide contextual code examples based on user intent
   - Enable discovery of Gaspatchio functions and patterns

## Architecture Overview

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Docstring Parser   │────▶│  Chunking Engine │────▶│ Vector Database │
│  (10-docstring)     │     │  (txtai)         │     │ (pg-vector/     │
└─────────────────────┘     └──────────────────┘     │  supabase)      │
                                     │                └─────────────────┘
┌─────────────────────┐              │                         │
│  Excel function examples      │──────────────┘                         │
│  & Examples         │                                         │
└─────────────────────┘                                         │
                                                               ▼
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  MCP Client         │◀────│  FastMCP Server  │◀────│  Search Layer   │
│  (IDE Extension)    │     │                  │     │  (BM25 + Vector)│
└─────────────────────┘     └──────────────────┘     └─────────────────┘
```

## Component Design Options

### 1. Data Ingestion & Processing

#### Option A: Multi-Stage Chunking Pipeline
```python
# Chunk Types:
1. Function Overview (name, short_description, parameters)
2. Code Examples (individual examples with context)
3. Usage Patterns (when_to_use sections)
4. Excel function examples (Gaspatchio equivalents of common Excel functions)
```

**Pros**: 
- Fine-grained retrieval control
- Can weight different chunk types differently
- Easier to update individual components

**Cons**: 
- More complex indexing
- Potential for losing context between chunks

#### Option B: Hierarchical Document Structure
```python
# Document Hierarchy:
- Module
  └── Class/Function
      ├── Full Documentation
      ├── Examples Collection
      └── Related Excel Patterns
```

**Pros**: 
- Preserves contextual relationships
- Simpler mental model
- Better for "show me everything about X" queries

**Cons**: 
- Larger chunks may dilute relevance
- Harder to find specific examples

**Recommendation**: Hybrid approach - index both granular chunks AND full documents with different weights

## Deep Dive: Data Ingestion & Chunking Strategies

### Understanding User Query Patterns

Before diving into chunking strategies, let's analyze typical actuary user queries:

1. **Navigational Queries** (30%)
   - "How do I use yearfrac in Gaspatchio?"
   - "What's the Gaspatchio equivalent of VLOOKUP?"
   - "Show me the date functions"

2. **Conceptual Queries** (40%)
   - "How do I calculate policy duration with roll forward?"
   - "Show me the Gaspatchio equivalent of an Excel mortality-table lookup"
   - "How to handle CSO tables in Gaspatchio?"

3. **Code Completion Queries** (20%)
   - "I have `af['effective_date']` - how do I extract the year?"
   - "Complete this: `gs.assumption_lookup(...)`"
   - "Fix this code: [snippet with error]"

4. **Learning Queries** (10%)
   - "Show me examples of complex date calculations"
   - "What's the best practice for assumption tables?"
   - "Explain ActuarialFrame vs DataFrame"

### Chunking Strategy Deep Dive

#### Strategy 1: Semantic Function Chunking

Break down each function/method into semantically meaningful pieces:

```python
# Example: DtNamespaceProxy.year() chunking
chunks = [
    {
        "chunk_id": "dt-year-signature",
        "type": "function_signature",
        "content": "af['date_column'].dt.year() -> 'ColumnProxy'",
        "semantic_tags": ["datetime", "extraction", "year", "property"],
        "parent_path": "gaspatchio_core.column.dt.year"
    },
    {
        "chunk_id": "dt-year-description",
        "type": "function_description", 
        "content": "Extract the year from the underlying datetime expression. Corresponds to Polars Expr.dt.year().",
        "semantic_tags": ["datetime", "year", "polars-equivalent"],
        "parent_path": "gaspatchio_core.column.dt.year"
    },
    {
        "chunk_id": "dt-year-example-1",
        "type": "code_example",
        "content": """
import polars as pl
import gaspatchio_core as gs
data = {"d": ["2020-01-01", "2021-12-31"]}
af = gs.ActuarialFrame(pl.LazyFrame(data).with_columns(pl.col("d").str.to_date()))
year_expr = af["d"].dt.year()
print(af.select(year_expr.alias("year")).collect())
# Output:
# shape: (2, 1)
# ┌──────┐
# │ year │
# │ ---  │
# │ i32  │
# ╞══════╡
# │ 2020 │
# │ 2021 │
# └──────┘
""",
        "semantic_tags": ["datetime", "year", "example", "basic"],
        "example_context": {
            "inputs": ["date column"],
            "outputs": ["integer year"],
            "complexity": "basic"
        }
    }
]
```

**Impact on Search**:
- Navigational queries match directly on function signatures
- Examples can be retrieved independently for "show me how" queries
- Descriptions provide semantic matching for conceptual queries

#### Strategy 2: Contextual Window Chunking

Include surrounding context to preserve relationships:

```python
# Sliding window approach with overlap
def create_contextual_chunks(docstring, window_size=3, overlap=1):
    sections = docstring.split_into_sections()  # [description, params, examples, etc.]
    chunks = []
    
    for i in range(0, len(sections), window_size - overlap):
        window = sections[i:i + window_size]
        chunk = {
            "content": "\n\n".join(window),
            "primary_section": sections[i].type,
            "context_sections": [s.type for s in window[1:]],
            "overlap_previous": i > 0,
            "overlap_next": i + window_size < len(sections)
        }
        chunks.append(chunk)
    
    return chunks
```

**Example Output**:
```
Chunk 1: [Description + Parameters + First Example]
Chunk 2: [Parameters + First Example + Second Example]  # Overlap
Chunk 3: [Second Example + Returns + See Also]
```

**Impact on Search**:
- Better for queries that need multi-aspect understanding
- Reduces "snippet blindness" where isolated chunks lack context
- Higher storage cost but better coherence

#### Strategy 3: Query-Optimized Multi-Resolution Chunking

Create multiple representations of the same content optimized for different query types:

```python
# Multi-resolution chunking
resolutions = {
    "nano": {  # 1-2 sentences
        "use_case": "Autocomplete, quick reference",
        "example": "yearfrac(start, end) - Calculate year fraction between dates"
    },
    "micro": {  # Function signature + one-liner
        "use_case": "Navigation, discovery",
        "example": "af['date'].excel.yearfrac(end_date, basis=0) -> Calculate the year fraction between two dates using Excel conventions"
    },
    "mini": {  # Description + signature + key params
        "use_case": "Understanding usage",
        "example": "[Full description paragraph + parameter list]"
    },
    "standard": {  # Complete docstring section
        "use_case": "Learning, implementation",
        "example": "[Full examples with outputs]"
    },
    "macro": {  # Full docstring + related functions
        "use_case": "Comprehensive understanding",
        "example": "[Everything + links to related date functions]"
    }
}
```

**Query Routing**:
```python
def route_query_to_resolution(query: str, query_type: str) -> str:
    if query_type == "autocomplete":
        return "nano"
    elif "how do I" in query.lower():
        return "standard"
    elif "example" in query.lower():
        return "mini" if len(query) < 50 else "standard"
    elif "everything about" in query.lower():
        return "macro"
    else:
        return "micro"  # default
```

#### Strategy 4: Hybrid Semantic-Structural Chunking

Combine semantic understanding with structural parsing:

```python
class HybridChunker:
    def chunk_docstring(self, docstring: GaspatchioDocstring) -> List[Chunk]:
        chunks = []
        
        # 1. Structural chunks (preserve docstring structure)
        chunks.extend(self._create_structural_chunks(docstring))
        
        # 2. Semantic chunks (based on meaning)
        chunks.extend(self._create_semantic_chunks(docstring))
        
        # 3. Cross-reference chunks (relationships)
        chunks.extend(self._create_reference_chunks(docstring))
        
        # 4. Excel function example chunks
        chunks.extend(self._create_excel_chunks(docstring))
        
        return chunks
    
    def _create_semantic_chunks(self, docstring):
        # Extract semantic concepts
        concepts = self._extract_concepts(docstring.content)
        
        for concept in concepts:
            # Create focused chunks around each concept
            chunk = {
                "type": "semantic_concept",
                "concept": concept.name,
                "content": concept.explanation,
                "related_code": concept.find_related_examples(),
                "search_boost": concept.importance  # For ranking
            }
```

### Chunking Strategy Comparison Matrix

| Strategy | Best For | Query Types | Storage | Complexity | Retrieval Precision |
|----------|----------|-------------|---------|------------|-------------------|
| Semantic Function | Precise lookups | Navigational | Low | Low | High for specific queries |
| Contextual Window | Learning | Conceptual | Medium | Medium | Good balance |
| Multi-Resolution | All query types | All | High | High | Excellent with routing |
| Hybrid | Complex domains | All | High | Very High | Best with tuning |

### Implementation Recommendations

#### For Gaspatchio's Use Case:

1. **Start with Semantic Function Chunking** for MVP
   - Easier to implement
   - Clear mental model
   - Good enough for 70% of queries

2. **Add Multi-Resolution in Phase 2**
   - Nano chunks for autocomplete
   - Standard chunks for examples
   - Keeps both simple and power users happy

3. **Implement Query-Aware Chunking**
   ```python
   class QueryAwareChunker:
       def __init__(self):
           self.query_patterns = {
               "excel_example": r"(?i)(excel|vlookup|yearfrac|formula)",
               "date_operations": r"(?i)(date|time|year|month|day)",
               "assumption_tables": r"(?i)(assumption|mortality|cso|table)"
           }
       
       def chunk_with_query_hints(self, content, expected_queries):
           # Adjust chunk boundaries based on expected query patterns
           # Boost certain sections if they match expected patterns
   ```

#### Chunking Pipeline Architecture

```python
# Proposed pipeline
class GaspatchioChunkingPipeline:
    def __init__(self):
        self.stages = [
            ParseStage(),          # Parse docstrings using 10-docstring parser
            ValidateStage(),       # Ensure quality
            ChunkStage(),          # Apply chunking strategy
            EnrichStage(),         # Add metadata, tags, links
            EmbedStage(),          # Generate embeddings
            IndexStage()           # Store in vector DB
        ]
    
    def process(self, source_files: List[Path]) -> ChunkingResult:
        documents = self.parse_stage.parse(source_files)
        
        for stage in self.stages[1:]:
            documents = stage.process(documents)
            
        return ChunkingResult(
            chunks=documents,
            stats=self._calculate_stats(documents),
            coverage=self._analyze_coverage(documents)
        )
```

### Special Considerations for Excel function examples

Excel function examples require special chunking because they're inherently relational:

```python
# Excel-aware chunking
class ExcelExampleChunker:
    def chunk_excel_example(self, mapping):
        return [
            {
                "type": "excel_formula",
                "excel_syntax": mapping.excel_formula,
                "gaspatchio_syntax": mapping.gaspatchio_code,
                "searchable_text": f"{mapping.excel_formula} {mapping.description}",
                "category": mapping.category,  # date, lookup, financial
                "complexity": mapping.complexity,
                "prerequisites": mapping.required_imports,
                # Link to examples that use this pattern
                "example_links": mapping.find_usage_examples(),
                # Common variations
                "variations": mapping.get_variations()
            }
        ]

# Example mapping chunk:
{
    "excel_syntax": "YEARFRAC(start_date, end_date, basis)",
    "gaspatchio_syntax": "af['fraction'] = af['start'].excel.yearfrac(af['end'], basis)",
    "searchable_text": "YEARFRAC year fraction between dates date calculation",
    "category": "date_calculation",
    "complexity": "basic",
    "prerequisites": ["import gaspatchio_core as gs"],
    "example_links": ["dt-yearfrac-example-1", "mortgage-calculation-example"],
    "variations": [
        {
            "name": "with literal date",
            "gaspatchio": "af['frac'] = af['start'].excel.yearfrac('2024-12-31', 0)"
        }
    ]
}
```

### Chunk Quality Metrics

To ensure chunking effectiveness:

```python
class ChunkQualityAnalyzer:
    def analyze(self, chunks: List[Chunk]) -> QualityReport:
        return {
            "coverage": self._calculate_api_coverage(chunks),
            "redundancy": self._measure_content_overlap(chunks),
            "coherence": self._test_chunk_standalone_quality(chunks),
            "retrievability": self._simulate_retrieval_scenarios(chunks),
            "size_distribution": self._analyze_chunk_sizes(chunks),
            "example_coverage": self._count_examples_per_function(chunks)
        }
    
    def _test_chunk_standalone_quality(self, chunks):
        # Can a chunk be understood without additional context?
        # Critical for good RAG performance
        pass
```

### Dynamic Chunking Based on Usage

Consider implementing adaptive chunking based on actual usage patterns:

```python
class AdaptiveChunker:
    def __init__(self, usage_analytics):
        self.analytics = usage_analytics
        
    def rechunk_based_on_usage(self, original_chunks):
        # Analyze which chunks are retrieved together
        co_retrieval = self.analytics.get_co_retrieval_patterns()
        
        # Merge frequently co-retrieved chunks
        # Split chunks that are too broad for common queries
        # Adjust chunk boundaries based on user feedback
        
        return optimized_chunks
```

This deep dive into chunking strategies shows how different approaches serve different query patterns and use cases. The key is to start simple with semantic function chunking and evolve based on actual usage patterns and user feedback.

### 2. Vector Database Schema

#### Supabase Schema Design
```sql
-- Core chunks table
CREATE TABLE gaspatchio_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_type TEXT NOT NULL, -- 'docstring', 'example', 'excel_recipe'
    content TEXT NOT NULL,
    embedding vector(1536), -- for OpenAI ada-002
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version TEXT NOT NULL
);

-- Metadata structure:
{
    "object_path": "gaspatchio_core.column.dt.year",
    "file_path": "column/namespaces/dt_proxy.py",
    "chunk_index": 0,
    "parent_id": "uuid-of-parent-chunk",
    "tags": ["datetime", "extraction", "year"],
    "example_index": 2,  -- for example chunks
    "excel_formula": "YEAR()",  -- for excel recipe chunks
    "complexity": "basic|intermediate|advanced"
}

-- Full-text search table for BM25
CREATE TABLE gaspatchio_search (
    id UUID REFERENCES gaspatchio_chunks(id),
    searchable_text TEXT,
    title TEXT,
    ts_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', searchable_text)) STORED
);

CREATE INDEX idx_search_vector ON gaspatchio_search USING GIN (ts_vector);
```

### 3. Search Strategy

#### Hybrid Search Approach
1. **Initial BM25 Search**: Fast keyword matching for function names, parameters
2. **Vector Similarity**: Semantic search for "how do I..." queries
3. **Re-ranking**: Combine scores with configurable weights

```python
# Search Pipeline
def search(query: str, search_type: str = "hybrid"):
    # 1. BM25 for exact matches
    bm25_results = bm25_search(query, limit=20)
    
    # 2. Vector search for semantic similarity
    vector_results = vector_search(query, limit=20)
    
    # 3. Combine and re-rank
    if search_type == "hybrid":
        return rerank_results(bm25_results, vector_results, 
                            bm25_weight=0.3, vector_weight=0.7)
```

### 4. MCP Server Design

#### FastMCP Implementation
```python
# Core MCP Tools
@server.tool()
async def search_gaspatchio_docs(
    query: str,
    doc_type: Literal["all", "functions", "examples", "excel_examples"] = "all",
    complexity: Optional[Literal["basic", "intermediate", "advanced"]] = None,
    limit: int = 5
) -> SearchResults:
    """Search Gaspatchio documentation and examples"""
    
@server.tool()
async def get_excel_function_example(
    excel_formula: str,
    context: Optional[str] = None
) -> ExcelFunctionExample:
    """Convert Excel function to Gaspatchio code"""
    
@server.tool()
async def suggest_next_steps(
    current_code: str,
    objective: str
) -> List[Suggestion]:
    """Suggest next Gaspatchio operations based on current code"""
```

## Key Considerations & Decisions

### 1. Content Versioning Strategy
**Decision Needed**: How to handle multiple versions of Gaspatchio?

**Options**:
- A) Single version (latest) - simpler but less flexible
- B) Multi-version with version selector - complex but future-proof
- C) Version tags in metadata with smart routing

**Recommendation**: Start with A, design for C

### 2. Update & Synchronization
**Decision Needed**: How to keep RAG pipeline in sync with codebase?

**Options**:
- A) Manual triggers via GitHub Actions
- B) Automated on merge to main
- C) Scheduled daily updates
- D) Real-time via webhooks

**Recommendation**: B for production, A for development

### 3. Quality Assurance & Metrics
**Not mentioned but critical**:

- **Retrieval Quality Metrics**:
  - Precision@K for different query types
  - User feedback integration
  - A/B testing framework for search weights

- **Content Coverage Analysis**:
  - Which functions lack examples?
  - Which Excel functions aren't covered?
  - Usage analytics to identify gaps

### 4. User Proficiency Adaptation
**Not mentioned but important**:

Should the system adapt to user skill level?
- Track query complexity over time
- Adjust example complexity accordingly
- Provide learning paths

### 5. Performance Considerations

#### Caching Strategy
```python
# Three-tier caching
1. Edge cache (MCP client) - 5 min TTL for identical queries
2. Redis cache (FastMCP) - 1 hour TTL for processed results  
3. Database query cache - 24 hour TTL for embeddings
```

#### Response Time Targets
- Search latency: < 200ms p95
- Full example retrieval: < 500ms p95
- Excel function lookup: < 1s p95

### 6. Excel function example management
**Decision Needed**: How to source and maintain Excel-function example pairs?

**Options**:
- A) Manually curated YAML/JSON files
- B) Extract from existing model code via comments
- C) Community-contributed with review process
- D) LLM-generated with human validation

**Recommendation**: Start with A, evolve to C

Example structure:
```yaml
excel_examples:
  - excel: "YEARFRAC(start_date, end_date, basis)"
    gaspatchio: |
      af["year_frac"] = af["start_date"].excel.yearfrac(af["end_date"], basis=0)
    context: "date calculations"
    complexity: "basic"
    notes: "Basis parameter maps directly"
```

### 7. Security & Access Control
**Not mentioned but necessary**:

- API key management for MCP server
- Rate limiting per user/organization
- Audit logging for compliance
- PII detection in queries

### 8. Integration Points

#### Development Workflow Integration
- VS Code extension using MCP client
- Jupyter notebook magic commands
- CLI tool for quick lookups
- CI/CD integration for code review

#### Feedback Loop
```python
# Capture usage data
@server.tool()
async def record_feedback(
    query: str,
    result_id: str,
    helpful: bool,
    comment: Optional[str] = None
):
    """Record user feedback on search results"""
```

## Implementation Phases

### Phase 1: MVP (4-6 weeks)
1. Basic docstring parsing and chunking
2. Supabase setup with vector storage
3. Simple BM25 + vector search
4. Basic FastMCP server with search tool
5. 10-20 manually curated Excel function examples

### Phase 2: Enhancement (4-6 weeks)
1. Hybrid search with re-ranking
2. Example-specific chunking
3. Excel function lookup tool
4. Basic caching layer
5. Usage analytics

### Phase 3: Intelligence (6-8 weeks)
1. Contextual suggestions
2. Learning path generation
3. Community contribution system
4. Advanced Excel function pattern matching
5. Performance optimization

## Success Metrics

1. **Adoption**: % of Gaspatchio users utilizing MCP extension
2. **Efficiency**: Time reduction in writing Gaspatchio code
3. **Quality**: Reduction in code review iterations
4. **Coverage**: % of Gaspatchio API with examples
5. **Satisfaction**: User feedback scores

## Open Questions for Discussion

1. **Embedding Model Choice**: OpenAI ada-002 vs open source alternatives?
2. **Multi-language Support**: Should examples support languages beyond English?
3. **Offline Capability**: Should we support local vector DB for air-gapped environments?
4. **LLM Integration**: Should the MCP server include LLM-powered code generation, or stay retrieval-only?
5. **Licensing**: How to handle community-contributed Excel function examples?

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|-------------------|
| Stale documentation | Automated testing of examples in CI |
| Poor search relevance | A/B testing framework, user feedback |
| Performance degradation | Horizontal scaling, caching, monitoring |
| Incomplete Excel function examples | Community contributions, LLM assistance |
| Version mismatch | Clear version indicators, compatibility matrix |

## Next Steps

1. Review and approve overall architecture
2. Finalize technology choices (embedding model, caching layer)
3. Create detailed technical specification
4. Set up development environment
5. Begin Phase 1 implementation

---

*This document serves as a living ADR and will be updated as decisions are made and implementation progresses.*
