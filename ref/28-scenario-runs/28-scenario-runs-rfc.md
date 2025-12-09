# RFC 28: ScenarioRun - Unified Local and Cloud Execution

**Status**: Draft
**Date**: 2025-12-08
**Author**: Claude & Gaz Wright

## Summary

Formalize the sink-then-stream pattern into a `ScenarioRun` class that manages batched model execution, result persistence, and flexible post-hoc aggregation - with support for both local execution and Azure cloud execution via containers.

## Motivation

### The Problem

Running large stochastic scenarios (e.g., 10K policies x 10K scenarios = 100M rows) requires:

1. **Memory management** - Can't hold all results in memory
2. **Flexible analysis** - Don't want to lock in aggregation upfront
3. **Reproducibility** - Track what was run, when, with what parameters
4. **Recovery** - Resume from failures, don't lose partial results
5. **Scale** - Run locally for dev, burst to cloud for production valuations

### Current State

Users must manually implement the sink-then-stream pattern:

```python
# Manual implementation today
from gaspatchio_core.scenarios import batch_scenarios

output_dir = Path("results/")
for batch_num, batch_ids in enumerate(batch_scenarios(scenario_ids, batch_size=10)):
    af = ActuarialFrame(model_points)
    af = with_scenarios(af, batch_ids)
    result = run_model(af).collect()
    result.write_parquet(output_dir / f"batch_{batch_num:04d}.parquet")
    del result

# Later aggregation
totals = pl.scan_parquet(output_dir / "*.parquet").group_by("scenario_id").agg(...)
```

This works but is:
- Boilerplate-heavy
- Error-prone (forget to delete intermediate, wrong glob pattern)
- No metadata tracking
- No progress reporting
- No recovery from partial failures
- **No path to cloud execution**

### Benchmarks Supporting This Pattern

| Scale | Rows | Unbatched Memory | Sink-then-Stream Memory | Time Overhead |
|-------|------|------------------|-------------------------|---------------|
| 1k x 100 | 100k | 5.6 GiB | 1.2 GiB | ~5% |
| 10k x 100 | 1M | ~57 GiB (est.) | 5.9 GiB | ~5% |

The sink-then-stream pattern provides **~10x memory reduction** with **negligible time overhead**.

---

## Design Principles

### Inspired by Polars Cloud

We borrow key concepts from [Polars Cloud](https://docs.pola.rs/polars-cloud/quickstart/):

| Polars Cloud Concept | Our Equivalent |
|----------------------|----------------|
| `ComputeContext` | `ComputeContext` - specifies where/how to execute |
| `.remote(ctx)` | `run.execute(context=ctx)` - same run, different backend |
| `.sink_parquet()` | Sink to local filesystem OR Azure Blob |
| `.await_and_scan()` | `run.scan()` - returns LazyFrame pointing to results |
| `.show()` | `run.preview()` - quick peek at results |

### Key Principle: Same API, Different Backend

```python
# Define the run ONCE
run = ScenarioRun(
    model_points="model_points.parquet",
    scenario_ids=list(range(1, 10001)),
    model_func=run_model,
)

# Execute locally
run.execute(context=ComputeContext.local())

# OR execute on Azure (same API!)
run.execute(context=ComputeContext.azure(vm_size="Standard_NV12ads_A10_v5"))

# Query results (works the same - local files or blob storage)
totals = run.aggregate(group_by="scenario_id", agg=pl.col("pv_net_cf").sum())
```

---

## Proposed API

### ComputeContext

```python
from gaspatchio_core.scenarios import ComputeContext

# Local execution (default)
local_ctx = ComputeContext.local(
    output_dir="results/run_001/",  # Local filesystem
    threads=8,  # Optional thread limit
)

# Azure execution
azure_ctx = ComputeContext.azure(
    vm_size="Standard_NV12ads_A10_v5",  # Azure VM SKU
    region="australiaeast",
    storage_account="myresults",  # Azure Blob Storage
    container="scenario-runs",  # Blob container
    use_gpu=True,  # Enable GPU for aggregation

    # Container configuration
    image="myregistry.azurecr.io/gspio:latest",  # Pre-built image
    # OR
    dockerfile="./Dockerfile",  # Build on demand

    # Resource limits
    memory_gb=56,
    timeout_hours=4,
)
```

### ScenarioRun

```python
from gaspatchio_core.scenarios import ScenarioRun, ComputeContext

# Create a run
run = ScenarioRun(
    name="Q4 Stress Test",  # Descriptive name
    model_points="model_points.parquet",  # Path, DataFrame, or LazyFrame
    scenario_ids=list(range(1, 10001)),
    model_func=run_model,  # The model function to execute
    batch_size=10,  # Scenarios per batch
)

# Execute (local by default)
run.execute()

# OR execute with explicit context
run.execute(context=ComputeContext.azure(...))

# Check status
print(run.status)  # "pending", "running", "completed", "failed", "partial"
print(run.progress)  # {"completed": 45, "total": 100, "elapsed": "12:34"}

# Aggregate results (streaming from local or blob)
totals = run.aggregate(
    group_by="scenario_id",
    agg=pl.col("pv_net_cf").sum().alias("total_pv"),
)

# Multiple aggregations without re-running
means = run.aggregate(group_by="scenario_id", agg=pl.col("pv_net_cf").mean())
quantiles = run.aggregate(agg=pl.col("pv_net_cf").quantile(0.99))

# Raw LazyFrame for custom queries
lf = run.scan()
custom = lf.filter(pl.col("scenario_id") < 100).collect(engine="streaming")

# Preview without downloading everything
run.preview(n=10)  # Show first 10 rows
```

### Loading Existing Runs

```python
# Load from local filesystem
run = ScenarioRun.load("results/run_2025_12_08/")

# Load from Azure Blob
run = ScenarioRun.load("az://myresults/scenario-runs/run_2025_12_08/")

# List available runs
runs = ScenarioRun.list_runs("az://myresults/scenario-runs/")
```

---

## Execution Backends

### Local Executor

```
┌─────────────────────────────────────────────────────────────┐
│  Local Execution                                            │
├─────────────────────────────────────────────────────────────┤
│  1. Load model_points from local path                       │
│  2. For each batch:                                         │
│     - Expand with scenarios                                 │
│     - Run model_func                                        │
│     - Sink to local parquet: results/batches/batch_NNNN.parquet │
│  3. Write metadata to results/run_metadata.json             │
│  4. Aggregation: scan local parquet, stream-aggregate       │
└─────────────────────────────────────────────────────────────┘
```

**Output structure:**
```
results/run_2025_12_08/
├── run_metadata.json
├── batches/
│   ├── batch_0000.parquet
│   ├── batch_0001.parquet
│   └── ...
└── aggregates/  # Optional cached aggregations
    └── totals_by_scenario.parquet
```

### Azure Executor

```
┌─────────────────────────────────────────────────────────────┐
│  Azure Execution                                            │
├─────────────────────────────────────────────────────────────┤
│  1. Serialize run definition to JSON                        │
│  2. Upload model_points to Blob Storage (if not already)    │
│  3. Provision VM via Terraform/ARM/API:                     │
│     - VM size from ComputeContext                           │
│     - Install Docker + NVIDIA runtime (if GPU)              │
│     - Pull container image from ACR                         │
│  4. VM executes container:                                  │
│     - Download model_points from Blob                       │
│     - Run batches, sink to Blob Storage                     │
│     - Upload metadata                                       │
│  5. VM shuts down                                           │
│  6. Aggregation: scan Blob parquet, stream-aggregate        │
└─────────────────────────────────────────────────────────────┘
```

**Blob structure:**
```
az://myresults/scenario-runs/run_2025_12_08/
├── run_metadata.json
├── batches/
│   ├── batch_0000.parquet
│   └── ...
└── aggregates/
    └── totals_by_scenario.parquet
```

---

## Azure Infrastructure

Based on the [Azure Benchmark Proposal](./28-gaspatchio_azure_benchmark_proposal.md):

### Container Images

Two Docker images, pushed to Azure Container Registry (ACR):

**CPU Image (`gspio:cpu`):**
```dockerfile
FROM python:3.12-slim
RUN pip install gaspatchio-core polars
COPY model_code/ /app/
ENTRYPOINT ["python", "-m", "gaspatchio_core.scenarios.runner"]
```

**GPU Image (`gspio:gpu`):**
```dockerfile
FROM nvcr.io/nvidia/cuda:12.4-devel-ubuntu22.04
RUN pip install gaspatchio-core 'polars[gpu]'
COPY model_code/ /app/
ENTRYPOINT ["python", "-m", "gaspatchio_core.scenarios.runner"]
```

### VM Provisioning

```python
# Internal: Azure executor provisions VM
vm_config = {
    "vm_size": ctx.vm_size,  # e.g., "Standard_NV12ads_A10_v5"
    "image": "Ubuntu 22.04",
    "cloud_init": """
        apt-get update && apt-get install -y docker.io
        # If GPU: install nvidia-container-toolkit
        az acr login -n myregistry
        docker pull myregistry.azurecr.io/gspio:gpu
    """,
    "managed_identity": True,  # For ACR + Blob access
}
```

### Authentication

- **Managed Identity** for VM -> ACR and Blob access
- **Service Principal** for local client -> Azure API
- **SAS tokens** for time-limited Blob access (alternative)

---

## GPU Considerations

### When GPU Helps

Based on research into Polars GPU acceleration:

| Operation | GPU Accelerated? |
|-----------|------------------|
| group_by + sum | ✅ Yes |
| group_by + mean | ✅ Yes |
| group_by + std | ⚠️ Likely |
| group_by + quantile | ❌ No (falls back to CPU) |
| Parquet reads | ✅ Yes (but I/O bound) |

**Key insight**: Model execution uses custom UDFs (falls back to CPU), but aggregation phase can benefit from GPU for sum/mean operations.

### API for GPU Aggregation

```python
# Aggregation with GPU (if available)
totals = run.aggregate(
    group_by="scenario_id",
    agg=pl.col("pv_net_cf").sum(),
    engine="gpu",  # Use GPU for this aggregation
)

# Falls back to CPU if:
# - No GPU available
# - Unsupported operation (quantile)
# - Query too small to benefit
```

---

## Metadata Schema

```json
{
    "schema_version": "1.0",
    "name": "Q4 Stress Test",
    "id": "run_2025_12_08_143000_abc123",

    "definition": {
        "model_points_path": "model_points.parquet",
        "model_points_hash": "sha256:...",
        "scenario_ids": [1, 2, 3, "...", 10000],
        "scenario_count": 10000,
        "batch_size": 10,
        "batch_count": 1000,
        "model_func": "my_model.run_projection",
        "model_kwargs": {"discount_rate": 0.03}
    },

    "execution": {
        "context": "azure",
        "vm_size": "Standard_NV12ads_A10_v5",
        "region": "australiaeast",
        "image": "myregistry.azurecr.io/gspio:gpu",
        "started": "2025-12-08T14:30:00Z",
        "completed": "2025-12-08T15:45:00Z",
        "duration_seconds": 4500,
        "status": "completed"
    },

    "batches": {
        "completed": [0, 1, 2, "...", 999],
        "failed": [],
        "pending": []
    },

    "metrics": {
        "total_rows": 10000000,
        "disk_usage_gb": 19.2,
        "peak_memory_gb": 5.9,
        "cost_usd": 12.50
    },

    "outputs": {
        "batches_path": "batches/",
        "aggregates_path": "aggregates/"
    }
}
```

---

## Implementation Plan

### Phase 1: Local Execution (MVP)
- [ ] `ScenarioRun` class with `execute()` and `aggregate()`
- [ ] `ComputeContext.local()` implementation
- [ ] Metadata persistence (JSON)
- [ ] Basic progress reporting (print/logging)
- [ ] `scan()` returning LazyFrame
- [ ] Resume from partial failures

### Phase 2: Azure Execution
- [ ] `ComputeContext.azure()` implementation
- [ ] Docker image build/push tooling
- [ ] VM provisioning (Terraform module or Azure SDK)
- [ ] Blob Storage integration for sink/scan
- [ ] `ScenarioRun.load()` from Blob URLs

### Phase 3: Production Hardening
- [ ] Rich progress bars (optional dependency)
- [ ] Aggregate caching
- [ ] Cost estimation before run
- [ ] GPU aggregation support
- [ ] Parallel local execution (multiprocessing)

### Phase 4: Advanced Features
- [ ] Run comparison tools
- [ ] Automatic VM sizing recommendations
- [ ] Spot instance support (cost savings)
- [ ] Multi-region execution

---

## Open Questions

### 1. Model Function Packaging

How does the model code get into the container?

```python
# Option A: Model is part of gaspatchio-core (unlikely for custom models)
run = ScenarioRun(model_func="gaspatchio_core.models.gmxb")

# Option B: User provides path to model file, we copy into container
run = ScenarioRun(model_func="./my_model.py:run_projection")

# Option C: User builds their own container with model baked in
ctx = ComputeContext.azure(image="myacr.azurecr.io/my-model:v1")

# Option D: Dynamic code serialization (pickle/cloudpickle)
run = ScenarioRun(model_func=run_projection)  # Function object serialized
```

### 2. Stochastic Returns Handling

The model needs scenario-specific returns. Options:

```python
# Option A: Returns table in Blob, model looks up by scenario_id
# (Current approach in tests - model handles internally)

# Option B: Returns generator provided to ScenarioRun
run = ScenarioRun(
    ...,
    returns_generator=generate_stochastic_returns,
)

# Option C: Returns pre-generated and stored alongside model_points
run = ScenarioRun(
    model_points="model_points.parquet",
    scenario_returns="scenario_returns.parquet",  # Explicit
)
```

### 3. Container vs Image Management

Should `ComputeContext` handle container building?

```python
# Option A: Pre-built images only (simpler)
ctx = ComputeContext.azure(image="myregistry.azurecr.io/gspio:gpu")

# Option B: Build on demand from Dockerfile
ctx = ComputeContext.azure(dockerfile="./Dockerfile.gpu")

# Option C: Build from requirements.txt + model path
ctx = ComputeContext.azure(
    requirements="requirements.txt",
    model_path="./my_model/",
)
```

### 4. Async Execution Model

For Azure runs that take hours:

```python
# Option A: Blocking (simple, but ties up client)
run.execute(context=azure_ctx)  # Blocks until complete

# Option B: Fire-and-forget with polling
run.submit(context=azure_ctx)  # Returns immediately
while run.status != "completed":
    time.sleep(60)
    run.refresh()  # Poll metadata from Blob

# Option C: Callback/webhook
run.submit(context=azure_ctx, on_complete="https://my-webhook.com/")
```

### 5. Cost Tracking

Should we estimate/track costs?

```python
# Before execution
estimate = run.estimate_cost(context=azure_ctx)
print(estimate)  # {"vm_hours": 2.5, "storage_gb": 20, "estimated_usd": 15.00}

# After execution
print(run.metadata["metrics"]["cost_usd"])  # Actual cost
```

### 6. Auto-Sizing VM Selection

Can we automatically recommend/select VM size based on the workload?

```python
# Option A: User always specifies (current design)
ctx = ComputeContext.azure(vm_size="Standard_NV12ads_A10_v5")

# Option B: Auto-select based on workload analysis
run = ScenarioRun(
    model_points="model_points.parquet",  # 10k rows
    scenario_ids=list(range(1, 10001)),   # 10k scenarios
    model_func=run_model,
)
ctx = ComputeContext.azure(auto_size=True)  # Analyzes and picks VM
run.execute(context=ctx)
print(ctx.selected_vm_size)  # "Standard_NV36ads_A10_v5"

# Option C: Recommend but let user override
recommendation = run.recommend_vm_size()
# Returns: {
#     "recommended": "Standard_NV36ads_A10_v5",
#     "reason": "10k x 10k = 100M rows, estimated 58 GiB memory, GPU beneficial for aggregation",
#     "alternatives": [
#         {"vm": "Standard_E32ds_v5", "reason": "CPU-only, cheaper, ~2x slower"},
#         {"vm": "Standard_NV12ads_A10_v5", "reason": "Smaller GPU, may OOM on aggregation"},
#     ]
# }
```

**Sizing factors to consider:**
- Model points row count
- Scenario count
- Batch size (memory per batch)
- Model complexity (columns produced, projection length)
- Aggregation requirements (GPU helps sum/mean, not quantile)
- Disk requirements (~20 KB/row for parquet output)

**Challenges:**
- Model complexity is hard to estimate without running it
- Could do a "probe run" with small sample to estimate memory/time
- Need pricing data for cost-optimal recommendations

### 7. Distributed Execution (Multi-VM)

For very large runs, partition across multiple VMs:

```python
# Option A: Single VM (current design)
# All batches run sequentially on one VM

# Option B: Horizontal scaling - partition by scenario
ctx = ComputeContext.azure(
    vm_size="Standard_NV12ads_A10_v5",
    num_workers=4,  # Spin up 4 VMs
    # Scenarios partitioned: VM1 gets 1-2500, VM2 gets 2501-5000, etc.
)

# Option C: Explicit partitioning
run = ScenarioRun(
    scenario_ids=list(range(1, 10001)),
    partition_by="scenario_id",  # Each VM gets a subset
    num_partitions=4,
)
```

**Architecture for distributed:**
```
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator (local or Azure Function)                     │
├─────────────────────────────────────────────────────────────┤
│  1. Partition scenario_ids into N chunks                    │
│  2. Spin up N VMs (or container instances)                  │
│  3. Each VM:                                                │
│     - Downloads model_points (same for all)                 │
│     - Runs its partition of scenarios                       │
│     - Sinks batches to shared Blob path:                    │
│       az://results/run_123/batches/worker_0/batch_0000.parquet │
│       az://results/run_123/batches/worker_1/batch_0000.parquet │
│  4. Orchestrator waits for all VMs to complete              │
│  5. Aggregation scans all worker outputs:                   │
│     pl.scan_parquet("az://results/run_123/batches/*/")      │
└─────────────────────────────────────────────────────────────┘
```

**Blob structure for distributed:**
```
az://myresults/scenario-runs/run_2025_12_08/
├── run_metadata.json
├── batches/
│   ├── worker_0/
│   │   ├── batch_0000.parquet
│   │   └── ...
│   ├── worker_1/
│   │   ├── batch_0000.parquet
│   │   └── ...
│   └── worker_N/
│       └── ...
└── aggregates/
    └── totals_by_scenario.parquet
```

**Considerations:**
- Model points must be accessible to all workers (Blob or copied to each)
- Scenario returns also need distribution strategy
- Failure handling: what if one worker fails? Resume? Retry?
- Cost vs time tradeoff: 4 VMs for 1 hour vs 1 VM for 4 hours (similar cost, faster wall-clock)
- Could use Azure Container Instances for lightweight workers (no VM management)
- Could use Azure Batch for managed job scheduling

---

## Alternatives Considered

### Polars Cloud Direct Integration

Use Polars Cloud directly instead of building our own.

**Rejected because:**
- Polars Cloud is AWS-only (we need Azure)
- Doesn't handle model execution, only Polars queries
- Less control over container/infrastructure

### Dask/Ray Integration

Use Dask or Ray for distributed execution.

**Not rejected, but deferred:**
- Adds complexity
- May be good for Phase 4 (multi-node execution)
- Single-VM with batching covers most use cases

### Pure Terraform/CLI Approach

No Python API, just Terraform + scripts.

**Rejected because:**
- Poor developer experience
- Can't easily iterate locally
- Harder to integrate into existing workflows

---

## References

- [RFC 27: Scenario Support](../27-scenario-support/27-scenario-support-rfc.md)
- [Performance Benchmarks](../27-scenario-support/27-performance-and-scale.md)
- [Azure Benchmark Proposal](./28-gaspatchio_azure_benchmark_proposal.md)
- [Polars Cloud Quickstart](https://docs.pola.rs/polars-cloud/quickstart/)
- [Polars Cloud Remote Query](https://docs.pola.rs/polars-cloud/run/remote-query/)
- [Polars GPU Support](https://docs.pola.rs/user-guide/gpu-support/)
