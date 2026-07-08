window.BENCHMARK_DATA = {
  "lastUpdate": 1783475040744,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Gaspatchio vs Lifelib (Windows)": [
      {
        "commit": {
          "author": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "distinct": true,
          "id": "e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7",
          "message": "ci(evals): enable Gaspatchio vs Lifelib comparison on the public repo\n\nBENCHMARKS_DEPLOY_KEY (read-only deploy key for opioinc/gaspatchio-benchmarks)\nis now configured as an Actions secret on gaspatchio/gaspatchio, so the\ncomparison job can clone the lifelib reference data. Restore its normal trigger\n(schedule / dispatch / push-main / benchmark label); it runs on the free\nstandard runners with the other public suites and publishes to dev/comparison.",
          "timestamp": "2026-07-07T14:57:55+12:00",
          "tree_id": "9765b961fc48b4d840b2c4c8a2229bb01a04a978",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7"
        },
        "date": 1783393871432,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.724,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 2.997,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.322,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 24.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.388,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 22.94,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.448,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2232.1,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 26.773,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 37.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 59.76,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.406,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4156.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 21.973,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 455.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.13,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.712,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4403,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 155.139,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 644.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.83,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "distinct": true,
          "id": "2a761959f16118a54710c92dcaefbe319aad46d1",
          "message": "ci(evals): give Criterion Windows headroom (40m timeout + rust-cache)\n\nThe Criterion benchmark job timed out at 20 minutes on the free\nwindows-latest runner: an uncached cargo bench compiles polars +\ncriterion from scratch, which exceeds 20m on Windows (Linux fits).\nGitHub cancelled the job, so dev/bench-windows never populated.\n\nBump the job timeout to 40m and add Swatinem/rust-cache. Only compiled\ndependencies are cached; the bench crate is rebuilt and run fresh each\ntime, so measured numbers stay accurate while warm builds land well\ninside the window.",
          "timestamp": "2026-07-07T15:22:29+12:00",
          "tree_id": "011e6dec1adf87b40e025acc9c1fc5e828926a01",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/2a761959f16118a54710c92dcaefbe319aad46d1"
        },
        "date": 1783395297802,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 15.426,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.793,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.377,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 21.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 6.801,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 18.04,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.383,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2611,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 23.347,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 42.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 60.96,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 1.953,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 5120.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 20.117,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 497.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 10.3,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 19.179,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 5214,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 154.474,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 647.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 8.05,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "1277725+mrmattwright@users.noreply.github.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0d479c24928f2489239063e39a27f2ec73d5ff71",
          "message": "fix(scenarios): gate auto-search probes so measuring a batch can never OOM the box (#8)\n\nfor_each_scenario(batch_size=\"auto\") resolved batch size by running each\nladder rung and checking the memory budget only after the probe returned.\nA probe larger than physical memory dies mid-collect() -- before its peak\nis recorded and before any back-off logic can run -- so the search itself\ncould kill the process (or the whole runner). Observed on the CI scenario\nbenchmark's 10-scenario x 100K-policy cell: b=1 measured 3.1 GB and fit,\nthen the b=4 streaming probe demanded ~11.5 GB on a 16 GB runner\n(Windows measured 11,226 MB on the same cell and survived only because\nits pagefile absorbed the spike). Reproduced under a 4 GB cgroup:\nkernel OOMKilled=true during probe #2, no clean error.\n\nGate every rung after the first by linear extrapolation from the last\nmeasured rung (peak grows at most linearly in batch for the scenario\ncross-join; measured ratios were 3.0-3.7x, so the prediction\nover-estimates). A rung whose predicted peak already fails the fits test\ncould never be selected, so probing it pays an unbounded memory cost for\nzero information. With the gate, the same 4 GB container cell completes\nin 7.5 s at batch=1 instead of being killed; runs that previously paid a\ndoomed probe get faster as well as safe.\n\nNo new constants: the gate reuses the measured peak, the actual batch\nratio, and the existing safety_margin/budget. Residual risk documented:\nthe first rung (streaming b=1) has no prior to predict from.\n\nIrreducibleCellError's contract ('fails loudly ... rather than being\nOOM-killed by the kernel mid-collect()') now holds on the probe path.",
          "timestamp": "2026-07-07T21:59:48+12:00",
          "tree_id": "61f872c9021500063c716ee9dc611a8de86aaafe",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0d479c24928f2489239063e39a27f2ec73d5ff71"
        },
        "date": 1783419182842,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.761,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.032,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.372,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 21.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.238,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 19.46,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.439,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2277.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.663,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 39,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 58.46,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.379,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4203.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 21.527,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 464.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.05,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.643,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4416.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 155.8,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 641.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.88,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "1277725+mrmattwright@users.noreply.github.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "346d4662b985d7a4a128252ba7c83d468ed010a0",
          "message": "fix(scenarios): probe gate predicts super-linear streaming cross-join peaks (#10)\n\nThe gate from the previous fix extrapolated a rung's peak linearly in\nbatch size from the last measured rung. Field falsification on the CI\n10sc x 100K cell: b=1 measured ~1.3 GB on the 4-core runner, so a linear\nprediction put b=4 within the 7.7 GB budget -- but the actual b=4 demand\nwas ~11.5 GB (8.6x the b=1 rung, 2.2x ABOVE linear; the Polars #20786\ncross-join inflation is super-linear in batch at high policy counts) and\nthe probe killed the runner again. Locally-measured 1K-10K ratios\n(3.0-3.7x, sub-linear) do not extrapolate to 100K: the scaling law\nitself changes with scale.\n\nMultiply the gate's linear prediction by streaming_batch_inflation\n(3.0, a named SizingDefaults constant chosen above the worst observed\n2.2x excess). Checked against every measured cell: 1K/10K cells keep\ntheir current batch choices; the 100K killer rung is now gated; the one\nbehavioral downgrade is 1000sc x 1K picking b=16 over b=64 (~8% slower)\n-- reliability over peak throughput. Over-predicting costs at most a\nsmaller batch; under-predicting costs the process.\n\nNew test pins the factor: a budget that a bare-linear gate would pass\n(100 MB peak, 1 GB budget -> linear 520 MB) must still skip the b=4\nprobe (inflated 1560 MB).",
          "timestamp": "2026-07-08T09:21:41+12:00",
          "tree_id": "7aeae535b10b4a974f6d35471b9d4bb10dcb7a20",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/346d4662b985d7a4a128252ba7c83d468ed010a0"
        },
        "date": 1783460080424,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 4.608,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.012,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.265,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 30.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 6.826,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 25.76,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.432,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2314.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 23.923,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 41.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 55.38,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.343,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4268,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 20.336,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 491.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.68,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.759,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4393.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 154.913,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 645.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.81,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "1277725+mrmattwright@users.noreply.github.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "56797ef297e3cd76a5a9de4b474a89ce1fe7d28e",
          "message": "fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes (#11)\n\n* fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes\n\nThird and deepest layer of the auto-search OOM fix: the gate's INPUT was\nbroken. Probe peaks are measured as RSS delta-over-baseline -- but in a\nprocess with retained allocator pools, a batch can be served entirely\nfrom pooled memory: RSS never grows and the sampler reads ~0. Observed\nlive on CI (probes: [b1/streaming=0MB+fits]) -- any prediction\nmultiplied from that zero is blind, so the gate launched an unaffordable\nprobe and the runner died again. The budget also collapsed across bench\ncells (7148 -> 3094 MB) because base RSS includes the pools.\n\nLibrary: floor each batch's measured peak with the materialised frame's\nestimated_size() -- the frame's bytes are live memory at peak regardless\nof where the allocator got them. This is the same floor the policy axis\nhas always applied to its seed measurement (_spill/_aggregated).\n\nBench: run each grid cell of run_scenario_benchmarks.py in a fresh\ninterpreter (the pattern scenario_batch_search_bench already uses for\nits floor workers): clean allocator baseline, honest probe measurements,\nfull budget per cell -- and a kernel-killed cell now loses one cell, not\nthe whole run. Child stderr is inherited so probe-ladder lines stream\ninto the CI log.\n\nNew test pins the pool-reuse lie: with the sampler forced to read 0 and\na budget the frame fits at b=1, the b=4 rung must still be gated and the\nrecorded rung peak must be the floor, not the lie.\n\n* fix(evals): distinguish cell kills from cell errors; bound cell wall clock\n\nReview feedback (Greptile, both accepted): the subprocess wrapper treated\nevery childless exit as a benign skip and had no per-cell timeout.\n\n- A clean nonzero exit with no result is a real error (import failure,\n  bug) -- raise so CI fails instead of publishing an incomplete benchmark\n  as green. Only signal kills (negative returncode, e.g. kernel OOM) and\n  timeouts are tolerated as one-cell losses, which is what the isolation\n  is for.\n- Cap each cell at 30 min (heaviest legitimate cell ~6 min) so one wedged\n  cell cannot eat the job timeout and lose every other cell's output.\n\nVerified: happy path returns metrics; a crashing child (missing points\nfile) raises RuntimeError in the parent.",
          "timestamp": "2026-07-08T10:34:49+12:00",
          "tree_id": "78eea24f36fce56777dfd384309a09753d470d54",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/56797ef297e3cd76a5a9de4b474a89ce1fe7d28e"
        },
        "date": 1783464451794,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.631,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.061,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.362,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 22.1,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.622,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 21.06,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.442,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2262.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 24.952,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 40.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 56.45,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.362,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4233.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 20.92,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 478,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.86,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.849,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4376.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 153.622,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 650.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.72,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "distinct": true,
          "id": "ec906df4330539df20b2913be4e9c199e4e1f1e8",
          "message": "ci(evals): run scenario benchmarks on every push to main\n\nThe scenario suite now completes reliably on free standard runners: the\nauto-search OOM chain is fixed (#8/#10/#11 gate + inflation + frame\nfloor) and the bench tolerates irreducible cells and isolates each cell\nin a fresh process (#9/#11). Validated on dispatch run 28903417786 --\nthe 10sc x 100K cell completes at batch=1 in 209s/6.5GB with the gate\nblocking the b=4 probe (probes: [b1/streaming=3198MB+fits] budget=7275MB).\n\nAdd push-to-main to the job's trigger so dev/scenario-bench{,-windows}\naccumulate a data point per merge, like the other benchmark suites.",
          "timestamp": "2026-07-08T10:56:32+12:00",
          "tree_id": "bf4e7d57e8e151dc257a9212034540677f13eb31",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ec906df4330539df20b2913be4e9c199e4e1f1e8"
        },
        "date": 1783465793278,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.814,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.01,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.357,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 22.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.585,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 21.25,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.556,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 1798.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.994,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 38.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 46.75,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.388,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4187.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 22.184,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 450.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.29,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 23.241,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4302.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 157.051,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 636.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.76,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "distinct": true,
          "id": "ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4",
          "message": "release: v0.5.3",
          "timestamp": "2026-07-08T12:06:26+12:00",
          "tree_id": "1f26e1d201ebd4d1b166b0280e6c9f758cccbe90",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4"
        },
        "date": 1783469952423,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 4.692,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.102,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.386,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 20.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 8.268,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 21.42,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.581,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 1721.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 29.488,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 33.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 50.75,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 3.367,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 2970,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 24.652,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 405.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.32,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.969,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4353.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 156.98,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 637,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.83,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "committer": {
            "email": "matt@opioinc.com",
            "name": "Matt Wright",
            "username": "mrmattwright"
          },
          "distinct": true,
          "id": "a4bfc5580c9525d19b28149ccc143914010a4597",
          "message": "ci: drop develop from workflow triggers\n\nThe public repo is trunk-based: develop was a launch-era leftover whose\ncontent is fully contained in main (post-release fixes landed via squash\nPR #7), and the branch has been deleted. Feature branches PR straight to\nmain; releases are signed tags on main.",
          "timestamp": "2026-07-08T13:30:41+12:00",
          "tree_id": "81d5b3dcfb5f2545f7642c835393e05f38f4c47d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/a4bfc5580c9525d19b28149ccc143914010a4597"
        },
        "date": 1783475036655,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 8.231,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 4.105,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.34,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 23.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 8.198,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 24.11,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.568,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 1760.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 28.042,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 35.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 49.37,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 3.356,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 2979.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 24.291,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 411.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.24,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.884,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4369.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 152.022,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 657.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.64,
            "unit": "x"
          }
        ]
      }
    ]
  }
}