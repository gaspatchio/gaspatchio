Below is a **“hand-off spec”** an engineer can follow to stand up the entire hybrid-search RAG stack on **Neon + `pg_search` + `pgvector`**, expose it through a **FastMCP** endpoint, and orchestrate query-class routing with **pydantic.ai**.

---

## 0. Architecture at a Glance (why these pieces)

```
┌─── client prompt ───┐
│   (IDE / CLI)       │
└────────┬────────────┘
    FastMCP endpoint     ←──   ① classify prompt (pydantic.ai)
        │                           ↓
        │                    {class, α, dsl}
        │                           ↓
        │            ② hybrid SQL (pg_search + pgvector)
        │                           ↓
        │      top-K docstring chunks + scores
        │                           ↓
        │   ③ answer synthesis LLM (pydantic.ai)
        ↓
┌───────────────────────────────────────────────────┐
│ Neon Postgres (AWS region)                        │
│   • pg_search – BM25 inverted index               │
│   • pgvector  – dense vector                     │
│   • gas_docstrings table (one row per object)     │
└───────────────────────────────────────────────────┘
```

*Rationale*

* **Neon** — serverless Postgres; turnkey support for `pg_search` in AWS regions as of Mar 2025 ([neon.com][1]).
* **`pg_search`** — Elasticsearch-grade BM25, typo-tolerant, JSON boosts, keeps us in SQL.
* **`pgvector`** — dense semantic similarity.
* **pydantic.ai router** — LLM returns structured JSON in a single call; avoids hand-rolled regex.
* **FastMCP** — “LLM agent hub” you already use; keeps retrieval and synthesis in one microservice.

---

## 1. Spin up Neon with `pg_search`

1. **Create project** at [https://console.neon.tech](https://console.neon.tech).

   * Choose an **AWS** region (e.g. `us-east-1`) – `pg_search` isn’t yet in Azure regions ([neon.com][1]).
   * Postgres version ≥ 15.

2. **Enable extensions** in the SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS pg_search;
CREATE EXTENSION IF NOT EXISTS pgvector;
```

3. **Grab the connection string** (`postgresql://user:pass@ep…db.neon.tech/dbname`) and store as `PG_DSN` in 1Password / Doppler.

---

## 2. Schema & indices

```sql
DROP TABLE IF EXISTS gas_docstrings;
DROP INDEX IF EXISTS gas_docstrings_bm25;
DROP INDEX IF EXISTS gas_docstrings_vec;

-- gas_docstrings: one row per fully-qualified symbol
CREATE TABLE gas_docstrings (
  id           BIGSERIAL PRIMARY KEY,
  object_path  TEXT UNIQUE,                     -- e.g. gaspatchio.frame.ActuarialFrame.yearfrac
  short_desc   TEXT,
  long_desc    TEXT,
  parameters   JSONB,
  returns      TEXT,
  examples     JSONB,                           -- [{"snippet": "...", "exp": "..."}]
  embedding    VECTOR(1536)                     -- dim depends on embed model
);

-- BM25 covering index across multiple fields
CREATE INDEX gas_docstrings_bm25
  ON gas_docstrings
  USING bm25 (object_path, short_desc, long_desc, examples)
  WITH (key_field='id');

-- ANN vector index
CREATE INDEX gas_docstrings_vec
  ON gas_docstrings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

*Why one row?* – Single embedding to keep cost down; `pg_search` covering index already preserves per-field term positions, so we can do field boosts in the DSL.

---

## 3. `KnowledgeBase` Python package (async)

### 3.1 Directory scaffold

```
kb/
├─ __init__.py
├─ models.py              # pydantic GaspatchioDocstring
├─ ingestion.py           # upsert_docs()
├─ retrieval.py           # hybrid_search()
└─ db.py                  # get_conn() helper
```

Add to your monorepo’s `pyproject.toml`:

```toml
[tool.poetry.dependencies]
psycopg = {extras = ["binary", "vector"], version = "^3.2"}
openai  = "^1.23"
python-dotenv = "^1.0"
tqdm = "^4.66"
pydantic = "^2.7"
```


### 3.3 `db.py`

```python
import os
from psycopg_async import AsyncConnectionPool    # thin wrapper around psycopg

pool = AsyncConnectionPool(os.getenv("PG_DSN"), min_size=1, max_size=5)

async def get_conn():
    return await pool.getconn()
```

### 3.4 `ingestion.py`

```python
import json, asyncio, os
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm
from .models import GaspatchioDocstring
from .db import get_conn

EMBED_MODEL = "text-embedding-3-small"
client = AsyncOpenAI()

INSERT_SQL = """
INSERT INTO gas_docstrings
  (object_path, short_desc, long_desc, parameters, returns, examples, embedding)
VALUES (%(path)s, %(short)s, %(long)s, %(params)s, %(ret)s, %(examples)s, %(emb)s)
ON CONFLICT (object_path) DO UPDATE
  SET short_desc = EXCLUDED.short_desc,
      long_desc  = EXCLUDED.long_desc,
      parameters = EXCLUDED.parameters,
      returns    = EXCLUDED.returns,
      examples   = EXCLUDED.examples,
      embedding  = EXCLUDED.embedding;
"""

async def upsert_docs(docs: list[GaspatchioDocstring]):
    async with (await get_conn()) as conn:
        await conn.execute("BEGIN")
        for d in tqdm(docs):
            text = "\n\n".join(filter(None, [
                d.short_description,
                d.long_description,
                *(ex.snippet for ex in d.examples)
            ]))
            emb = (await client.embeddings.create(
                    model=EMBED_MODEL, input=text)).data[0].embedding
            await conn.execute(INSERT_SQL, {
                "path": d.object_path,
                "short": d.short_description,
                "long": d.long_description,
                "params": json.dumps(d.parameters),
                "ret": d.returns,
                "examples": json.dumps([e.model_dump() for e in d.examples]),
                "emb": emb
            })
        await conn.execute("COMMIT")
```

### 3.5 `retrieval.py` – hybrid SQL

```python
HYBRID_SQL = """
WITH
bm25 AS (
  SELECT id, paradedb.score(id) AS bscore
  FROM   gas_docstrings
  WHERE  (object_path, short_desc, long_desc, examples) @@@ %(dsl)s
  ORDER  BY bscore DESC
  LIMIT  200
),
vec AS (
  SELECT id,
         1 - (embedding <-> %(emb)s) AS vscore
  FROM   gas_docstrings
  ORDER  BY embedding <-> %(emb)s
  LIMIT  200
)
SELECT d.object_path,
       d.short_desc,
       d.long_desc,
       d.examples,
       COALESCE(bscore,0) AS bm25,
       COALESCE(vscore,0) AS v,
       (%(alpha)s * COALESCE(vscore,0) + (1-%(alpha)s) * COALESCE(bscore,0)) AS hybrid
FROM   gas_docstrings d
LEFT   JOIN bm25 USING (id)
LEFT   JOIN vec  USING (id)
ORDER  BY hybrid DESC
LIMIT  %(k)s;
"""

async def hybrid_search(prompt: str, dsl: str, alpha: float, k: int = 8):
    # embed prompt
    emb = (await client.embeddings.create(
        model=EMBED_MODEL, input=prompt)).data[0].embedding
    async with (await get_conn()) as conn:
        rows = await conn.fetch(HYBRID_SQL, dict(
            dsl=dsl, emb=emb, alpha=alpha, k=k))
    return rows
```

---

## 4. Prompt-class router in **pydantic.ai**

```python
from pydantic_ai import CompletionModel

class QueryClass(BaseModel):
    class_: str  # navigational | conceptual | code | learning
    alpha: float
    dsl: str     # pg_search DSL (with boosts)

router = CompletionModel(
    system="""
You are a query classifier. Map the user prompt into one of
[navigational, conceptual, code, learning].
Return JSON with keys: class_, alpha, dsl.

α values:
- navigational 0.25
- conceptual 0.40
- code        0.60
- learning    0.35

DSL examples:
- navigational: object_path:{term}^3 OR short_desc:{term}
- code: examples:{term}^2 OR parameters:{term}
""",
    model="gpt-4o",
    schema=QueryClass
)
```

Usage:

```python
qc = router.complete({"user": prompt})
rows = await hybrid_search(prompt, qc.dsl, qc.alpha)
```

---

## 5. FastMCP integration

### 5.1 `services/knowledge_mcp.py`

```python
from fastmcp import MCP, Tool, context

kb_router = Tool(
    name="kb_search",
    description="Hybrid search over Gaspatchio knowledge base",
    func=hybrid_search
)

mcp = MCP(tools=[kb_router])

@mcp.default_handler
async def handle(prompt: str):
    qc = router.complete({"user": prompt})
    docs = await kb_router(prompt, qc.dsl, qc.alpha)
    context.attach("retrieved_docs", docs)
    answer = CompletionModel(
        system="""
You are Gaspatchio expert. Answer using ONLY info in {{retrieved_docs}}.
""",
        model="gpt-4o"
    ).complete({"user": prompt})
    return answer
```

Run locally:

```bash
uvicorn services.knowledge_mcp:mcp --port 8000
```

### 5.2 Deploy

* **Neon** – nothing to deploy: serverless.
* **FastMCP** – container → Fly.io:

```Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
ENV PG_DSN=${PG_DSN} OPENAI_API_KEY=${OPENAI_API_KEY}
CMD ["uvicorn", "services.knowledge_mcp:mcp", "--host", "0.0.0.0", "--port", "8080"]
```

```
fly launch --name gaspatchio-kb --region syd
fly deploy
```

---

## 6. CI / tests

* **`pytest tests/test_ingest.py`** – ingest a fixture JSON, assert row count.
* **`pytest tests/test_search.py`** – query “yearfrac”, assert top result path matches.
* **GitHub Actions** – run unit tests, fail on coverage < 90 %.

---

## 7. Observability & tuning

| Metric         | How to collect                             | Budget                            |
| -------------- | ------------------------------------------ | --------------------------------- |
| Query latency  | `pg_stat_statements`, p99 target < 150 ms  | Neon Pro gives 1 s compute resume |
| Recall @ 5     | nightly `kb.eval` script (LLM grade)       | ≥ 0.85                            |
| Embedding cost | cache embeddings locally; OpenAI batch API | <\$20/mo                          |

Tune:

* `ivfflat lists` 100 → 200 if recall dips.
* `LIMIT 200` early-fusion → 400 for longer prompts.
* Re-balance field boosts in DSL.

---

### Hand-off checklist

1. **Create Neon DB (AWS)** + enable extensions.
2. **Run schema SQL** (Section 2).
3. **Ingest**: `python -m kb.ingestion data/*.json`.
4. **Export PG\_DSN / OPENAI\_API\_KEY**.
5. **Start FastMCP locally** → `curl :8000 -d 'How do I use yearfrac?'`.
6. **Fly deploy**.

Everything above is sufficient for an engineer to implement, test and ship the Gaspatchio hybrid RAG search in production. Feel free to ping if deeper configurables come up! ([neon.com][1], [neon.tech][2], [neon.tech][3], [paradedb.com][4])

[1]: https://neon.com/docs/extensions/pg_search?utm_source=chatgpt.com "The pg_search extension - Neon Docs"
[2]: https://neon.tech/blog/pgsearch-on-neon?utm_source=chatgpt.com "pg_search is Available on Neon"
[3]: https://neon.tech/guides/pg-search?utm_source=chatgpt.com "Building an End-to-End Full-Text Search Experience With ... - Neon"
[4]: https://www.paradedb.com/blog/introducing_search?utm_source=chatgpt.com "pg_search: Elastic-Quality Full Text Search Inside Postgres"
