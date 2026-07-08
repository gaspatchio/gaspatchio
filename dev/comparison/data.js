window.BENCHMARK_DATA = {
  "lastUpdate": 1783486391881,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Gaspatchio vs Lifelib": [
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
        "date": 1783393551815,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.857,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.575,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.145,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 55.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 4.935,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 34.03,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.349,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2865.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 15.834,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 63.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 45.37,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 1.745,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 5730.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 13.029,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 767.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.47,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 16.283,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 6141.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 98.874,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 1011.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 6.07,
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
        "date": 1783395096498,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.626,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.733,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.179,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 44.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.738,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 32.06,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.416,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2403.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.163,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 49.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 48.47,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.299,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4349.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.172,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 618.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.03,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.638,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4621.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 118.629,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 843,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.48,
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
        "date": 1783418926070,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.65,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.685,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.167,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 47.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.923,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 35.47,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.414,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2415.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.155,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 49.6,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 48.68,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.296,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4355.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.208,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 617,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.06,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.585,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4632.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 118.844,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 841.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.51,
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
        "date": 1783459908059,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.621,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.707,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.169,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 47.3,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.783,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 34.22,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.42,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2381,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.216,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 49.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 48.13,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.354,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4248.1,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.24,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 615.8,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 6.9,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.864,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4573.7,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 119.195,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 839,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.45,
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
        "date": 1783464238979,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.594,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.71,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.172,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 46.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.665,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 32.94,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.417,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2398.1,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 19.975,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 50.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 47.9,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.297,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4353.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.064,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 622.5,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 6.99,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.566,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4636.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 119.801,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 834.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.56,
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
        "date": 1783465559083,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.7,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.747,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.176,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 45.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.917,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 33.62,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.428,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2336.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.974,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 47.7,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 49,
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
            "value": 16.978,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 589,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.25,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.925,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4561,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 119.553,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 836.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.45,
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
        "date": 1783469719856,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.614,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.68,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.172,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 46.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.696,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 33.12,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.42,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2381,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.012,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 50,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 47.65,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.346,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4262.6,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.028,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 623.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 6.83,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 22.001,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4545.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 118.484,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 844,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.39,
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
        "date": 1783474802744,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.626,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.71,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.165,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 48.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.731,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 34.73,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.426,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2347.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.469,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 48.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 48.05,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.283,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4380.2,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.201,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 617.2,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.1,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.228,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4710.8,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 120.034,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 833.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.65,
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
        "date": 1783486391518,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "gaspatchio-setup",
            "value": 1.634,
            "unit": "seconds"
          },
          {
            "name": "lifelib-setup",
            "value": 1.719,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-points",
            "value": 0.184,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/8-throughput",
            "value": 43.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/8-points",
            "value": 5.852,
            "unit": "seconds"
          },
          {
            "name": "lifelib/8-throughput",
            "value": 1.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/8",
            "value": 31.8,
            "unit": "x"
          },
          {
            "name": "gaspatchio/1K-points",
            "value": 0.433,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/1K-throughput",
            "value": 2309.5,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/1K-points",
            "value": 20.45,
            "unit": "seconds"
          },
          {
            "name": "lifelib/1K-throughput",
            "value": 48.9,
            "unit": "points/sec"
          },
          {
            "name": "speedup/1K",
            "value": 47.23,
            "unit": "x"
          },
          {
            "name": "gaspatchio/10K-points",
            "value": 2.358,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/10K-throughput",
            "value": 4240.9,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/10K-points",
            "value": 16.609,
            "unit": "seconds"
          },
          {
            "name": "lifelib/10K-throughput",
            "value": 602.1,
            "unit": "points/sec"
          },
          {
            "name": "speedup/10K",
            "value": 7.04,
            "unit": "x"
          },
          {
            "name": "gaspatchio/100K-points",
            "value": 21.88,
            "unit": "seconds"
          },
          {
            "name": "gaspatchio/100K-throughput",
            "value": 4570.4,
            "unit": "points/sec"
          },
          {
            "name": "lifelib/100K-points",
            "value": 118.569,
            "unit": "seconds"
          },
          {
            "name": "lifelib/100K-throughput",
            "value": 843.4,
            "unit": "points/sec"
          },
          {
            "name": "speedup/100K",
            "value": 5.42,
            "unit": "x"
          }
        ]
      }
    ]
  }
}