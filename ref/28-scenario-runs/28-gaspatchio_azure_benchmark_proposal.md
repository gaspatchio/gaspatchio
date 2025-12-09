# Proposal: Azure-Based Benchmarking Harness for Gaspatchio (VMs + Docker + GPU)

## 1. Background and Goals

Gaspatchio models are compute-heavy (Polars, Rust-backed lookups, large scenario grids) and will ultimately be deployed on a mix of CPU and GPU hardware. We want a **repeatable, data-driven way** to answer:

- How fast do representative gaspatchio workloads run on different Azure VM sizes (CPU vs GPU)?
- What is the **performance per dollar** for each SKU?
- When does the **Polars GPU engine** provide a meaningful speed-up for our real workloads?
- What is the recommended “default” hardware profile for:
  - local exploratory work,
  - CI/regression runs,
  - big valuation/scenario batches?

The core idea is to build a **benchmark harness** that can be executed in a consistent environment across many Azure VM SKUs, with:

- A single, canonical entrypoint (e.g. `python bench.py`) that runs one or more gaspatchio models.
- A **containerized** runtime (Docker) to keep the software stack fixed and reproducible.
- A small amount of Azure infra that:
  - spins up VMs of various sizes (CPU and GPU),
  - runs the benchmark container N times,
  - uploads the results (JSON/CSV) into blob storage,
  - and tears the VM down or deallocates it.

This gives us a repeatable “hardware lab” that we can re-run after major changes (new gaspatchio release, new Polars GPU version, etc.).

---

## 2. Why Use Docker Even for “Serious” Benchmarks

### 2.1 Reproducibility > Micro-Optimizing Away Container Overhead

On Azure, you are always running inside a VM hypervisor. Docker on Linux just adds:

- process isolation (namespaces),
- resource limits (cgroups),
- an overlay filesystem for the image layers.

For the kind of workloads we care about (Polars + Rust + CUDA kernels):

- CPU-bound overhead from Docker is typically in the **noise level** (often < 1–2% and dominated by run-to-run jitter).
- GPU performance is governed by:
  - CUDA kernels,
  - GPU memory bandwidth,
  - PCIe/NVLink,
  none of which are meaningfully altered by being inside a container.

In exchange, we gain:

- A **fixed Python/CUDA/Polars/gaspatchio stack**, pinned to exact versions.
- A single benchmark image that can be:
  - run on developer machines,
  - re-used in CI,
  - re-used on-prem or other clouds if needed.
- Much simpler setup on each VM: “install Docker (+ NVIDIA runtime), pull image, run once” instead of recreating Python environments everywhere.

We can empirically verify container-vs-native overhead on one or two SKUs by running both ways and comparing medians. Once we’ve shown the difference is negligible, we can confidently do all cross-SKU comparisons in Docker.

### 2.2 Docker with GPU: Not a Barrier to Acceleration

For GPU work, Docker is a first-class path:

- The container uses the **same host NVIDIA driver** and **same CUDA runtime** as native processes.
- The NVIDIA container runtime (`--gpus all`) exposes `/dev/nvidia*` devices and required libraries into the container.
- Polars’ GPU engine (via RAPIDS/cuDF) runs inside this environment just as it would on bare metal.

The main gotchas are:

- Ensuring the host driver is new enough for the CUDA version in the container.
- Installing `nvidia-container-toolkit` so `docker run --gpus all` works.
- Verifying that `collect(engine="gpu")` actually runs on GPU (easy to add a smoke test in `bench.py`).

With those in place, the GPU kernels see the same hardware behavior whether we run in a container or not.

---

## 3. Benchmark Design

### 3.1 Canonical Benchmark Harness (`bench.py`)

We will define a single Python entrypoint, e.g. `bench.py`, responsible for:

1. Loading a fixed dataset (e.g. model points, scenario tables) from a known path (e.g. `/data`).
2. Building the appropriate `ActuarialFrame` and gaspatchio model pipeline.
3. Running one or more standard workloads:
   - A realistic but bounded run (e.g. N policies × M scenarios).
   - Optionally both **CPU** and **GPU** modes on the same machine (for direct comparison).
4. Measuring:
   - wall-clock time (per benchmark variant),
   - row/column counts of outputs,
   - selected profiling stats (Polars `profile()` output, if available),
   - system info (VM size, core count, RAM, GPU model, etc.),
   - configuration (e.g. `POLARS_MAX_THREADS`, `engine="cpu"|"gpu"`).
5. Writing a single JSON (and optional CSV) metrics file, e.g.:

```json
{
  "bench_suite": "gaspatchio_baseline_v1",
  "bench_name": "lapse_model_10k_scenarios",
  "engine": "gpu",
  "wall_time_s": 43.2,
  "n_rows": 1234567,
  "n_cols": 24,
  "run_index": 3,
  "vm_size": "Standard_NV12ads_A10_v5",
  "azure_region": "australiaeast",
  "container": true,
  "cores": 12,
  "memory_gb": 56,
  "gpu_model": "NVIDIA A10",
  "gpu_mem_gb": 24,
  "threads": 12,
  "git_sha_gaspatchio": "...",
  "git_sha_model": "..."
}
```

We’ll run each configuration multiple times (e.g. 5–10 runs) and use the median wall-time for comparisons.

### 3.2 Controlling Variability

To make comparisons meaningful, we’ll:

- Pin thread counts:
  - `POLARS_MAX_THREADS` / `RAYON_NUM_THREADS` = number of vCPUs per VM (or a fixed cap).
- Use the same dataset across all runs:
  - dataset stored in Azure Blob Storage and copied to local SSD (`/mnt`) on the VM,
  - the container binds that local directory as `/data`.
- Do at least one warm-up run on each VM (not counted in metrics).
- Use a single Azure region (e.g. `australiaeast`) for all tests.
- Keep VMs “clean”:
  - benchmark VMs are used only for these runs,
  - shut down or deallocate immediately after.

---

## 4. VM and Docker Choices

### 4.1 CPU VM Families

We want to cover the main axes:

- **Balanced general-purpose**: Dsv5 (compute + memory balance).
- **Compute-optimized**: Fsv2 (higher clock, more vCPUs).
- **Memory-optimized**: Ebs/Easv5 (for extremely wide tables or memory-heavy joins).

Representative sizes might include:

- `Standard_D4ds_v5` (4 vCPUs, balanced)
- `Standard_D8ds_v5` (8 vCPUs)
- `Standard_F8s_v2` (compute-optimized)
- `Standard_E8ds_v5` or `Standard_E16ds_v5` (memory-optimized)

These will be used for:

- Baseline CPU-only Polars runs.
- Regression benchmarking as gaspatchio evolves.

### 4.2 GPU VM Families

For Polars GPU acceleration, we care about modern NVIDIA GPUs with sufficient VRAM:

- **NVads A10 v5** family (NVIDIA A10, 24 GB):
  - Good price/performance for mixed compute workloads.
  - Supports partial GPU instances with different vCPU/RAM profiles.
- Optionally:
  - Other NC/NV SKUs if we want to explore higher-end GPUs or more VRAM.

Representative sizes:

- `Standard_NV12ads_A10_v5` (1/2 A10 GPU, ~12 vCPUs, mid-level RAM).
- `Standard_NV36ads_A10_v5` (full A10 with more CPU/RAM).

These will be used for:

- Direct CPU vs GPU comparisons on the same VM family.
- Determining how large a workload needs to be before GPU overhead is amortised.

### 4.3 Why Dedicated VMs (Not Serverless Container Services)

Because these are **“serious”** benchmarks, we prioritize:

- Complete control over:
  - VM size,
  - driver version,
  - background load.
- Stable performance over convenience.

We therefore prefer:

- Dedicated Azure VMs (one VM per SKU/config).
- Light cloud-init / Custom Script configuration to:
  - install Docker (+ NVIDIA runtime for GPU VMs),
  - pull the benchmark container,
  - run `bench.py` N times,
  - upload results to blob storage,
  - shut the VM down.

Container services (e.g. Container Apps) are great for steady-state workloads but introduce more moving parts, and their internal scheduling behaviour is less transparent for fine-grained benchmarking.

---

## 5. Azure Implementation Plan

We’ll implement the harness in layers:

1. **Core assets** (once, in the repo).
2. **Infrastructure module** (“benchmark VM” template).
3. **Orchestrator** (matrix runner).
4. **Analysis scripts**.

### 5.1 Core Assets

1. `bench.py` (as above).
2. `Dockerfile.cpu`:
   - Base: Ubuntu or a slim Python base image.
   - Installs gaspatchio + Polars CPU + dependencies.
   - Copies `bench.py` and model code into `/app`.
   - Default `CMD ["python", "bench.py"]`.

3. `Dockerfile.gpu`:
   - Base: `nvcr.io/nvidia/cuda:<version>-devel-ubuntu22.04` or similar.
   - Installs gaspatchio + Polars GPU (`polars[gpu]`) + CUDA/RAPIDS deps.
   - Same entrypoint as CPU image.

We can eventually unify these into a single multi-stage or parameterized image, but starting with `-cpu` and `-gpu` tags is simpler.

4. Build & push images to Azure Container Registry (ACR):

```bash
az acr create -g <rg> -n <acr_name> --sku Basic

docker build -f Dockerfile.cpu -t <acr_name>.azurecr.io/gspio-bench:cpu .
docker build -f Dockerfile.gpu -t <acr_name>.azurecr.io/gspio-bench:gpu .

az acr login -n <acr_name>
docker push <acr_name>.azurecr.io/gspio-bench:cpu
docker push <acr_name>.azurecr.io/gspio-bench:gpu
```

### 5.2 Benchmark VM Template (Terraform / Bicep / ARM)

We create a reusable “benchmark VM” module with parameters:

- `vm_size` (e.g. `Standard_D8ds_v5`, `Standard_NV12ads_A10_v5`),
- `image` (Ubuntu 22.04),
- `use_gpu` (bool),
- `sku_label` (for tagging in metrics),
- `runs` (number of benchmark reps),
- references to:
  - ACR name,
  - Storage account & container for results,
  - Resource group & region.

The VM is configured with:

- **Managed identity** (for access to ACR and Storage).
- **Cloud-init** or Custom Script Extension that:
  1. Installs Docker.
  2. If `use_gpu == true`, installs NVIDIA driver and `nvidia-container-toolkit`.
  3. Logs into ACR (`az acr login` using managed identity).
  4. Pulls the appropriate image (`gspio-bench:cpu` or `gspio-bench:gpu`).
  5. Downloads data from Storage to local SSD (e.g. `/mnt/data`).
  6. Runs the benchmark container N times:

     ```bash
     for i in $(seq 1 $RUNS); do
       docker run --rm \
         --cpus $VCPU_COUNT \
         --memory ${MEMORY_LIMIT}g \
         ${GPU_FLAGS} \
         -e BENCH_SUITE="gaspatchio_baseline_v1" \
         -e BENCH_NAME="lapse_model_10k_scenarios" \
         -e RUN_INDEX=$i \
         -e VM_SIZE="$VM_SIZE" \
         -e SKU_LABEL="$SKU_LABEL" \
         -e AZURE_REGION="$LOCATION" \
         -e POLARS_MAX_THREADS="$VCPU_COUNT" \
         -v /mnt/data:/data \
         -v /mnt/bench_out:/bench_out \
         <acr_name>.azurecr.io/gspio-bench:${IMAGE_TAG}
     done
     ```

  7. Uploads all `bench_result*.json` files in `/mnt/bench_out` to the Storage container (using the VM’s managed identity).
  8. Shuts down / deallocates the VM.

This module can be instantiated for each SKU we want to test.

### 5.3 Orchestrator (Matrix Runner)

We then define the list of benchmark configurations centrally, for example in Terraform:

```hcl
variable "benchmarks" {
  type = map(object({
    vm_size   = string
    use_gpu   = bool
    runs      = number
    image_tag = string
  }))

  default = {
    "D8ds_v5_cpu" = {
      vm_size   = "Standard_D8ds_v5"
      use_gpu   = false
      runs      = 5
      image_tag = "cpu"
    }
    "NV12ads_A10_gpu" = {
      vm_size   = "Standard_NV12ads_A10_v5"
      use_gpu   = true
      runs      = 5
      image_tag = "gpu"
    }
    "NV36ads_A10_gpu" = {
      vm_size   = "Standard_NV36ads_A10_v5"
      use_gpu   = true
      runs      = 5
      image_tag = "gpu"
    }
  }
}

module "bench_vm" {
  for_each = var.benchmarks
  source   = "./modules/bench_vm"

  vm_size   = each.value.vm_size
  use_gpu   = each.value.use_gpu
  runs      = each.value.runs
  image_tag = each.value.image_tag
  sku_label = each.key
}
```

We can invoke this:

- Locally (`terraform apply`),
- Or via a GitHub Actions workflow that:
  - applies the configuration,
  - waits for VMs to complete and shut down,
  - then triggers a follow-up job to download/analyse results.

### 5.4 Results Storage and Analysis

- **Storage**:
  - One Storage account (e.g. `gspioBenchResults`),
  - Container: `benchmarks`,
  - Files named: `bench_suite/sku_label/run_index.json`.

- **Analysis**:
  - A small `analyze_benchmarks.py` script (Polars-based) that:
    - downloads all JSON files from the container,
    - loads them into a `DataFrame`,
    - aggregates by `{bench_suite, bench_name, sku_label, engine}`,
    - computes medians, min/max, and maybe cost-per-run (once we enrich with pricing).

Example high-level report:

- For each benchmark workload:
  - Ranking of SKUs by **wall_time_s**,
  - Ranking of SKUs by **wall_time_s / hourly_cost** (performance per dollar),
  - CPU vs GPU comparisons on the same VM family.

---

## 6. Native vs Container Validation (One-Time)

To address any lingering concern about Docker overhead, we can add a one-off step:

1. Pick a representative VM (e.g. `Standard_D8ds_v5` for CPU and `Standard_NV12ads_A10_v5` for GPU).
2. On each:
   - Run the benchmark **natively** (host Python environment, no Docker) 5–10 times.
   - Run the benchmark via Docker (same image used across all other tests) 5–10 times.
3. Compare the median wall-times:
   - If difference is within ~2–3%, we treat them as equivalent for our purposes and proceed with container-only benchmarking.
   - If we observe a larger gap, we investigate:
     - CPU limits passed to Docker,
     - data location (overlayfs vs local SSD),
     - any host-only background services.

This gives us documented, empirical support that containers are a non-issue for our use case.

---

## 7. Benefits and Next Steps

### 7.1 Benefits

- **Reproducible benchmarks**:
  - Fixed environment (Docker images) and fixed benchmark harness.
- **Hardware comparability**:
  - Same workload across multiple Azure SKUs (CPU and GPU) with consistent methodology.
- **Actionable decisions**:
  - Clear recommendations for:
    - default VM SKUs for production workloads,
    - minimum viable VM sizes for small/medium users,
    - when to recommend GPU vs CPU for a given model size.
- **Future-proofing**:
  - Easy to re-run after:
    - gaspatchio performance improvements,
    - Polars (CPU or GPU) upgrades,
    - new Azure VM families.

### 7.2 Next Steps

1. Implement `bench.py` and agree on:
   - benchmark suite name(s),
   - workloads to include (e.g. 1–2 representative models).
2. Build and push `gspio-bench:cpu` and `gspio-bench:gpu` images to ACR.
3. Implement the “benchmark VM” module in Terraform (or Bicep/ARM, if preferred).
4. Define the initial benchmark matrix (3–5 SKUs: 2–3 CPU, 1–2 GPU).
5. Run the first full benchmark sweep and:
   - validate Docker vs native on 1 CPU and 1 GPU SKU,
   - generate a first pass performance report.
6. Iterate:
   - refine workloads,
   - extend to more SKUs as needed,
   - fold the findings into gaspatchio documentation (“Recommended Azure hardware”).

Once this is in place, running “serious” benchmark campaigns becomes a matter of updating a configuration file and re-applying infra, rather than hand-building environments on ad hoc machines.
