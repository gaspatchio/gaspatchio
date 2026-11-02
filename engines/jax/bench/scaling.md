# The JAX engine, measured

Measured on the tree that **the commit carrying this file** holds, as it stood on 2026-09-24. The measurement and the code it measures travel together, which is why this file has no commit in its name: a name carrying one would point at a tree the code is not in. Every figure below is one laptop's; what is stable about them is the ratios and the shapes, not the seconds.

- **Over** the tree of 2026-09-24, with uncommitted changes
- **Machine** macOS-15.7.9-x86_64-i386-64bit-Mach-O, 8 physical cores, 16 GiB
- **Device** cpu: cpu
- **Interpreter** `engines/jax/.venv/bin/python` 3.13.0
- **jax** 0.4.38 / **jaxlib** 0.4.38 / **polars** 1.42.1 / **numpy** 2.5.3
- **Core extension** `_internal.cpython-313-darwin.so`, sha256 `16df6b5117fdb148c293d4f07013c1e40fe3da9474f4cd402cc0d2fe20c9fa90`
- **Compilation cache** `~/Library/Caches/gaspatchio-jax/compilation` (the default user cache)

## Scaling

| model | policies | batches | batch | compiles | widths | temp B/policy | pre-flight s | warm batch s | wall s | RSS fixed MB | RSS peak MB | Polars s | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| level-4 | 1,000 | 1 | 1,000 | 1 | 84 | 1,345 | 0.96 | 0.0153 | 2.20 | 241 | 447 | 1.41 |  |
| level-4 | 10,000 | 1 | 10,000 | 1 | 84 | 1,345 | 0.87 | 0.1946 | 3.47 | 242 | 984 | 3.11 |  |
| level-4 | 100,000 | 2 | 65,536 | 2 | 84 | 1,345 | 1.04 | 0.9254 | 4.23 | 278 | 4157 | not attempted | region pass only; nothing published |
| level-4 | 1,000,000 | 16 | 65,536 | 2 | 84 | 1,345 | 2.43 | 1.3010 | 24.17 | 740 | 4851 | not attempted | region pass only; nothing published |
| level-5 | 1,000 | 1 | 1,000 | 1 | 84 | 1,345 | 0.58 | 0.0147 | 2.44 | 242 | 446 | 1.48 |  |
| level-5 | 10,000 | 1 | 10,000 | 1 | 84 | 1,345 | 0.61 | 0.2049 | 3.78 | 243 | 991 | 3.36 |  |
| level-5 | 100,000 | 2 | 65,536 | 2 | 84 | 1,345 | 1.15 | 1.0157 | 4.91 | 280 | 3881 | not attempted | region pass only; nothing published |
| level-5 | 1,000,000 | 16 | 65,536 | 2 | 84 | 1,345 | 2.69 | 1.4612 | 28.83 | 745 | 4790 | not attempted | region pass only; nothing published |
| jagged | 10,000 | 4 | 7,470 | 4 | 12,24,36,48 | 193 | 0.88 | 0.0229 | 8.36 | 242 | 669 | not attempted | terms of one to seven years; four widths in one book |

A *region pass only* row computes every batch and keeps none: it measures the projection rather than the door in front of it. A whole run at those sizes publishes too -- the engine writes each batch away as it finishes -- but it is mostly building and writing columns, which the whole rows measure.

**`RSS peak MB` is the kernel's high-water mark for the row alone** (`ru_maxrss`): each whole run and each region pass runs in a process of its own, so no row carries another's peak. `RSS fixed MB` is that process's resident set once the book is prepared, before any batch has run.

**`warm batch s` is the median over every batch of the run, a tail batch included where the book leaves one.** A row whose batch count is more than one and whose policies are not a whole multiple of its batch size therefore averages a full batch with a shorter one: at 100,000 policies the two batches are 65,536 and 34,464. The rows that report a full batch's own cost are the ones where the tail is a sixteenth of the run or less.

## Inside a region pass

Where each region-only row's wall went, in seconds summed over its batches: settling a batch on the host (its inputs, its axis, its horizons), finding its compiled program, the program itself, and the bench's own bookkeeping (reading the program's temporaries). *Other* is the wall less the four.

| model | policies | settle s | program s | compute s | bookkeeping s | other s |
|---|---|---|---|---|---|---|
| level-4 | 100,000 | 0.37 | 0.82 | 1.85 | 0.02 | 1.18 |
| level-4 | 1,000,000 | 1.93 | 0.83 | 19.97 | 0.19 | 1.25 |
| level-5 | 100,000 | 0.44 | 1.04 | 2.03 | 0.02 | 1.38 |
| level-5 | 1,000,000 | 2.82 | 1.44 | 22.72 | 0.20 | 1.65 |

## Compilation

Each figure is taken at the size its own row names — 4,096 policies for the two rectangles, the whole book for the jagged one — and **each in a fresh interpreter over a cache directory that starts empty**. They are in a table of their own because they are figures about one shape, and printing them against the sizes above would attach them to shapes those rows do not use.

| model | policies | cold s | from the cache s | ratio |
|---|---|---|---|---|
| level-4 | 4,096 | 1.91 | 0.13 | 15x |
| level-5 | 4,096 | 1.89 | 0.14 | 14x |
| jagged | 10,000 | 2.17 | 0.14 | 16x |

## What a warm figure is worth

One measurement — level 4, 10,000 policies, one warm batch, the median of 5 — taken 7 times in this run, **each through a fresh plan, a fresh settled batch and a freshly compiled program**. Any conclusion drawn from a difference between two warm figures is a conclusion about this number first.

| readings | min s | max s | spread |
|---|---|---|---|
| 7 | 0.1909 | 0.1961 | **2.7 %** |

## The sequential scan's cost

Level 4's own `sum`, warm, with the sequential `lax.scan` the folds use and with `jnp.sum` in its place. The verdict column is the cost against the spread above, and it is read off these numbers rather than argued.

| book | scan s | jnp.sum s | cost | verdict |
|---|---|---|---|---|
| 1,000 | 0.0150 | 0.0139 | +7.7 % | ABOVE the warm figure's own spread |
| 10,000 | 0.1899 | 0.1727 | +10.0 % | ABOVE the warm figure's own spread |


