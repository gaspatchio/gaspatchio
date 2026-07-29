window.BENCHMARK_DATA = {
  "lastUpdate": 1785303060787,
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
          "id": "bc41aa4859f2939f232cebce2f855cac1947619d",
          "message": "Bump polars to 1.42.1; rollforward extractions share one kernel call by construction (#14)\n\n* chore(deps): bump polars to 1.42.1, raise numpy cap to <2.6\n\nPolars 1.42's ColumnNotFoundError appends a query-plan dump to the\nmessage; the error formatter's first-word-before-newline heuristic\ngrabbed the dump's 'COLUMNS' token and reported the wrong column name.\nThe extraction now tries the quoted-name patterns first and confines\nthe legacy bare-word fallback to the message header, handling both the\nold and new formats.\n\nSupersedes dependabot PR #6, whose stale branch also predated the\nformatter fix and the v0.5.2/0.5.3 correctness work.\n\n* perf(rollforward): one kernel call per compiled rollforward, by construction\n\nMultiple extractions from one compiled rollforward were meant to share a\nsingle kernel call, but the mechanism was outsourced: the collector\ncached one plugin Expr and relied on the Polars optimiser's CSE pass to\ndeduplicate the .struct.field() reads. Polars 1.42 stopped applying CSE\nto plugin expressions (they may be non-deterministic), and in real\nworksheet-style models CSE never applied anyway — each 'af.x = ...' is\nits own with_columns node, so a K-state rollforward has always cost K\nfull kernel runs. The release-gate test only ever passed because it\npacked both extractions into a single with_columns.\n\nThe guarantee is now structural. CompiledRollforward carries the\nexpression surface directly — compiled.expr_for(state) /\ncompiled.increment_for(label) — returning references to one hidden\nstruct column named by the model fingerprint. ActuarialFrame\nmaterialises that column the first time an assigned expression\nreferences it (a fingerprint-keyed registry supplies the plugin expr)\nand, as it always has, strips __rollforward_* columns from collected\noutput. The plan is auditable: explain() shows one plugin node plus\ncheap field reads, on any polars version.\n\nRollforwardCollector stays as a deprecated facade with its old\nself-contained-expression semantics — kernel tests and raw-Polars usage\nkeep working unchanged — and compiled.plugin_expr() is the documented\nescape hatch outside ActuarialFrame. Tutorials move to the new surface\n(one line and one import shorter). The release gate now asserts the\nstacked-assignment pattern models actually use.\n\n* fix(curves): satisfy numpy 2.5 stubs in svensson tau grid; review polish\n\nThree follow-ups from CI and review on the polars/numpy bump:\n\n- numpy 2.5's stubs type ndarray iteration as np.float64, so reusing the\n  tau1/tau2 loop names for _refine_taus's plain-float results failed\n  mypy inside stubtest (the only CI failure — local resolve had numpy\n  2.1.3; CI resolves fresh). The grid-scan candidates get their own\n  names, which they deserved anyway.\n\n- CompiledRollforward builds its plugin expr once per instance\n  (cached_property, same pattern as _hidden_column) instead of\n  rebuilding one per extraction for setdefault to discard.\n\n- New wide-frame release-gate test (23 columns, past the\n  incremental-schema threshold) locks the cache self-heal invariant the\n  materialisation hook relies on: the dirty flag set by materialising\n  must be deep-resolved through the _schema property before\n  _apply_incremental_schema snapshots the cache. Review flagged the\n  snapshot as a staleness risk; investigation showed\n  _resolve_assigned_dtype's property read (column/shape.py:148) always\n  refreshes first, and this test fails if that ordering ever changes.\n\n* docs(skills): teach compiled.expr_for, not the deprecated collector\n\nThe delta detector in gaspatchio-docs correctly reports nothing to fix\n(RollforwardCollector still exists with an unchanged signature), but\nprose teaching a deprecated pattern is its designed blind spot — the\nmodel-building symbol table and the model-review antipatterns example\nnow show the blessed CompiledRollforward.expr_for surface.",
          "timestamp": "2026-07-08T16:44:15+12:00",
          "tree_id": "8d6a39ef8c423639457a09bb9389928d06edde0d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/bc41aa4859f2939f232cebce2f855cac1947619d"
        },
        "date": 1783486629038,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.885,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.046,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.361,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 22.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.129,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 19.75,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.501,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 1996,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.154,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 39.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 50.21,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.445,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4090,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 21.354,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 468.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.73,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 24.176,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4136.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 150.848,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 662.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.24,
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
          "id": "5a02e98c45f779e8734e9567afb0e326a8c50223",
          "message": "ci(release): build windows/macos wheels one interpreter per matrix leg (#15)\n\nThe v0.5.3-era wheel jobs built cp312/313/314 sequentially in one job via\n--find-interpreter. Measured on the first warm run after #12: the rust-cache\nhit exactly but windows still took 44 min (vs 51 cold), because the polars\nstack sits inside pyo3's dependency cone — every interpreter change\nrecompiles all 29 crates (~14 min), and the three sequential builds thrash\none target dir, so the saved cache only ever holds the last interpreter's\nartifacts and the expensive layer never hits.\n\nSplitting the interpreter into the matrix makes each leg build exactly one\nCPython (-i pinned to setup-python's interpreter), with its own cache key\nand artifact name. Legs run in parallel (~15 min wall-clock cold), and each\ncache holds one config so warm runs rebuild only the gaspatchio crates.\nThe release job's wheels-* download pattern picks up the renamed artifacts\nunchanged; the wheel set stays exactly cp312/313/314 per platform.",
          "timestamp": "2026-07-08T20:56:25+12:00",
          "tree_id": "ccc463340528e69b4b6820ec2f7842b994fc3ce0",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5a02e98c45f779e8734e9567afb0e326a8c50223"
        },
        "date": 1783501764948,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 15.976,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.102,
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
            "value": 7.187,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 21.14,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.458,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2183.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.447,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 39.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 55.56,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.967,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 3370.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 23.954,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 417.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.07,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 34.453,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 2902.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 155.815,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 641.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 4.52,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "1277725+mrmattwright@users.noreply.github.com"
          },
          "committer": {
            "name": "GitHub",
            "username": "web-flow",
            "email": "noreply@github.com"
          },
          "id": "5a02e98c45f779e8734e9567afb0e326a8c50223",
          "message": "ci(release): build windows/macos wheels one interpreter per matrix leg (#15)\n\nThe v0.5.3-era wheel jobs built cp312/313/314 sequentially in one job via\n--find-interpreter. Measured on the first warm run after #12: the rust-cache\nhit exactly but windows still took 44 min (vs 51 cold), because the polars\nstack sits inside pyo3's dependency cone — every interpreter change\nrecompiles all 29 crates (~14 min), and the three sequential builds thrash\none target dir, so the saved cache only ever holds the last interpreter's\nartifacts and the expensive layer never hits.\n\nSplitting the interpreter into the matrix makes each leg build exactly one\nCPython (-i pinned to setup-python's interpreter), with its own cache key\nand artifact name. Legs run in parallel (~15 min wall-clock cold), and each\ncache holds one config so warm runs rebuild only the gaspatchio crates.\nThe release job's wheels-* download pattern picks up the renamed artifacts\nunchanged; the wheel set stays exactly cp312/313/314 per platform.",
          "timestamp": "2026-07-08T08:56:25Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5a02e98c45f779e8734e9567afb0e326a8c50223"
        },
        "date": 1783923053378,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 4.211,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.096,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.356,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 22.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.415,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 20.83,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.487,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2053.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 26.196,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 38.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 53.79,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.426,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4122,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 22.107,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 452.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.11,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 23.194,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4311.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 156.742,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 638,
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
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "1277725+mrmattwright@users.noreply.github.com"
          },
          "committer": {
            "name": "GitHub",
            "username": "web-flow",
            "email": "noreply@github.com"
          },
          "id": "5a02e98c45f779e8734e9567afb0e326a8c50223",
          "message": "ci(release): build windows/macos wheels one interpreter per matrix leg (#15)\n\nThe v0.5.3-era wheel jobs built cp312/313/314 sequentially in one job via\n--find-interpreter. Measured on the first warm run after #12: the rust-cache\nhit exactly but windows still took 44 min (vs 51 cold), because the polars\nstack sits inside pyo3's dependency cone — every interpreter change\nrecompiles all 29 crates (~14 min), and the three sequential builds thrash\none target dir, so the saved cache only ever holds the last interpreter's\nartifacts and the expensive layer never hits.\n\nSplitting the interpreter into the matrix makes each leg build exactly one\nCPython (-i pinned to setup-python's interpreter), with its own cache key\nand artifact name. Legs run in parallel (~15 min wall-clock cold), and each\ncache holds one config so warm runs rebuild only the gaspatchio crates.\nThe release job's wheels-* download pattern picks up the renamed artifacts\nunchanged; the wheel set stays exactly cp312/313/314 per platform.",
          "timestamp": "2026-07-08T08:56:25Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5a02e98c45f779e8734e9567afb0e326a8c50223"
        },
        "date": 1784527766172,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.547,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 2.689,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.303,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 26.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 6.869,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 22.67,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.378,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2645.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.525,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 48.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 54.3,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 1.766,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 5662.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 17.11,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 584.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.69,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 17.17,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 5824.1,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 135.23,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 739.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 7.88,
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
          "id": "f7b2b0e8b14d9c2615b8304faf62cec38bb84502",
          "message": "Apply the documented dimensions rename mapping; invite private bug reports (#32)\n\n* fix(assumptions): apply the documented dimensions rename mapping\n\nThe dimensions dict is documented as mapping YOUR name -> SOURCE column\nname, but the string-shorthand conversion built DataDimension(source)\nand discarded the dict key: rename_to was never set, the processed\ntable kept the source column names, and lookup() failed with \"No value\nprovided for key column '<source name>'\". Every shipped example uses\nidentity mappings, so the rename path had never worked.\n\n- Shorthand entries now wire rename_to=dim_name (identity mappings are\n  a no-op).\n- An explicit DataDimension under a differing dict key gets the same\n  default; a user-set rename_to still controls the processed column\n  name, and lookup() translates it back so lookups always speak the\n  dimension-dict vocabulary.\n- The 'shouldn't happen' error now reports both vocabularies when a\n  custom dimension produces an unmatched column name.\n\nFixes #30. Reported via a private field report.\n\n* docs(security): invite private bug reports with an anonymisation promise\n\nMany gaspatchio users work at insurers and cannot post code publicly.\nDocument the intake path: any bug may be reported by email; confirmed\nbugs get a public tracking issue with a rewritten neutral reproduction,\nno names, employers, or model details, and opt-in-only credit.\n\n* fix(assumptions): preserve renamed dimensions through shock reconstruction\n\nReview follow-up (greptile P1 on #32): with_shock/from_shocks rebuild a\nTable from its PROCESSED frame but generated identity dimension specs\nfrom the dict keys (with_shock via a column_name attribute that\nDataDimension does not even have), so any dimension whose processed\ncolumn name differs from its key — an explicit\nDataDimension(rename_to=...) — failed reconstruction with 'Column not\nfound'.\n\n_reconstruction_dimensions() maps each dimension key to its processed\ncolumn name; all three reconstruction sites use it, computed from the\ntable actually supplying the source frame (after with_shock, an\nexplicit rename_to has already collapsed to the dimension name). The\nlookup vocabulary is preserved through arbitrary shock chains.\n\n* fix(assumptions): honour non-Data dimension output names in lookup and reconstruction\n\nReview follow-up (second greptile P1 on #32): Melt/Categorical/Computed\ndimensions surface their processed column via their  field, which\nmay differ from the dimensions-dict key. The lookup translation and\n_reconstruction_dimensions() only handled DataDimension, so such tables\nfailed lookup('No value provided for key column') and failed shock\nreconstruction against a nonexistent column.\n\nBoth now map , so the lookup\nvocabulary (the dict keys) holds for every dimension type, through\nwith_shock and both from_shocks branches. Regression test: a\nMeltDimension named differently from its dict key, looked up and\nshocked.\n\n* chore(deps): pin ruff — the docstring-example linter is version-sensitive\n\nCI resolves dev dependencies fresh (no lockfile ships in this repo), so\nruff>=0.11.10 floated to yesterday's 0.16.0 release, whose changed I001\nimport-sorting behaviour failed ~70 docstring-example lint tests on\nevery PR regardless of its diff. Pin to the version the examples are\nwritten against; the systemic reproducibility fix is tracked in #33.",
          "timestamp": "2026-07-26T15:07:38+12:00",
          "tree_id": "ff0d146f3b39a49d30ba833252f1dea60226af9f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/f7b2b0e8b14d9c2615b8304faf62cec38bb84502"
        },
        "date": 1785036196319,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.474,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 2.866,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.32,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 25,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.242,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 22.63,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.463,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2159.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.9,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 38.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 55.94,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.452,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4078.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 22.34,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 447.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.11,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 24.62,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4061.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 154.027,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 649.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.26,
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
          "id": "e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd",
          "message": "Issue-tracking scheme: triage labels, templates, release notes, public roadmap policy (#34)\n\n* chore(github): issue templates with auto-triage labels and release-notes config\n\nBug reports now open with bug + needs-triage applied automatically, and the\ntemplate points insurer-employed reporters at the private email intake from\nSECURITY.md. release.yml gives auto-generated release notes keyed off PR\nlabels (bug / enhancement / documentation), with ignore-for-release as the\nopt-out.\n\n* docs: public roadmap policy and bug-lifecycle trail\n\nDocuments the label lifecycle a reporter can watch (needs-triage -> confirmed\n-> pending-release -> released via milestone) and the placeholder-issue model\nfor larger features (roadmap + exploring/building/shipped), including the\ncomment-before-building note for contributors and a non-commitment disclaimer.",
          "timestamp": "2026-07-27T10:20:08+12:00",
          "tree_id": "069536837f93ad61d285546ce8eed09794dec759",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd"
        },
        "date": 1785105187969,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.845,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.076,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.356,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 22.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.323,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 20.57,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.479,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2087.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 25.503,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 39.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 53.24,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.5,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4000,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 21.481,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 465.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.59,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 33.931,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 2947.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 155.089,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 644.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 4.57,
            "unit": "x"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "1277725+mrmattwright@users.noreply.github.com"
          },
          "committer": {
            "name": "GitHub",
            "username": "web-flow",
            "email": "noreply@github.com"
          },
          "id": "e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd",
          "message": "Issue-tracking scheme: triage labels, templates, release notes, public roadmap policy (#34)\n\n* chore(github): issue templates with auto-triage labels and release-notes config\n\nBug reports now open with bug + needs-triage applied automatically, and the\ntemplate points insurer-employed reporters at the private email intake from\nSECURITY.md. release.yml gives auto-generated release notes keyed off PR\nlabels (bug / enhancement / documentation), with ignore-for-release as the\nopt-out.\n\n* docs: public roadmap policy and bug-lifecycle trail\n\nDocuments the label lifecycle a reporter can watch (needs-triage -> confirmed\n-> pending-release -> released via milestone) and the placeholder-issue model\nfor larger features (roadmap + exploring/building/shipped), including the\ncomment-before-building note for contributors and a non-commitment disclaimer.",
          "timestamp": "2026-07-26T22:20:08Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd"
        },
        "date": 1785133686003,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 4.022,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 4.12,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.331,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 24.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.07,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 21.36,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.703,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 1422.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 24.916,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 40.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 35.44,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.414,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4142.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 20.248,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 493.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.39,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 23.615,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4234.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 149.937,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 666.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.35,
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
          "id": "0fd6835f1968741dc6e09a2194d9ca85922449a0",
          "message": "Load the principles into agent context; make CI dependency resolution reproducible (#33) (#44)\n\n* docs(principles): load the north star into every agent session\n\nThe published principles (gaspatchio.dev/principles) lived only in the docs\nrepository. CLAUDE.md imported the AGENTS.md rule sets and nothing else, so\nneither a contributor nor a coding agent working in this repo ever saw the\npositions the framework actually takes — design decisions and bug triage were\nbeing argued without the thing they should be argued against.\n\nAdd PRINCIPLES.md as the in-repo copy (the published page stays canonical for\nwording) and import it from CLAUDE.md ahead of the rule sets. The seven\none-liners also go inline in AGENTS.md, so agents that do not follow links\nstill get the north star.\n\nTwo things the source document leaves implicit are made explicit here: the\nresolution of its central tension — be liberal about the shapes you accept, be\nstrict about the meanings you infer — and that\nref/21-kaizen/01-rails-inspired-principles.md is superseded where it conflicts,\nnotably its \"Magic That Makes Sense\" section, which \"Sharp knives, no magic\"\nrejects.\n\n.github/copilot-instructions.md is generated from AGENTS.md; regenerated.\n\n* ci(deps): track uv.lock and install with --locked (#33)\n\nCI resolved dev dependencies fresh on every run, so a pull request's result\ndepended on what PyPI had released that morning rather than on its own diff.\nOn 2026-07-25 ruff floated to 0.16.0 and its changed I001 behaviour failed\n~70 docstring-example tests on a PR that touched none of them, and would have\nfailed every later PR and push to main identically. The lockfile already\nexisted but was gitignored, so laptops were reproducible and CI was not — the\nworst arrangement, because it hid the problem locally.\n\nTrack bindings/python/uv.lock and install it with `uv sync --locked` at all\ntwelve sync sites. Eleven were still floating, including evals.yml, which runs\non every push to main. The ruff pin comment in bindings/python/pyproject.toml\nsaid \"no lockfile ships in this repo\"; that is no longer true, so it now\ndescribes what the pin is actually for.\n\nAlso add a repository-root pyproject.toml declaring the workspace boundary.\nWithout it uv walks up out of the repository looking for a workspace root and,\nin a local multi-repo checkout, resolves against sibling repositories — so\n`uv run` from the repository root failed with a dependency conflict belonging\nto another project entirely, which is the first thing AGENTS.md's bare\n`uv run` examples would hit. bindings/python is excluded rather than made a\nmember: as a member, uv relocates the environment and lockfile to the\nrepository root, orphaning the lockfile CI expects and forcing every\ncontributor into a full Rust rebuild. AGENTS.md now states the working\ndirectory instead of leaving it implied.\n\nVerified: 2644 passed, 8 skipped, 5 xfailed, 1 xpassed.\n\n* docs(ref): design for the v0.6.0 outstanding-issue batch\n\nTriage of the ten issues left open after #21-#30 merged: eight to fix, one\nalready done on this branch, one deferred. Every verdict is justified against\nPRINCIPLES.md by name, which is newly possible now that the principles load\nwith the repository rules.\n\nTwo verdicts depart from what the issues themselves propose, and the reasoning\nis recorded rather than left implicit:\n\n- #37 takes the targeted-error option over auto-wrapping bare strings as\n  literals. Auto-wrapping infers a meaning from a shape, which \"Sharp knives,\n  no magic\" forbids, and would silently change behaviour for anyone passing a\n  column name as a string.\n- #36 materialises `month` and `proj_year`, not `year`. A framework-owned\n  `year` column would collide with the calendar year that model points\n  routinely carry, and Gotcha #7 already names `proj_year` vs `year` as a\n  cause of silently-wrong stress scenarios — a fix that worsens a documented\n  trap is not a fix.\n\n#31 turned out to be narrower than \"wrong convention\": `extrapolation` is\nalready declared, defaulted, serialised across the plugin boundary, and read\nby nothing, and \"flat\" is simply applied in the wrong space for log_linear\nalone. The work is making a dead parameter live, with \"flat\" clamping the spot\nrate (coherent with linear/pchip) and \"forward\" available for market-consistent\nlong-tail discounting.\n\n#41 is deferred on capacity, not disagreement: an Excel-port path is a whole\nskill, and a bad one is worse than none.\n\n* docs(ref): drop the two-day window; every fix ships in v0.6.0\n\nThe batch was originally scoped to a two-day window, which forced a\npre-designated item to drop if the estimate proved optimistic (#39, error\nattribution). That constraint is lifted: the release is cut when the work is\ndone rather than to a date, so nothing is expendable.\n\n#39 stays last in the order, but for a different reason — it is the one item\nwhose cost cannot be estimated before starting, so it belongs off the critical\npath rather than at the front of it. PRs 1 and 2 also touch surfaces that 3-5\nbuild on (the AGENTS.md examples, the lookup error path), so landing them first\nmeans the harder work rebases onto corrected foundations.\n\nThe accepted trade-off is now recorded as a risk rather than left implicit: two\nbreaking changes (#24, #28) stay unreleased for longer, mitigated by telling\nthe field reporter directly what is coming and what it changes.\n\n* docs(ref): implementation plan for the v0.6.0 issue batch\n\nTwelve tasks across five pull requests, each with the failing test written\nfirst, the exact command to run it, and the implementation to make it pass.\nFile paths and signatures were verified against the tree rather than assumed:\nthe proxy dunders delegate to a dispatch method (so __neg__ is self.mul(-1.0)\nand inherits list shimming), the bare-string lookup key originates at\n_api.py:993, and projection.set's real signature is until=/until_value=/\nfrequency= rather than the projection_end_* names the docs still show.\n\nTwo steps deliberately direct the implementer to read code before writing:\nlocating the describe() raise from its traceback, and reading the replay\nmachinery before attempting collect-time attribution. Inventing call sites\nthat cannot be verified would be worse than pointing at the evidence.\n\n* fix(deps): bump pyasn1 to 0.6.4; document the pymdown-extensions exception\n\nTracking bindings/python/uv.lock gave the PR scanner a Python lockfile to read\nfor the first time. It reported six advisories across two packages as\n\"introduced\" by that commit — the scan of main returned an empty result set\nbecause there was nothing to scan. The risk was not new, only unmeasured,\nwhich is the argument for tracking the lockfile rather than against it.\n\npyasn1 0.6.3 -> 0.6.4 clears PYSEC-2026-3455/3456/3457, GHSA-8ppf-4f7h-5ppj\nand GHSA-hm4w-wwcw-mr6r outright — remediation by lockfile bump, as this\nfile's own policy prefers.\n\nGHSA-9xwg-3r6f-jcx2 (pymdown-extensions path traversal in the b64 extension)\ncannot be remediated: the fix is 11.0.0 and marimo 0.23.13 pins\npymdown-extensions>=10.21.2,<11. It is recorded as an exception with its\nreachability stated — the package arrives through the optional `recipes`\nextra so it is absent from the published wheel's runtime closure, and\nexploitation needs the b64 extension enabled over attacker-controlled\nmarkdown, which gaspatchio never renders.\n\nVerified: uv lock --check and uv sync --locked exit 0; 2644 passed, 8 skipped,\n5 xfailed, 1 xpassed.\n\n* ci(security): apply osv-scanner.toml to every scanned lockfile\n\nosv-scanner resolves its config relative to each scanned file's own directory,\nso the root osv-scanner.toml governed Cargo.lock but never\nbindings/python/uv.lock. The GHSA-9xwg-3r6f-jcx2 exception added in the\nprevious commit was therefore inert — the scanner reported it under \"unused\nignores\" while still failing on the very advisory it named.\n\nPassing --config makes the one file authoritative for every lockfile, which\nkeeps a single reviewed exception list rather than scattering a second\nosv-scanner.toml into bindings/python.\n\nVerified locally against the real scanner image (ghcr.io/google/osv-scanner\n:v2.3.8, the version the workflow pins): without the flag it reports\nGHSA-9xwg-3r6f-jcx2 and lists the ignore as unused; with it, \"9 vulnerabilities\nfiltered, No issues found\".",
          "timestamp": "2026-07-29T11:42:06+12:00",
          "tree_id": "a9d5a2701820f06e59b432ffbdeb1fd7d5d86555",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0fd6835f1968741dc6e09a2194d9ca85922449a0"
        },
        "date": 1785282873180,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 3.847,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.259,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.444,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 18,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 7.236,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 16.3,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.444,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2252.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 24.072,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 41.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 54.22,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.351,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4253.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 20.619,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 485,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 8.77,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 24.511,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4079.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 153.325,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 652.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.26,
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
          "id": "0863a9ce7464d48d7566ddcd787257d40f98509b",
          "message": "Papercuts: unary negation, stale quickstart, describe on list columns, timing signpost (#45)\n\n* fix(column): support unary negation on list columns (#38)\n\n`-af.some_list_column` raised \"neg operation not supported for dtype\nlist[f64]\" while `0.0 - col` and `col * -1.0` both worked, as did `.abs()`,\n`.floor()`, casts and `** 2`. Both proxies define the full arithmetic dunder\nset but omitted `__neg__`, so Python fell through to Polars' native `neg`,\nwhich has no list kernel.\n\nNegation now multiplies by -1 through the same dispatch method the other\noperators use, so it inherits list-column shimming rather than reimplementing\nit. Added to ColumnProxy and ExpressionProxy alike — the second matters because\n`-(af.col * 2.0)` negates an expression, not a column.\n\n* docs: correct the removed projection API and make the quickstart executable (#35)\n\nAGENTS.md is auto-loaded by every agent session, so its quickstart calling\n`af.date.create_projection_timeline(...)` — removed some releases ago — made\nevery downstream session start from a false premise. The parameter names had\ndrifted too, so Gotcha #2's `projection_end_value=99` was stale in the same\nway.\n\nThe sweep found four more occurrences beyond the two known ones:\n\n- skills/gaspatchio-model-building/references/mortality-tables.md\n- schedule/_schedule.py, whose docstring pointed at\n  `date.create_timeline(projection_end_value=N)`. That method does still\n  exist, but takes (start_col, end_col, freq, ...) and has never had that\n  parameter, so the reference was wrong in a way that reads as correct.\n- errors/constants.py, whose projection-end reference set predates\n  `next_anniversary` being accepted.\n\nCorrecting prose fixes today and drifts again next release, so the documented\nshape is now executed by a test, together with an assertion that the removed\nentry point stays removed.\n\n* fix(cli): describe parquet files containing list columns (#40)\n\n`gspio describe` on a file with a list<f64> column printed \"Unsupported key\ntype for array storage: List(Float64)\" and logged an ERROR, because it fed\nevery file through assumption-table detection. Reading back a run's own output\nis what the CLI's agent workflow instructs, so the documented happy path was\nthe one that misbehaved.\n\nList columns are now partitioned out before table-structure detection and\nsummarised on their own terms — inner dtype and length range. A file carrying\nthem is projection output, so describe says so and stops, rather than\nsuggesting a Table() constructor that cannot run against it. The printed\nexample now shows how to read the file back and explode a period column.\n\nTwo further problems surfaced while fixing it:\n\n- The --json payload reported list columns inside detected_dimensions, so an\n  agent following the documented workflow would have tried to key a lookup on\n  a per-period column. They now have their own `list_columns` field and are\n  excluded from the dimension analysis.\n- A frame of nothing but list columns reached value-column detection with no\n  columns left; that case now short-circuits.\n\n* docs: signpost timing conventions in the top-level guide (#42)\n\nprospective_value's beginning/end-of-period semantics were documented only in\nits docstring, so the read-AGENTS-first path could miss that timing is a choice\nat all.\n\nTwo things made this worth more than a cross-reference. The defaults are\nopposite — prospective_value defaults to end_of_period while\ncumulative_survival's rate_timing defaults to beginning_of_period — and with\nconstant rates both conventions give identical answers, so a wrong choice\nsurvives testing and only diverges once rates vary at age boundaries or on a\nreal curve. Both are now stated in a table, with the discount-factor anchoring\ncontract from #28 alongside: passing discount_factor= rather than\ndiscount_rate= means the factors must share the convention you asked for, and\nunder per-period rates the two are not a single multiplication apart.\n\nDefaults were read from accessors/projection.py rather than from `gspio docs`,\nwhose index is currently stale.\n\n* fix(cli): three defects in the list-column describe path (#40)\n\nAll three found in review, all three confirmed by reproducing them before\nfixing. Each had slipped through because the original tests only ever\nexercised a file with ONE list column, only checked the text path for an\nall-list file, and never passed --value-column at all.\n\n1. The generated example was broken for more than one list column.\n   `pl.col(\"a\", \"b\").list.len().alias(\"n_periods\")` expands to two outputs\n   sharing a name and raises DuplicateError, so the snippet printed for any\n   real projection output did not run. Each column now gets its own alias.\n   This is the defect #35 exists to prevent, shipped in the commit that fixes\n   #35.\n\n2. `--json` on a file of nothing but list columns reported a value column\n   named \"rate\" that appears nowhere in the file, and suggested code\n   referencing it. analyze_table falls back to that default on an empty\n   frame; the short-circuit added earlier covered only the text path. With no\n   scalar columns the file cannot be an assumption table, so the value column\n   is empty and the suggested code reads the parquet back instead.\n\n3. `--value-column` naming a list column was validated against the full frame\n   and accepted, then reported as an assumption-table value. It is now\n   rejected with an error naming the scalar columns that are available.\n\nEach fix ships a test verified to fail against the previous commit.\n\n* fix: address self-review findings across the papercuts batch (#38, #35, #40)\n\nFourteen findings, all in this branch's own changes. Each was reproduced\nbefore being fixed.\n\nThe serious one is #38's. `__neg__` was implemented as `mul(-1.0)`, which\nsilently widened Int64 to Float64 (and List(Int64) to List(Float64)) where\n`0 - col` had always preserved the dtype. A negated duration could no longer\nkey an integer assumption table. `mul(-1)` preserves it; a dtype assertion now\npins that. `__neg__` was also missing from _BaseProxy in proxy.pyi, so `-col`\nremained a pyright error for every user with type checking on — the fix was\ninvisible to exactly the audience that reported it.\n\n#40's list-column handling had been threaded through describe as six\nindependent special cases, and the console and JSON modes had already drifted\napart as a result. Replaced with one classification (_partition_nested_columns)\nand one shared example generator, which removes four symptoms by construction:\n\n- Array and Struct columns still reproduced the original bug verbatim;\n  is_nested() covers what isinstance(dtype, pl.List) missed, and gaspatchio's\n  own rollforward machinery puts Struct columns in frames.\n- --json still fabricated a \"rate\" value column for the realistic shape (a\n  scalar policy id alongside list columns); the previous guard only caught\n  files that were entirely lists, which no real output is.\n- sample_rows dumped whole per-period lists: a 10-column x 1200-period file\n  produced ~900 KB of JSON, destroying the context of the agent that follows\n  the documented workflow. Now 2.9 KB.\n- The printed example was not runnable for more than one list column\n  (duplicate alias) nor when the resolved path made Rich wrap it mid-statement.\n- A zero-column parquet raised IndexError; --value-column naming a scalar on a\n  mixed file silently dropped the Table example the user had asked for; the\n  console printed a value column before disclaiming it applied.\n\n#35's fix stopped one line short. Phase 1 creates `issue_age` and Phase 3 read\n`af.age`, so the documented model still failed immediately after the corrected\ncall — and looking up on a scalar age yields one rate with nothing for\ncumulative_survival() to accumulate. Phase 3 now derives attained age and the\ntest executes the whole three-phase shape rather than the single line that had\nbeen reported. Writing it surfaced a real gotcha, now documented: maximum_age\nsizes one grid from the youngest life, so a 55-year-old reaches attained age\n115 and the lookup raises.\n\nAlso: errors/constants.py carried a \"keep in sync\" comment naming an invariant\nnothing enforced, which is how it drifted; a test now asserts it against the\nLiteral. pyright on cli.py goes 6 errors to 0, ruff on tests/api 4 to 0.\n\nVerified: 2661 passed, 8 skipped, 5 xfailed, 1 xpassed; stubtest clean across\n263 modules; manifests regenerated with no drift.",
          "timestamp": "2026-07-29T17:19:04+12:00",
          "tree_id": "ff70a6817a9091f43e02033b2265ed37dc3b955a",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0863a9ce7464d48d7566ddcd787257d40f98509b"
        },
        "date": 1785303057797,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 17.246,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 3.539,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.291,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 27.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 6.082,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 20.9,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.365,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2739.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 19.9,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 50.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 54.52,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 1.732,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 5773.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.94,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 590.3,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 9.78,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 16.58,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 6031.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 135.209,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 739.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 8.15,
            "unit": "x"
          }
        ]
      }
    ]
  }
}