window.BENCHMARK_DATA = {
  "lastUpdate": 1787462607791,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Scenario Benchmarks (Windows)": [
      {
        "commit": {
          "author": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "committer": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "id": "2a761959f16118a54710c92dcaefbe319aad46d1",
          "message": "ci(evals): give Criterion Windows headroom (40m timeout + rust-cache)\n\nThe Criterion benchmark job timed out at 20 minutes on the free\nwindows-latest runner: an uncached cargo bench compiles polars +\ncriterion from scratch, which exceeds 20m on Windows (Linux fits).\nGitHub cancelled the job, so dev/bench-windows never populated.\n\nBump the job timeout to 40m and add Swatinem/rust-cache. Only compiled\ndependencies are cached; the bench crate is rebuilt and run fresh each\ntime, so measured numbers stay accurate while warm builds land well\ninside the window.",
          "timestamp": "2026-07-07T03:22:29Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/2a761959f16118a54710c92dcaefbe319aad46d1"
        },
        "date": 1783398003452,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.386,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 162.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2953.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.087,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 4411.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3323.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 509.459,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 986.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1962.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.528,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 308.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4645,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 260.725,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 11226.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3835.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "0d479c24928f2489239063e39a27f2ec73d5ff71",
          "message": "fix(scenarios): gate auto-search probes so measuring a batch can never OOM the box (#8)\n\nfor_each_scenario(batch_size=\"auto\") resolved batch size by running each\nladder rung and checking the memory budget only after the probe returned.\nA probe larger than physical memory dies mid-collect() -- before its peak\nis recorded and before any back-off logic can run -- so the search itself\ncould kill the process (or the whole runner). Observed on the CI scenario\nbenchmark's 10-scenario x 100K-policy cell: b=1 measured 3.1 GB and fit,\nthen the b=4 streaming probe demanded ~11.5 GB on a 16 GB runner\n(Windows measured 11,226 MB on the same cell and survived only because\nits pagefile absorbed the spike). Reproduced under a 4 GB cgroup:\nkernel OOMKilled=true during probe #2, no clean error.\n\nGate every rung after the first by linear extrapolation from the last\nmeasured rung (peak grows at most linearly in batch for the scenario\ncross-join; measured ratios were 3.0-3.7x, so the prediction\nover-estimates). A rung whose predicted peak already fails the fits test\ncould never be selected, so probing it pays an unbounded memory cost for\nzero information. With the gate, the same 4 GB container cell completes\nin 7.5 s at batch=1 instead of being killed; runs that previously paid a\ndoomed probe get faster as well as safe.\n\nNo new constants: the gate reuses the measured peak, the actual batch\nratio, and the existing safety_margin/budget. Residual risk documented:\nthe first rung (streaming b=1) has no prior to predict from.\n\nIrreducibleCellError's contract ('fails loudly ... rather than being\nOOM-killed by the kernel mid-collect()') now holds on the probe path.",
          "timestamp": "2026-07-07T09:59:48Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0d479c24928f2489239063e39a27f2ec73d5ff71"
        },
        "date": 1783419692927,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.792,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 165.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2637.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.035,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 1901.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3329.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 499.293,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 3364.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2002.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.423,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 389.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4269.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 221.572,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5484.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4513.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "346d4662b985d7a4a128252ba7c83d468ed010a0",
          "message": "fix(scenarios): probe gate predicts super-linear streaming cross-join peaks (#10)\n\nThe gate from the previous fix extrapolated a rung's peak linearly in\nbatch size from the last measured rung. Field falsification on the CI\n10sc x 100K cell: b=1 measured ~1.3 GB on the 4-core runner, so a linear\nprediction put b=4 within the 7.7 GB budget -- but the actual b=4 demand\nwas ~11.5 GB (8.6x the b=1 rung, 2.2x ABOVE linear; the Polars #20786\ncross-join inflation is super-linear in batch at high policy counts) and\nthe probe killed the runner again. Locally-measured 1K-10K ratios\n(3.0-3.7x, sub-linear) do not extrapolate to 100K: the scaling law\nitself changes with scale.\n\nMultiply the gate's linear prediction by streaming_batch_inflation\n(3.0, a named SizingDefaults constant chosen above the worst observed\n2.2x excess). Checked against every measured cell: 1K/10K cells keep\ntheir current batch choices; the 100K killer rung is now gated; the one\nbehavioral downgrade is 1000sc x 1K picking b=16 over b=64 (~8% slower)\n-- reliability over peak throughput. Over-predicting costs at most a\nsmaller batch; under-predicting costs the process.\n\nNew test pins the factor: a budget that a bare-linear gate would pass\n(100 MB peak, 1 GB budget -> linear 520 MB) must still skip the b=4\nprobe (inflated 1560 MB).",
          "timestamp": "2026-07-07T21:21:41Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/346d4662b985d7a4a128252ba7c83d468ed010a0"
        },
        "date": 1783460576089,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.412,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 162.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2931.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.394,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 495.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3290.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 481.385,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 225.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2077.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.249,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 369.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4706,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 213.086,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5922.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4692.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "committer": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "id": "ec906df4330539df20b2913be4e9c199e4e1f1e8",
          "message": "ci(evals): run scenario benchmarks on every push to main\n\nThe scenario suite now completes reliably on free standard runners: the\nauto-search OOM chain is fixed (#8/#10/#11 gate + inflation + frame\nfloor) and the bench tolerates irreducible cells and isolates each cell\nin a fresh process (#9/#11). Validated on dispatch run 28903417786 --\nthe 10sc x 100K cell completes at batch=1 in 209s/6.5GB with the gate\nblocking the b=4 probe (probes: [b1/streaming=3198MB+fits] budget=7275MB).\n\nAdd push-to-main to the job's trigger so dev/scenario-bench{,-windows}\naccumulate a data point per merge, like the other benchmark suites.",
          "timestamp": "2026-07-07T22:56:32Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ec906df4330539df20b2913be4e9c199e4e1f1e8"
        },
        "date": 1783465107496,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.493,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 163.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2863,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 37.989,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 536,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2632.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 502.181,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 834.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1991.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.432,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 903.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4267.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 222.544,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6301.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4493.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783466320281,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.47,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 162.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2881.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.852,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 588.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3241.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 499.658,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 800.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2001.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.869,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 838.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4021,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 228.039,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5895.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4385.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783471795695,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.3,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 166.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3029.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.567,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 586.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3167.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.426,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 837,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4459.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 218.889,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5830.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4568.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783475559211,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.432,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 163.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2913.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.336,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 586.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3296.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 511.501,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 796.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1955,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.497,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 836.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4255.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 214.992,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6864.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4651.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783487864771,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.646,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 202.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2743.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.404,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 556.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3184.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1191.508,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 537.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 839.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.956,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 861,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4356.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 226.519,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4820.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4414.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783502332573,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.466,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 194.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2885.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 63.581,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 532.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 1572.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 511.242,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 576.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1956,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.766,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 859,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4207.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 229.439,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4814.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4358.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783923839084,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.689,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 212,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2710.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 35.855,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 535.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2789,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 858.573,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 545.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1164.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 20.518,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 892.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4873.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 182.367,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4866.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 5483.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1784529197694,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.692,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 193.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2131.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 39.723,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 544.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2517.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1220.469,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 543.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 819.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 29.651,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 853.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3372.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 256.236,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4799.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3902.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1785036572147,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.765,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 217.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2098.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.178,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 560.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3014.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 491.549,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 572,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2034.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.124,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 864.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4520.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 220.936,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4753.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4526.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1785106444818,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.582,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 198.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2791.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 38.859,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 547.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2573.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1201.773,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 546,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 832.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 30.055,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 873.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3327.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 229.115,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4893.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4364.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1785134270884,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.45,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 206.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2898.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.672,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 574.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3157.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 507.75,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 589.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1969.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.118,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 920.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4521.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 219.171,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4861.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4562.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1785283462605,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.456,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 209.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2893.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 38.449,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 546.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2600.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 512.304,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 594.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1952,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 26.76,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 861.2,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3736.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 238.666,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4825,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4190,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1785303690200,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.665,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 206.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2728.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.568,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 564.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3167.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 532.894,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 580.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1876.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.813,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 880.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4199.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 234.6,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4810.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4262.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "ab1081f7463237dbfbd4eca563452cc313cdc0c5",
          "message": "Lookup: a bare string is the value (VLOOKUP semantics) (#46)\n\n* fix(assumptions): name both remedies for a bare-string lookup key (#37)\n\n`tbl.lookup(product=\"annuity\", age=af.age)` routed the string to `pl.col(...)`,\nso it was read as a column name and failed with \"Column 'annuity' not found.\nDid you mean...\" — pointing away from the actual mistake, and listing the\nframe's columns as candidates, which points further away still.\n\nThe issue offered two options; this takes the second deliberately. Auto-wrapping\na bare string as a literal infers a meaning from a shape, which \"Sharp knives,\nno magic\" forbids, and would silently change behaviour for anyone legitimately\npassing a column name as a string. Strings keep their Polars meaning; the error\nnames both readings and lets the caller say which they meant.\n\nThe error also arrives earlier than planned. Any ColumnProxy among the\ndimension values carries its parent frame, so the bare strings can be checked\nagainst the real schema at the lookup() call site rather than several lazy\nsteps later at collect(). With no proxy among the values there is no schema to\ncheck and the deferred error stands — no behaviour invented where there is no\ninformation to base it on.\n\nThe proxy check is duck-typed rather than an isinstance: ColumnProxy is\nannotation-only in this module and importing it at runtime would be circular.\nThat matches how the same function already recognises proxies a few lines down.\n\nVerified: 2652 passed, 8 skipped, 5 xfailed; ruff clean on both files; pyright\nunchanged from baseline (8 pre-existing errors in _api.py, none added).\n\n* feat(assumptions)!: a bare-string lookup key is the value, not a column (#37)\n\n`lookup(product=\"annuity\", age=af.age)` read the string as a COLUMN name\n(Polars convention), failed with \"Column 'annuity' not found\", and the only\nway to express the value was pl.lit(\"annuity\") — Polars leaking into the most\nordinary actuarial operation there is. VLOOKUP semantics are what an actuary\nmeans by that line, and the framework's own older design docs already wrote\nlookups that way (sex=\"M\", scalar_id=\"mort\").\n\nA bare string now means the value. Columns are referenced the gaspatchio way —\naf.product, af[\"product\"] — or pl.col(\"product\") for those who want Polars.\n\nThis replaces the targeted-error approach from the previous commit, and\ndeletes it: with no bare-string-as-column path there is no eager schema check,\nso its cross-frame false positive and its wrong-diagnosis-before-dimension-\nvalidation orderings (both found in review) cease to exist rather than\nneeding fixes, and string values travel as data rather than being interpolated\ninto suggested code.\n\nBREAKING, but safely so: a caller who relied on string-as-column now gets a\nlookup MISS, and since #24 misses raise by default naming the key that missed.\nThe old behaviour failed loudly too — it just blamed the wrong thing. The two\ninternal tests that used string-as-column only asserted isinstance(expr,\npl.Expr) and still pass.\n\nVerified: 256 assumption tests pass, including the #17/#22/#30 regression\nsuites on this same code path.\n\n* docs: bare-string lookup keys are values — state it in the always-loaded contract (#37)",
          "timestamp": "2026-07-30T23:15:02+12:00",
          "tree_id": "f0bc4329dfc18946ab686758027beb632b24b961",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ab1081f7463237dbfbd4eca563452cc313cdc0c5"
        },
        "date": 1785411599185,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.51,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 200.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2848.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.862,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 576.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3138.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 507.515,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 575.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1970.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.529,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 889.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4250,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 225.241,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4881.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4439.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "e5a78c1d20883d12557812713c878eb1628343af",
          "message": "fix(curves)!: clamp log_linear extrapolation in rate space; make the extrapolation parameter live (#48)\n\n* fix(curves)!: clamp log_linear extrapolation in rate space and make the extrapolation parameter live\n\nlog_linear interpolates log-discount-factors, and outside the knot range\nthe kernel clamped the log-DF LEVEL. Holding a level constant stops the\ndiscount factor decaying: a flat 5% curve returned ~1.64% at 30y (a\n30-year cashflow carried at ~2.7x its true value), and below the first\nknot the same clamp read 5%@5y as 27.6% at t=1, diverging as t -> 0.\nThe extrapolation kwarg was declared, defaulted, serialised across the\nplugin boundary — and read by nothing.\n\nNow \"flat\" (the default) holds the boundary knot's spot rate in both\ndirections, matching what flat has always meant for linear/pchip whose\nknots ARE rates. \"forward\" extends the last segment's forward rate, the\nmarket-consistent choice for long-tail discounting; it requires\nlog_linear, and rate-space methods reject it rather than ignoring it.\nUnknown modes error at Curve construction, not at collect().\n\nThe eager Python path (log_linear_spot) had the identical defect and is\nfixed with the identical arithmetic; parity between the two paths is\nasserted across tenors and modes. canonical_form() includes\nextrapolation only when non-default, so every existing curve keeps its\nsource_sha() while a \"forward\" curve stamps differently — audit by\ndefault, without invalidating shas that predate the parameter working.\n\nBREAKING: models discounting beyond the last knot (or before the first)\nwith a log_linear curve produced overstated present values; re-run\nreconciliations after upgrading. See CHANGELOG.\n\n* fix(curves): preserve extrapolation through shifts; validate on every construction path\n\nTwo review findings, both real. The shift helpers rebuilt curves with a\nhand-written field list that omitted extrapolation (and parametric), so\na parallel- or key-rate-shifted \"forward\" curve silently became \"flat\"\n— the stressed valuation flattened its long tail while the base run\nstayed correct, which is precisely the silent divergence #31 exists to\nkill. They now rebuild with dataclasses.replace, which carries every\nfield by construction, present and future.\n\nValidation moves from the from_zero_rates call site into __post_init__:\nclassmethods, direct Curve(...) construction, and replace() all funnel\nthrough it, so an invalid interpolation/extrapolation pair can no\nlonger produce a live curve that fails (or silently evaluates flat)\nonly at collect time.\n\nRegression tests verified to fail against the previous commit.",
          "timestamp": "2026-07-31T13:16:11+12:00",
          "tree_id": "7aac2aea156cdcda930b35ac08027ee350b0d402",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e5a78c1d20883d12557812713c878eb1628343af"
        },
        "date": 1785461963171,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.731,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 213.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2680.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 41.588,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 563.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2404.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 534.179,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 580.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1872,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.042,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 908.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4339.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 226.323,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4843.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4418.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "ac747daec774a4fbaa292cd03c716d9afe826d00",
          "message": "Errors: attribute collect-time failures to the assigned column (#49)\n\n* feat(errors): name the offending column in collect-time failures (#39)\n\nA lazy chain failing at collect() surfaced the raw Polars error — e.g.\n\"ShapeError: list lengths differed at index 0: 6 != 3\" — with no clue\nwhich assigned column produced it: a long hunt in a 50-column model.\nThe bisect-replay machinery to attribute it (ErrorBoundaryFinder) has\nexisted since #18, but the graph it replays was only recorded under\ntraced debug runs, so in every normal run it had nothing to work with.\n\nEvery assignment is now recorded as a bare (name, expr) tuple — no\nstack inspection, unlike the traced path, because the setter is the\nmodel-build hot path. When a ShapeError, InvalidOperationError or\nSchemaError reaches the collect() boundary, the recorded assignments\nreplay against the pristine pre-assignment baseline until one\nreproduces the error class; the message then ends with the column name\nand its defining expression. Audit by default: the lineage the\nprinciples promise now reaches the error path.\n\nThe fallback contract is the safety property: on ANY ambiguity — empty\ngraph, replay that does not reproduce, failure inside the replay — the\noriginal error passes through byte-for-byte. A wrong column name costs\nmore than no column name. Structural operations (filter/join/select/\nrename/drop/sort) are not recorded, so they restart the recording\nwindow rather than risk replaying against a stale baseline.\n\ncalc-graph export ignores the bare tuples (no metadata) and still\ndemands a debug-mode run; two tests that asserted \"non-traced graphs\nstay empty\" now assert the property they actually protected — no\nTracedOperation metadata capture outside tracing.\n\n* fix(errors): harden collect-time attribution against fifteen review findings\n\nA full adversarial review of the #39 commit surfaced fifteen defects, six\nempirically reproduced. The worst was a regression of the most common\nerror path: the always-populated graph routed ordinary missing-column\nerrors into the enhanced compilation path, whose builder crashed on the\nbare tuples and re-raised the RAW Polars error — losing the friendly\ndid-you-mean panel for a simple misspelling. The compilation path now\nrequires TracedOperation records, and tuple-only graphs keep the basic\nformatting they always had.\n\nSoundness — the \"wrong name costs more than no name\" contract:\n- Traced graphs survive structural ops (calc-graph export needs them,\n  even after the decorator restores tracing off) but are marked UNSOUND;\n  both attribution and the enhanced replay refuse a graph whose baseline\n  no longer matches the live plan.\n- Multi-expression with_columns batches restart the window: every\n  expression sees the pre-batch frame live, but replay is sequential,\n  so a sibling-shadowing batch could blame a healthy column.\n- The exact-failure scan starts strictly after the known-good prefix;\n  it used to start one op early and double-apply, blaming a valid\n  self-referential dtype-changing assignment for another column's error.\n- Attribution requires the replayed error's leading message to match the\n  original, not just its class — no more pairing column A's name with\n  column B's error text.\n- Rollforward hidden-column injection is recorded (non-traced) or marks\n  the window unsound (traced) instead of silently desynchronising it.\n- Tuples are recorded AFTER the successful apply — a rejected expression\n  leaves no phantom op.\n\nCost and lifecycle:\n- Replay baselines are row-capped: diagnosis stays fast at scale, and an\n  error past the cap yields no attribution rather than a slow one.\n- A successful collect() closes the window, bounding graph growth on\n  long-lived frames and scoping replay to ops since the last success.\n- Plan logging under show_query_plan fires only for traced records,\n  restoring the pre-#39 optimize-mode behaviour.\n- AF_ERROR_MODE=off/basic disables attribution even on debug frames;\n  already-formatted exceptions are never decorated twice.\n\nCoverage:\n- run_to_parquet / run_aggregated route batch-collect failures through\n  the boundary, so the reported at-scale pain case gets the column name.\n- calc-graph export no longer misclassifies tuple-recorded columns as\n  raw model-point inputs.\n- util/__init__.pyi gains get_error_mode/set_error_mode, clearing two\n  pre-existing stubtest errors.\n\nEight new regression tests, one per reproduced finding class.",
          "timestamp": "2026-07-31T13:49:26+12:00",
          "tree_id": "b02ad59b0b73edad9176edd2a175b1d66e2fcf66",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ac747daec774a4fbaa292cd03c716d9afe826d00"
        },
        "date": 1785463916091,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.855,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 209.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2594,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 40.208,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 545.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2487.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 531.259,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 578.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1882.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 25.399,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 888.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3937.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 234.384,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4834.2,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4266.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "f2798f944a917802b31bef561bdbc8cdeae284c9",
          "message": "release: v0.6.0 — silent wrong numbers become loud errors (#50)\n\n* docs(changelog): record the full batch since v0.5.3 — every shipped fix has an entry\n\nOnly #14, #48 and #49 wrote CHANGELOG entries as they merged; the other\nthirteen commits since v0.5.3 — the audit/field-report P0 runs (#16–#19,\n#32) and the triage batch (#44–#47) — shipped without a record. Release\nnotes derive from this file, so the gap had to close before tagging.\n\nAdds Breaking entries for on_missing=\"raise\" (#24), varying-rate\nprospective_value (#28), the bare-string lookup flip (#37) and the month\nperiod index (#36) alongside the existing #31; Fixed entries for\n#21–#23, #25–#27, #29, #30, #38, #40; and Documentation, Infrastructure\nand Security sections. Every entry names its issue and every breaking\nentry carries an Action line, per the release-notes policy from #34.\n\n* release: v0.6.0",
          "timestamp": "2026-07-31T14:34:48+12:00",
          "tree_id": "6cfa274dc2633fdc6798b3e65e4a0e983d4a4704",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/f2798f944a917802b31bef561bdbc8cdeae284c9"
        },
        "date": 1785466684228,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.719,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 213.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2689.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 32.073,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 555.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3117.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 567.701,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 574.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1761.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.872,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 897.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4020.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 227.269,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4837.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4400.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "eff3bbd7a86499d2be370fa8d702df7504a15ed9",
          "message": "ci: dispatch a RAG rebuild to gaspatchio-mix when bindings change on main (#51)\n\n* ci: dispatch a RAG rebuild to gaspatchio-mix when bindings change on main\n\nThe gspio docs/knowledge index only rebuilt when the docs repo pushed;\ncore docstring changes never refreshed it, so the retrieval surface —\nLLM-shaped from the inside out is the principle at stake — served stale\nanswers between docs releases. Mirrors the docs repo's trigger workflow.\nGated on the RAG_DISPATCH_ENABLED variable so the job skips (rather than\nfails) until the MIX_DISPATCH_PAT secret exists.\n\n* ci: pin repository-dispatch to a full commit SHA\n\nThe step hands MIX_DISPATCH_PAT (contents read/write on\nopioinc/gaspatchio-mix) to the action, so a retargeted mutable tag could\nexfiltrate it. Pinning to the reviewed v4.0.1 commit matches how the other\ncredential-touching steps (pypi-publish, sbom-action) are already pinned.\n\nRaised by Greptile on #51.",
          "timestamp": "2026-08-01T11:11:08+12:00",
          "tree_id": "8f9c0de4294b4442b40bc357225d60bf299a969f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/eff3bbd7a86499d2be370fa8d702df7504a15ed9"
        },
        "date": 1785541505422,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.251,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 210.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2352.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 35.325,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 561.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2830.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1238.053,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 541,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 807.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.528,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 870,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4250.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 229.51,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4826.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4357.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "8867b66ac2f6c7d1999960d614ec9628f4bacd52",
          "message": "String outputs on the list-broadcast when() path + broadcast_to_periods() (GSP-110) (#56)",
          "timestamp": "2026-08-02T08:45:33+12:00",
          "tree_id": "ff15490624e77256faeb9c60872ba34850e022fb",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/8867b66ac2f6c7d1999960d614ec9628f4bacd52"
        },
        "date": 1785618447160,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.874,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 215.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2581.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 32.683,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 567.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3059.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 514.642,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 580.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1943.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.888,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 872.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4369.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 225.509,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4824.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4434.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "6487cea894cc04e942556c716fd678b8a9147b19",
          "message": "release: v0.7.0 — book shapes are declared, and conditionals speak strings (#57)",
          "timestamp": "2026-08-02T09:22:50+12:00",
          "tree_id": "49369f9e567c54ab72901163229492273a754257",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/6487cea894cc04e942556c716fd678b8a9147b19"
        },
        "date": 1785620704844,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.519,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 213.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2842,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 31.823,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 559.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3142.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 531.514,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 586.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1881.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.672,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 887.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4053.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 227.657,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4829.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4392.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "5fbf6bb863062eeb502644c917716c01bcf12912",
          "message": "fix(errors): attribute plan-lowering panics through the collect boundary (#54) (#59)\n\nA schema mismatch inside a when().then() branch fails during IR plan\nlowering, where polars panics ('no valid schema can be derived') instead\nof raising a typed error. pyo3 surfaces that as PanicException — a\nBaseException subclass — which sailed past both 'except Exception' at the\ncollect()/profile() boundary and the #39 attribution gate, reaching the\nmodel author as a bare Rust panic naming nothing. In the field this cost\na statement-level bisect of a ~500-line Solvency II model to localise one\nbad assignment.\n\nThe boundary now converts that panic into a catchable SchemaError\ncarrying the standard attribution block (failing column + defining\nexpression), chained to the original panic:\n\n- is_plan_lowering_panic() matches the panic narrowly (type name +\n  message) — pyo3_runtime is a synthetic module, so no import.\n- The replay probes catch BaseException, guarded so anything that is\n  neither an Exception nor this panic (interrupts, foreign panics)\n  re-raises immediately.\n- attribute_collect_failure() admits the panic alongside the existing\n  attributable error classes; replay matches it by class + leading\n  message like any other failure.\n- _handle_plan_lowering_panic() converts only when attribution succeeds;\n  an unattributed panic passes through untouched per the fallback\n  contract (never rewrite an error into something that merely looks\n  diagnosed).\n\nLLM-shaped from the inside out: plan-lowering panics were exactly the\nfailures that needed the named-column contract most, and the only ones\nthat bypassed it. Tests use raw pl.Expr branches so the repro stays\nfailing after #53 fixes proxy-built expressions.",
          "timestamp": "2026-08-02T18:14:03+12:00",
          "tree_id": "1d3a5ad0a7eab23bb4e246fe10e6ba4355a715e0",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5fbf6bb863062eeb502644c917716c01bcf12912"
        },
        "date": 1785652653630,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.088,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 209.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2445.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 38.713,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 563.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2583.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 546.878,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 584.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1828.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 22.246,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 890.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4495.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 227.465,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4811,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4396.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "45f40180e80b0fbfeee33d10075cd2f8fd40c78b",
          "message": "chore(deps): bump event-listener 5.4.1 -> 5.4.2 (RUSTSEC-2026-0221) (#58)\n\nTransitive via polars-stream -> async-channel. Affected versions\nunconditionally implement Send/Sync for the listener! macro's StackSlot,\nletting a !Send tag set via Event::with_tag cross threads — a data race\nin safe code. Practical exposure here is nil (async-channel uses untagged\nevents), but the advisory fails every push-to-main osv scan with\n--fail-on-vuln, so main has scanned red since 2026-08-01. Patch-level\ndrop-in; no other packages move.",
          "timestamp": "2026-08-02T18:51:46+12:00",
          "tree_id": "de7e8d0aa7db775a40f160594393d3142442bd81",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/45f40180e80b0fbfeee33d10075cd2f8fd40c78b"
        },
        "date": 1785654538258,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 2.704,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 228.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3697.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 24.794,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 558.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 4033.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 392.282,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 591.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2549.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 19.228,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 871.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 5200.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 174.832,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4862.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 5719.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "b63d7c1ab442e1bfac82cf0e912438aabf94e0f6",
          "message": "fix(column): make scalar/list broadcast order-independent for + and - (#53) (#60)\n\npolars broadcasts a scalar into list arithmetic only when the scalar side\nis a leaf (bare column or literal) — a compound scalar expression\n(col * col) against a list operand fails supertype derivation, and only\nfor add/sub (mul/div/floordiv/mod broadcast fine). The failing boundary\nis erratic at the raw level: (a*b) + col_list fails while col_scalar +\ncol_list works, and even col_list + (a*b) fails while (a*col_list) +\n(a*b) works. So the natural actuarial shape\nAnnPrem*ExpsPerPrem + (SA*ExpsPerSA + ExpsPol)*InflFactor lived or died\non operand order — three instances found in the wild during the v0.6.0\nfield test, all 'fixed' by flipping operands.\n\nThe dispatch layer now compensates, shape-driven rather than replicating\npolars' quirk boundary: when one operand of +/- is a compound scalar\n(ExpressionProxy with scalar shape) and the other is list-shaped, the\ncompound side is pre-broadcast with repeat_by to the list side's per-row\nlengths (jagged-safe) and the op executes as native list-list\narithmetic. Bare columns, literals, and the working operators keep their\nexisting native plans; unknown shapes are left alone rather than\nguessed.\n\nMeet you where you are: the formula as written in the spec is the\nformula in the code — requiring an operand-ordering rule to make +\ncommute broke that. Sharp knives: the previous behaviour was not a\nprincipled refusal (the same expression worked when mirrored).\n\n13 new tests pin order-independence for + and -, subtraction\nantisymmetry, untouched * and /, the when()-branch shape, and jagged\nper-row broadcasting. Full suite: 2,812 passed.",
          "timestamp": "2026-08-02T20:01:21+12:00",
          "tree_id": "17ef386f55253b8c0fb5a35900a983c86939e8f3",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b63d7c1ab442e1bfac82cf0e912438aabf94e0f6"
        },
        "date": 1785659098881,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.789,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 211.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2639.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.838,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 570,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2955.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 543.366,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 580.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1840.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.92,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 904.2,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4012.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 260.32,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4819,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3841.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "6f57792bbf110519c8aa5f99d26a401196db4358",
          "message": "fix(scenarios): refuse scenario_id-carrying base tables in shocks-dict stacking (#52) (#61)\n\nstack_shocked_table stamps pl.lit(sid) over scenario_id on every\nbase_tables entry — a table already keyed by a scenario axis had its\noriginal scenarios silently collapsed onto one batch key. Before strict\ntable builds (#17) this last-write-won silently: the shipped scenarios\ndocs example printed 1714.28 (every scenario priced at the UP rate)\nwhere the true per-scenario answer is 1748.01. After #17 it became a\n'Duplicate key combination at source row N' error — loud, but far from\nthe cause and naming neither the table's existing scenario axis nor the\nfix.\n\nThe stacking boundary now raises upfront, naming the table, its existing\nscenario_id dimension, and both remedies: keep the table\nscenario-invariant and express per-scenario differences as shocks (the\nshocks-dict contract), or pass the scenario-keyed table through the\nid-list/drivers shapes, where base_tables reach the model untouched.\n\nSharp knives, no magic: refuse to run rather than silently fill in a\nfallback that looks right until the regulator asks. The docs side was\nhandled in opioinc/gaspatchio-docs#8; this is the core guard.\n\nFour new tests: the refusal, the message contract (table + axis + both\nremedies), the scenario-invariant happy path untouched, and the\nScenarioRun entry point surfacing the guard instead of the deep\nduplicate-key error. Full suite: 2,803 passed.",
          "timestamp": "2026-08-02T20:28:51+12:00",
          "tree_id": "ae68e2dd73c32b186f7cb2f4b9490d4964279442",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/6f57792bbf110519c8aa5f99d26a401196db4358"
        },
        "date": 1785660515816,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.075,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 204.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3252.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 28.956,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 537.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3453.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 420.57,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 578,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2377.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 19.98,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 890.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 5005,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 200.999,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4744.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4975.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "eaf8721925694f1148c4844f1f8d2e4a75f55406",
          "message": "release: v0.7.1 — addition commutes, and panics name their column (#62)\n\nThree fixes from the v0.6.0 field-test backlog, none breaking: scalar/\nlist broadcast is order-independent for + and - (#53), plan-lowering\npanics convert to attributed SchemaErrors at the collect boundary (#54),\nand a shocks-dict ScenarioRun refuses a base table that already carries\nscenario_id (#52). Plus the event-listener 5.4.2 lock bump clearing\nRUSTSEC-2026-0221 from the main-branch scan.\n\nVersion stamps in core/Cargo.toml, bindings/python/Cargo.toml,\nbindings/python/pyproject.toml; Cargo.lock and uv.lock regenerated\n(uv lock --check passes).",
          "timestamp": "2026-08-02T21:39:56+12:00",
          "tree_id": "b0dd349ad47f48f455e75c025d0527121f6ab11d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/eaf8721925694f1148c4844f1f8d2e4a75f55406"
        },
        "date": 1785664899263,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.029,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 202.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2481.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.691,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 561.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2968.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 523.303,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 572.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1910.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.485,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 860.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4084.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 232.129,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4823.2,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4307.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "eaf8721925694f1148c4844f1f8d2e4a75f55406",
          "message": "release: v0.7.1 — addition commutes, and panics name their column (#62)\n\nThree fixes from the v0.6.0 field-test backlog, none breaking: scalar/\nlist broadcast is order-independent for + and - (#53), plan-lowering\npanics convert to attributed SchemaErrors at the collect boundary (#54),\nand a shocks-dict ScenarioRun refuses a base table that already carries\nscenario_id (#52). Plus the event-listener 5.4.2 lock bump clearing\nRUSTSEC-2026-0221 from the main-branch scan.\n\nVersion stamps in core/Cargo.toml, bindings/python/Cargo.toml,\nbindings/python/pyproject.toml; Cargo.lock and uv.lock regenerated\n(uv lock --check passes).",
          "timestamp": "2026-08-02T09:39:56Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/eaf8721925694f1148c4844f1f8d2e4a75f55406"
        },
        "date": 1785738274638,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 2.456,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 223.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 4071.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 23.526,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 554.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 4250.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 294.672,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 623.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 3393.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 13.779,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 894.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 7257.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 142.995,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4770.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 6993.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "03df6ed7f6fa780a2a856572fbb8f74bbf52300f",
          "message": "fix(rollforward): broadcast scalar inputs; name the NAR timing convention on deduct_nar (#65)\n\n* fix(rollforward): accept scalar input columns and broadcast across periods\n\nA level death benefit or a flat charge rate is naturally one value per\npolicy, but every rollforward input had to be a List column, so callers\nhad to materialise n_periods identical copies of the same number. That is\nceremony with no meaning, and the error when they didn't (\"must be List\ndtype\") named the symptom rather than the fix.\n\nScalar (numeric, non-List) inputs are now broadcast across the period\naxis. List inputs are untouched, so existing plans produce bit-identical\nresults.\n\nThree sites inferred period counts from owned_slices[0], which with a\nscalar column registered first would read a horizon of 1 and reject every\npolicy: the row count, the uniform-schedule guard, and the per-row length\ncheck. All three now consider only genuine per-period lists, and a\nregression test registers the scalar column first to hold that.\n\nThe dtype is checked before casting rather than relying on the cast to\nfail: polars casts String to Float64 as nulls, so a string input would\notherwise have surfaced as \"null value not supported\" instead of naming\nthe real problem.\n\nServes Meet you where you are — accept the shape the assumption already\nhas, rather than making the user reshape it to suit the kernel.\n\n* feat(rollforward): name the NAR timing convention on deduct_nar\n\ndeduct_nar measured the net amount at risk where the charge was taken and\napplied no discount. That is one mainstream universal life convention. The\nother charges COI at the start of the period for a death benefit paid at\nthe end, so the amount at risk is measured against the accumulated balance\nand the charge is discounted back — and it was not expressible.\n\nThe two agree under constant rates and diverge once rates vary, silently:\nboth produce plausible account values and nothing errors. On a 5-year\nprojection at 3% credited the account values differ by 0.24% in year one\nand 0.74% by year five, widening throughout.\n\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face)   # unchanged default\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face,\n                       nar_timing=\"end_of_period\",\n                       coi_discount_rate=af[\"coi_disc\"],\n                       credited_rate=af[\"credited\"])\n\nUnder end_of_period the COI and the balance are mutually dependent, since\ndeducting the charge lowers the balance and so raises the amount at risk.\nThe kernel solves that in closed form rather than iterating:\n\n    NAR = (death_benefit - s*accum) / (1 - coi_rate*accum*v)\n\nnar_timing reuses beginning_of_period / end_of_period, the vocabulary\nprospective_value and cumulative_survival already use — this is the third\ntiming-sensitive method in the API and should not introduce a third\nvocabulary. The default is unchanged and bit-identical.\n\nThe rates are separate arguments rather than inferred from a neighbouring\ngrow(): the COI discount rate is its own product assumption, distinct from\nthe credited rate. Passing either without end_of_period raises rather than\nbeing silently ignored, and an unknown nar_timing names the valid options.\n\nNaming the convention also avoids an argument whose identity value would\nnot reproduce the default: an inferred discount of 1.0 gives the\nsimultaneous solve, not the beginning-of-period form, so \"pass 1.0\" and\n\"omit it\" would have disagreed.\n\nVerified against an external universal life workbook that uses the\nend-of-period convention: NAR matches its cached 497,761.78 to floating\npoint, COI and closing account value to within its own 2dp rounding.\n\nServes Sharp knives, no magic — the convention is visible at the call site\ninstead of folded into a rate — and Meet you where you are.\n\nRefs GSP-119, #64\n\n* fix(rollforward): refuse an end-of-period NAR without its rates\n\nBoth rate factors default to 1.0 in the kernel. Left to default under\nnar_timing=\"end_of_period\" they do not degrade gracefully — they produce the\nsimultaneous-solve convention, a third real convention this API deliberately\ndoes not expose. A forgotten argument therefore returned a different answer\nrather than an error, and a plausible one: the account value still looks like\nan account value.\n\nverify() already refused the mirror-image mistake (rates supplied with\nbeginning_of_period). This closes the asymmetry and names which rate is\nmissing rather than listing both.\n\nAlso admit a Boolean scalar input. The List path casts its inner values\nunconditionally, so a per-period condition mask already worked, while the\nscalar branch gated on is_numeric() — false for Boolean. A policy-level flag,\nsuch as a ratchet's `when=`, was accepted as a list of repeats and refused as\nthe single value it naturally is.\n\nAdds Python coverage for scalar broadcast, which had none: scalar-equals-\nrepeated-list for float, int and Boolean, the all-scalar case that has no List\ncolumn to read a horizon from, and the String refusal.\n\nBoth found by Greptile on #65.",
          "timestamp": "2026-08-05T16:46:05+12:00",
          "tree_id": "e25f97f9b3c8c726a1195627dfb6afd4c1e44e5c",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/03df6ed7f6fa780a2a856572fbb8f74bbf52300f"
        },
        "date": 1785906600867,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.257,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 200.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2348.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 34.394,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 563.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2907.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 550.77,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 579.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1815.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 25.27,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 861.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3957.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 249.686,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4804,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4005,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "5545217550d0c6b5837a9862e79c7a5971fe3980",
          "message": "feat(rollforward): corridor test on deduct_nar, and refuse a negative NAR (#78)\n\ndeduct_nar measured the amount at risk as death_benefit - account_value.\nOnce a well-funded policy's account value outgrew its face amount that went\nnegative, which made the COI a credit to the account, which enlarged the\naccount, which made the amount at risk more negative. Nothing bounded it. On\na constructed universal life policy the final account value came out 166x too\nlarge, silently, with the correct and incorrect runs agreeing exactly for the\nfirst 49 years.\n\nTwo changes, either of which alone would stop the runaway.\n\ncorridor_factor= adds the regulatory corridor test that real universal life\nproducts carry — IRC section 7702's cash-value-accumulation test and its\nequivalents. The death benefit is at least y times the account value, so the\namount at risk is MAX(NARf, NARc). The corridor branch solves its own\ncircularity and the sign in its denominator is flipped, which is the whole\npoint: under a fixed benefit, charging the COI widens the gap to a fixed\ntarget, so the branch is self-reinforcing; under a proportional benefit it\nshrinks the benefit too, so the branch is self-limiting. As y decays to 1.0\nat advanced ages NARc goes to zero, and that is what caps a well-funded\npolicy. Applies to both timing conventions.\n\nA negative amount at risk is now refused outright rather than returned. It is\nnot a meaningful actuarial quantity, and the error names the period, both\nfigures, and the argument that fixes it. Passing corridor_factor=1.0 is the\nexplicit way to ask for \"floor the amount at risk at zero\", since\nDB = MAX(face, 1.0 * AV) is exactly that.\n\nChose one argument on the existing op over general state-dependent death\nbenefits. The general form is the more principled abstraction and would also\ncover increasing-benefit designs, but it needs expressions over running state\nin the IR, where Op arguments must currently be bare column references. The\none product that might have motivated it does not: a Type B (increasing)\nbenefit gives NAR = face, a constant with no circularity, already expressible\nas a precomputed subtract.\n\nCloses #77. GSP-126.",
          "timestamp": "2026-08-05T18:48:43+12:00",
          "tree_id": "b6c8fd068efa69e097fef66baa0764b93c7d7c4d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5545217550d0c6b5837a9862e79c7a5971fe3980"
        },
        "date": 1785913911762,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.716,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 194.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2691.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 34.794,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 567.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2874.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 549.023,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 581.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1821.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 26.691,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 320.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3746.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 240.471,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4858.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4158.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "0783b17d8de91bb609e39facb4af4d9f5ee290ec",
          "message": "docs(skills): gotcha #4 said af.month doesn't exist — it does (#79)",
          "timestamp": "2026-08-08T09:08:47+12:00",
          "tree_id": "cb06abc5117f274fc966c2ee17f1f13d39b0d03a",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0783b17d8de91bb609e39facb4af4d9f5ee290ec"
        },
        "date": 1786139576663,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.727,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 200.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2683,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 45.396,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 547.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2202.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.477,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 874.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4085.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 240.838,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4844.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4152.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "239c92c7f5beec9d340de6aefee4d46a0028ebe3",
          "message": "docs: make CONTRIBUTING canonical, add code of conduct and PR template (#87)\n\n* chore(gitignore): ignore .claude/worktrees/\n\nAgent worktrees under .claude/worktrees/ carry a full bindings/python/.venv.\nOne stale worktree left 6.7 GB untracked at the repo root — 21,727 vendored\nfiles that break `reuse lint` locally and sit one `git add .` away from being\ncommitted. CI never catches this because it checks out clean.\n\nxl-marinade already ignores this path; gaspatchio ignored three other .claude\npaths but not this one.\n\n* docs: make CONTRIBUTING canonical, add code of conduct and PR template\n\nContribution rules lived only in AGENTS.md, which coding agents read and human\ncontributors never see. GitHub surfaces CONTRIBUTING.md as a banner when someone\nopens an issue or a PR, and counts it in community standards — that is where the\nrules belong.\n\nCONTRIBUTING.md is now canonical for humans and agents alike: branch-vs-fork\nguidance (including which workflows fork PRs cannot run, since evals.yml and\ntrigger-rag-rebuild.yml need real secrets), the bindings/python working-directory\nrule, signing setup for the signed-commits ruleset now active on main, the\nissue-title convention, PR scope, and the merge policy. AGENTS.md keeps only what\ndiffers when there is no human in the loop and points at it.\n\nAdds the Contributor Covenant 2.1 and a PR template that asks which principle a\nchange serves and which it strains, and — for anything moving a projected number —\nbefore/after on a reproducible model point with the timing convention stated,\nsince constant rates hide that class of error entirely.\n\nCloses the CONTRIBUTING, CODE_OF_CONDUCT and pull_request_template gaps in\nGitHub's community standards checklist.\n\n* docs: regenerate copilot-instructions after the AGENTS.md change\n\n.github/copilot-instructions.md is generated from AGENTS.md by\nscripts/gen_skill_manifests.py, and tests/skills/test_skill_manifests.py asserts\nthe two stay in sync. The previous commit edited the source without regenerating.\n\n* docs: correct the signing guidance — squash does not sidestep the rule\n\nThe claim that unsigned commits need no rewrite because a squash merge produces a\nsingle signed commit is wrong, and was proven wrong on gaspatchio/xl-marinade#3:\n`gh pr merge --squash` was refused with \"the base branch policy prohibits the\nmerge\". GitHub evaluates required_signatures against every commit in the PR and\nrefuses before it creates the squash commit.\n\nUnsigned commits must be re-signed, which means a rebase. Says so now, and points\ncontributors at a maintainer rebase rather than leaving them to untangle it.\n\n* docs(pr-template): guard the changelog against concurrent-merge clobber\n\nThe template asked for a CHANGELOG entry only when the public API changed, and\nsaid nothing about the case that actually bites: two PRs editing the same\nchangelog block, the later merge silently winning with no test to catch it.\nThat happened on gaspatchio/xl-marinade#8, whose speedup vanished from its\nrelease notes.\n\nMakes the entry conditional on user-visible change rather than API surface, and\nadds an explicit re-check when main has moved under an open PR.",
          "timestamp": "2026-08-08T11:06:54+12:00",
          "tree_id": "a73d21674a045774bfbdf59221773d69e6e38b77",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/239c92c7f5beec9d340de6aefee4d46a0028ebe3"
        },
        "date": 1786145219987,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 2.705,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 213.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3696.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 29.926,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 563.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3341.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 368.071,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 578.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2716.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 17.032,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 899.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 5871.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 175.512,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4847.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 5697.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "3908b8247152d2362401e950bb00b043a237d994",
          "message": "fix(deps): bump cryptography to 50.0.0; filter the unreachable pymdown ReDoS advisory (#88)\n\nTwo new High advisories landed in OSV and now fail the scheduled scan on\nevery main push. cryptography 49.0.0 (PYSEC-2026-3552 / GHSA-g6cj-pr64-35w5,\nCVSS 8.2) has a published fix — take it via the lockfile; it is transitive\ndev tooling (authlib, google-auth, joserfc, pyjwt, secretstorage), nothing\nin the wheel's runtime closure.\n\npymdown-extensions (GHSA-gm37-52c6-37mw, ReDoS in the default inline\nprocessors, CVSS 7.5) is fixed only in 11.0.1, which the resolver cannot\nreach: marimo 0.23.13 pins pymdown-extensions>=10.21.2,<11 — the same\nversion-lock already documented for GHSA-9xwg-3r6f-jcx2. Filter it with\nthe same reachability reasoning and the same revisit trigger.",
          "timestamp": "2026-08-08T11:46:22+12:00",
          "tree_id": "409b6f9627f19e98c63a80cefff7983fe972b7d6",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/3908b8247152d2362401e950bb00b043a237d994"
        },
        "date": 1786147842486,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.461,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 208.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2241.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 46.397,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 542.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2155.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 569.854,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 563,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1754.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 31.781,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 883.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3146.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 237.04,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4850.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4218.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "5310176fbf7e13c402841d53f487a3c39799d9ee",
          "message": "fix(assumptions): lookup() cooperates with proxies in either operand order (#84)\n\n* fix(assumptions): lookup() cooperates with proxies in either operand order\n\npl.Expr's binary operators raise on a ColumnProxy/ExpressionProxy operand\ninstead of returning NotImplemented, so Python never offers the proxy its\nreflected method — lookup(...) * af.v raised while af.v * lookup(...)\nworked. Which of two mathematically identical spellings crashes is exactly\nthe kind of trap the formula-is-the-code promise forbids.\n\nlookup() now returns ProxyAwareExpr, a pl.Expr subclass whose operators\nunwrap a proxy operand to its underlying expression and re-wrap their\nresults, so the property survives operator chains\n(lookup * af.a * af.b). isinstance(x, pl.Expr) stays true — no new type\nfor callers to know about, and every existing annotation still holds.\n\nCloses #67.\n\n* fix(column): delegate proxy-operand operators to the proxy layer; extend the contract to rollforward and Schedule exprs\n\nReview hardening of the gh#67 fix. The red-team probe matrix caught a\nreal divergence in the first design: unwrapping the proxy operand and\ndelegating to raw polars bypassed the proxy layer's operator shims, so\nlookup(...) ** af.list_col raised (polars has no list pow) while the\nreverse order worked — the same asymmetry class gh#67 describes, one\nshape up.\n\nProxyAwareExpr now hands a proxy operand the whole operation via the\nreflected operator: the proxy layer stays the single owner of operator\nsemantics, current and future shims included, and the result is the\nframe-native ExpressionProxy with the full accessor surface. Non-proxy\noperands delegate to polars unchanged and re-wrap.\n\nThe same either-order contract now covers the other bare-Expr surfaces a\nmodel combines with af columns — CompiledRollforward.expr_for /\nincrement_for, the collector's self-contained exprs, and the\nSchedule.*_expr family.\n\nA 40-cell operator x shape x operand-order matrix checks every cell\nagainst a pure-Python reference so the two dispatch routes can never\ndiverge silently. One cell is xfail: scalar base ** list-valued\nexpression exponent, a pre-existing proxy-layer gap (gh#89). The\noperator-only boundary of the guarantee is documented in the module and\nlookup docstrings; the raise-not-NotImplemented root cause is filed\nupstream as pola-rs/polars#28748.",
          "timestamp": "2026-08-08T12:29:02+12:00",
          "tree_id": "a4538836236d2a4fc25d12a0c4be3489e06ab523",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5310176fbf7e13c402841d53f487a3c39799d9ee"
        },
        "date": 1786150626958,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.369,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 220.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2288.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 32.553,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 534.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3071.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 901.261,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 564.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1109.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 25.226,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 849.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3964.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 211.165,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4808.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4735.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "51a86c110bfb73b98191269ee2e564aee6bb754b",
          "message": "release: v0.8.0 — rounding is requested by name, and lookups commute (#90)\n\nThe v0.6.0 field-test issue batch (#66–#68, #70–#73) plus the preceding\nrollforward hardening. New: .excel.round with Excel's half-away-from-zero\non per-period columns (the never-implemented panicking wrappers are\nremoved), a rollforward Round op on the same rule by design, and a\ncorridor test on deduct_nar with a negative NAR refusing to run. Fixed:\nlookup() and the other bare-Expr surfaces cooperate with proxies in\neither operand order, only declared columns become dimension keys, scalar\nrollforward inputs broadcast across periods, and the length-mismatch\nerror points at what fails. Plus the cryptography 50.0.0 bump and the\nreviewed pymdown advisory filter.\n\nVersion stamps in core/Cargo.toml, bindings/python/Cargo.toml,\nbindings/python/pyproject.toml; Cargo.lock and uv.lock regenerated\n(uv lock --check passes).",
          "timestamp": "2026-08-08T13:38:48+12:00",
          "tree_id": "2063e3a8d0ce1f82739353fa8ebc58601be1dad2",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/51a86c110bfb73b98191269ee2e564aee6bb754b"
        },
        "date": 1786154501685,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.723,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 212.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2686,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.675,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 576.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2969.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 564.451,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 599.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1771.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.35,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 875.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4106.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 239.997,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4886.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4166.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "01d554dcf6cf1fae68c59f80267392a737d8a1ea",
          "message": "release: v0.8.1 — the surface tells the truth (#100)\n\nVersion stamps 0.8.0 → 0.8.1 in core/Cargo.toml,\nbindings/python/Cargo.toml, and bindings/python/pyproject.toml, with\nCargo.lock and uv.lock regenerated to match, plus the CHANGELOG entry.\n\nPatch-only: #96 (gspio tutorial reaches the shipped rollforward\npatterns, gh#94), #97 (capture-slot errors name the real rule, gh#93),\n#98 (track_increments=True refuses loudly at build time, refs gh#69).\nNo numeric behaviour changes.",
          "timestamp": "2026-08-08T21:07:26+12:00",
          "tree_id": "867a41d4565773529b115ca7765815ed3656b70f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/01d554dcf6cf1fae68c59f80267392a737d8a1ea"
        },
        "date": 1786181474170,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.379,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 197.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2283.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 80.731,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 545.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 1238.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 555.546,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 598.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1800,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.889,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 878,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4186.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 235.451,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4829.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4247.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "4692029197f4eb802ca161b509f78b0d34a01bfb",
          "message": "fix(accessors): gate list path on shape, not proxy type, so composed expressions convert element-wise (#105)\n\nto_monthly(), compound(), and cumulative_survival() gated their list\npath on isinstance(proxy, ColumnProxy), so a composed list-valued\nExpressionProxy fell through to the scalar path and refused to run at\ncollect (pow on list[f64], cum_prod on list). Gate on the resolved\nshape alone — the pattern PR #85 established for excel.round; both\nproxy types resolve .shape identically.\n\nServes 'Meet you where you are': a composed per-period expression is\nthe same shape the user already had, and the accessor now accepts it.\n\nFixes #86",
          "timestamp": "2026-08-09T11:18:37+12:00",
          "tree_id": "302976df27e98e9aba604bc033c6af1e96555af8",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/4692029197f4eb802ca161b509f78b0d34a01bfb"
        },
        "date": 1786232588584,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.814,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 208,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2622.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 35.894,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 572,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2786,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 546.713,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 595.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1829.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.633,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 889.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4059.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 238.861,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4856.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4186.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "0000b0b3908078ec95e5058a98bd63a2e363ad2f",
          "message": "fix(column): resolve bare-expression shapes in the pow dispatch, so scalar ** lookup(list key) works (#106)\n\nThe pow shim's operand detection only recognised proxy operands, so a\nbare pl.Expr exponent (e.g. Table.lookup over a list key) was treated\nas scalar and handed to raw polars pow, which has no list support.\nResolve a bare expression's shape from the schema the same way\nExpressionProxy does (_shape_from_expr_dtype), extracted into a\n_pow_arg_is_list helper.\n\nFlips the operator x shape matrix xfail cell\n(list_x_scalar/pow/proxy_first) to a passing assertion, as gh#89\nspecified.\n\nFixes #89",
          "timestamp": "2026-08-09T19:49:59+12:00",
          "tree_id": "c760f7133b415088c889a366834ffc6b0da25704",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0000b0b3908078ec95e5058a98bd63a2e363ad2f"
        },
        "date": 1786263177685,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.974,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 221,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2010.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 47.252,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 554.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2116.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 551.287,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 601.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1813.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 27.519,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 867.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3633.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 243.127,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4904.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4113.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "0c0884e2385c1f4924f10f9d668997c56239d7d6",
          "message": "docs(skills): formula_pattern cannot signal a mixed binding — teach the distribution query (#107)\n\n* docs(skills): formula_pattern is one row's formula — teach the distribution query, not trust in the column\n\nThe conversion reference claimed formula_pattern 'reports the dominant\npattern, not the exception'; on merged mixed bindings it reports one\nrow's formula — in the observed cases the first row's, which is\nprecisely the exception (upstream: gaspatchio/xl-marinade#12, the\nschema stores a single formula id per binding). Replace the claim with\nthe defensive truth and the Counter-over-formula_r1c1 idiom the\nround-three clean-room run used to catch it.\n\nRefs #103\n\n* docs(skills): make the distribution query runnable from the binding row\n\nThe worked example bound sheet/col/first_row/last_row without saying where\nthey come from, and agent_cells_light stores col as a 1-based number — a\nreader deriving the letter from the binding address gets zero rows with no\nerror. Parse the binding's own A1 range instead; snippet executed against a\nreal IR (capital-regimes erm-153 extract) before committing.\n\nAddresses Greptile review on #107.",
          "timestamp": "2026-08-09T20:20:55+12:00",
          "tree_id": "a5beb9e7f0c8f36d9952b5b146aa1a589e51d62b",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0c0884e2385c1f4924f10f9d668997c56239d7d6"
        },
        "date": 1786264716045,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 2.931,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 214.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3411.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 25.596,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 572.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3906.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 391.394,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 607.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2555,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 19.65,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 864.2,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 5089.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 183.647,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4887.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 5445.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "0c0884e2385c1f4924f10f9d668997c56239d7d6",
          "message": "docs(skills): formula_pattern cannot signal a mixed binding — teach the distribution query (#107)\n\n* docs(skills): formula_pattern is one row's formula — teach the distribution query, not trust in the column\n\nThe conversion reference claimed formula_pattern 'reports the dominant\npattern, not the exception'; on merged mixed bindings it reports one\nrow's formula — in the observed cases the first row's, which is\nprecisely the exception (upstream: gaspatchio/xl-marinade#12, the\nschema stores a single formula id per binding). Replace the claim with\nthe defensive truth and the Counter-over-formula_r1c1 idiom the\nround-three clean-room run used to catch it.\n\nRefs #103\n\n* docs(skills): make the distribution query runnable from the binding row\n\nThe worked example bound sheet/col/first_row/last_row without saying where\nthey come from, and agent_cells_light stores col as a 1-based number — a\nreader deriving the letter from the binding address gets zero rows with no\nerror. Parse the binding's own A1 range instead; snippet executed against a\nreal IR (capital-regimes erm-153 extract) before committing.\n\nAddresses Greptile review on #107.",
          "timestamp": "2026-08-09T08:20:55Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0c0884e2385c1f4924f10f9d668997c56239d7d6"
        },
        "date": 1786337090149,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.781,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 195.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2644.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.754,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 562.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2962.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 544.231,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 586.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1837.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 27.059,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 871.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3695.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 241.957,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4846.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4133,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "9e30a3b55103582f3c3696082dafc7f495512051",
          "message": "docs(skills): draw the proxy duck-typing boundary — clip and when/then, not *_horizontal (#108)\n\n* docs(skills): draw the proxy duck-typing boundary — polars free functions don't know af['col']\n\nThe model-building skill claimed the bracket form 'works everywhere';\npl.max_horizontal(af['a'], af['b']) raises 'cannot create expression\nliteral for value of type ColumnProxy' (gh#102). Scope the claim to\ngaspatchio call sites and teach the working idioms: .clip() for the\nExcel MAX/MIN clamp, when/then/otherwise for element-wise max of two\ncolumns (broadcasts on list columns, which the horizontal functions\nwould not). Both idioms executed on 0.8.1 before documenting.\n\nRefs #102\n\n* docs(skills): state the null contract on the when/then max idiom\n\nThe conditional max is not Excel's blank-ignoring MAX: a null comparison\ntakes the otherwise branch (MAX(7, null) -> null where Excel returns 7),\nand on list columns the mask blend nulls any element where either operand\nis null — executed on both shapes before writing this down. The doc's job\nis naming silent divergences from the spreadsheet being translated; this\nwas one.\n\nAddresses Greptile review on #108.",
          "timestamp": "2026-08-14T15:24:37+12:00",
          "tree_id": "3b8d50e25cb79d7704311154d341eb18799b2a5a",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/9e30a3b55103582f3c3696082dafc7f495512051"
        },
        "date": 1786679258109,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.769,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 204.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2653.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.692,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 560.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2968.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 518.179,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 590.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1929.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.646,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 909.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4229.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 238.133,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4880.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4199.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "b511ab8f9bf7ae3dd612f55955f32be0ba06dd30",
          "message": "feat(rollforward): round_charge — round the individual flow, not the state (#112)\n\n* feat(rollforward): round_charge rounds the individual flow, not the state\n\nSpreadsheets round individual charges inside the recursion and leave\nthe running balance unrounded — s -= ROUND(coi, 2) — a placement the\nvocabulary could not express: Round targets the state and discards the\nsub-cent residue every period. The two agree only while the balance is\nan exact multiple of the rounding unit, so the mechanism difference\nsurvives testing and drifts at scale.\n\nround_charge: int | None on charge/grow/deduct_nar rounds the computed\nflow (half away from zero, Excel's rule, shared round_half_away helper\nwith the Round op) before applying it, leaving the state to carry its\nresidue forward. Under end-of-period NAR timing the exact charge is\nsolved first, then rounded — rounding does not participate in the\nclosed-form solve, and this is documented at the call site.\n\nSerde-defaulted on the kernel op enum, so previously-serialised IRs\nkeep the unrounded behaviour.\n\nFixes #92\n\n* fix(rollforward): refuse non-int round_charge at construction\n\n2.0 and True both survived the range check (bool is an int subclass) and\ntravelled to the kernel's Option<i32>, failing at compile/collect with a\nserde error that never names round_charge. Refuse at verify() instead,\nnaming the argument and the fix — the same construction-time honesty as\nthe bounds check beside it (Sharp knives: refuse to run rather than fail\nopaquely later). Red test first. Also settles two pre-existing D205s in\nthis PR's own Grow/GrowCapped docstrings so the branch lints clean.\n\nAddresses Greptile review on #112.",
          "timestamp": "2026-08-16T16:20:42+12:00",
          "tree_id": "5bcbf4546ee5d0658ef448bb13cb7b26b44c4d92",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b511ab8f9bf7ae3dd612f55955f32be0ba06dd30"
        },
        "date": 1786855414304,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.687,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 207.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2712.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.498,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 568.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2985.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 545.457,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 587.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1833.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.598,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 900.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4237.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 238.462,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4911.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4193.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "744242a6028b8b3868509b618d8cd89640e71bf8",
          "message": "fix(typing): heal the two mypy errors merge skew left on main (#125)\n\nEach tranche PR was mypy-clean against the main it branched from; the\ncombination is not. #109's truthful stubs made the assignment ignore in\n_passes.py redundant, and _builder's duck-typed pass-through now returns\nan unlaundered Any. CI only gates stubtest, so this never went red\npublicly — but the documented dev standard is both checkers pass, and\nthe next branch to run mypy locally inherits the noise.\n\nVerified: uv run mypy gaspatchio_core/rollforward/ clean; rollforward\nsuite 229 passed on the current kernel build.",
          "timestamp": "2026-08-16T19:58:16+12:00",
          "tree_id": "a1defa862230103b5cf1c4333c12929a2284fc6c",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/744242a6028b8b3868509b618d8cd89640e71bf8"
        },
        "date": 1786868171705,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 2.828,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 237.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3535.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 25.852,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 570,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3868.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 398.854,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 591.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2507.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 19.067,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 916.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 5244.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 182.771,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4911.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 5471.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c",
          "message": "release: v0.8.2 — the recursion tells the whole truth\n\nReal per-op increment emission closes the #69 arc; round_charge places ROUND on the flow as source spreadsheets do (#92); between() scope sticks to its handle (#101); truthful stubs un-blind the rollforward API (#104); shape-gated conversions (#86, #89); skill honesty (#102, #103).",
          "timestamp": "2026-08-16T20:26:56+12:00",
          "tree_id": "28e43bada9956aeb8e736ae581ea08a8047dd50c",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c"
        },
        "date": 1786870193084,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.8,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 200.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2631.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.788,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 572.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2959.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 560.313,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 602.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1784.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.973,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 898.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4171.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 239.183,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4879.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4180.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c",
          "message": "release: v0.8.2 — the recursion tells the whole truth\n\nReal per-op increment emission closes the #69 arc; round_charge places ROUND on the flow as source spreadsheets do (#92); between() scope sticks to its handle (#101); truthful stubs un-blind the rollforward API (#104); shape-gated conversions (#86, #89); skill honesty (#102, #103).",
          "timestamp": "2026-08-16T08:26:56Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c"
        },
        "date": 1786939328767,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.663,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 197.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2729.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 34.527,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 578.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2896.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 555.157,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 590.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1801.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 26.248,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 915,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3809.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 247.515,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4812.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4040.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "6dac1471b88ecab7e0b6dfc1eb5dcbf4aa4981cb",
          "message": "feat(graph): calc-graph nodes carry shape and kind from the shape SOT (#134)\n\n* feat(graph): calc-graph nodes carry shape and kind from the shape SOT\n\nThe lineage graph classified columns only by raw dtype string, while\nthe framework's own shape/kind vocabulary (scalar/list,\nvalue/boolean_mask) lived unwired next door in column/shape.py. Expose\ntwo dtype-only helpers on the SOT (shape_from_dtype, kind_from_dtype —\nsame rules, one home; _shape_from_schema now routes through the former)\nand stamp every graph node with both at construction. Lineage output\nnow speaks the same shape language as the dispatch layer.\n\n* feat(graph): backfill node dtype/shape/kind from the collected schema\n\nTracing-time dtype inference is a per-assignment probe and can return\nNone, and a probe failure cascades to downstream assignments — those\nnodes exported shape/kind as unknown even though the frame's collected\nschema knows the answer. After building the graph, resolve any\nstill-unknown dtype/shape/kind from the schema; a schema failure\ndegrades to the traced values rather than breaking export.",
          "timestamp": "2026-08-17T19:58:25+12:00",
          "tree_id": "9f9b3abfcb5cc6cfced9029d32283eb8f6d3d78f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/6dac1471b88ecab7e0b6dfc1eb5dcbf4aa4981cb"
        },
        "date": 1786954945995,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.699,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 204.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2703.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 34.803,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 568.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2873.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 543.477,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 617,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1840,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 25.217,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 911,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3965.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 237.531,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4876.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4210,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "db9b0299c7b86bbe2fbb6cb16ea68656f242a5d8",
          "message": "perf(bench): generate model points instead of committing 22.8 MB of LFS (#140)\n\n`benches/fixtures/age-last-smoking-{1k,100k}.parquet` fed only the assumption-table\nlookup benchmarks, and almost all of it was redundant: every list column is a pure\nfunction of five scalars per policy, so 100,000 policies expand to 64.4M projection\nmonths from ~500 KB of real entropy.\n\nLFS bandwidth is billed to the repository owner on every fetch, including\nthird-party clones of this public repo — 2,316 clones from 356 unique cloners in\n14 days, largely the plugin marketplace, none of which need benchmark fixtures.\n#139 scoped and cached CI's fetches; removing the object from the checked-out tree\nmeans it is never fetched by anyone. `core/benches/**` drops from 22.86 MB to ~50 KB.\n\n`benches/common/mod.rs` generates the frame from a per-policy SplitMix64 stream\nseeded off the policy index, so a policy's attributes depend only on its index and\n`model_points(1_000)` is exactly the first 1,000 rows of `model_points(100_000)` —\nthe nesting the cross-size benchmarks rely on. Wrapping integer arithmetic only, so\nLinux and Windows agree. Both sets are memoised; previously the bench groups did\nfive full 22 MB parquet reads per run.\n\nAlso removes the unreferenced 100-row `age-last-smoking.parquet` seed. The copy at\nbindings/python/jobs/example/ is a different consumer and is untouched.\n\nFidelity vs the retired fixtures, measured before deletion: identical schema,\nidentical row count, 950 vs 950 distinct (issue_age, duration) combinations, and\n64,303,576 vs 64,352,584 exploded projection months (-0.08%).\n\ncore/tests/bench_model_points.rs pins schema, every derivation, scalar/list\nagreement, the prefix property, determinism and key-space coverage.\n\nExpect a one-time ~9% step down on array_lookup_1k and array_vector_lookup_1k.\nThe compute-bound hash_vector case is flat at +0.3%, so the lookup workload is\nequivalent; the array delta was not isolated (data volume, key diversity and\nchunking all ruled out). Far inside the 200% alert threshold.",
          "timestamp": "2026-08-18T14:19:27+12:00",
          "tree_id": "7d1ea29e9f087b2877bfae7377ead557b88aae98",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/db9b0299c7b86bbe2fbb6cb16ea68656f242a5d8"
        },
        "date": 1787021671959,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 4.486,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 202,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2229.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 48.205,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 551.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2074.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1214.088,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 559.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 823.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.663,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 902.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4226.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 239.01,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4880.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4183.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "e13687a5d92127353633e50da6bca3880154d40c",
          "message": "docs(tutorials): state the run-model contract where __main__ teaches the standalone form (#136)",
          "timestamp": "2026-08-18T18:22:16+12:00",
          "tree_id": "4f16303432f3f9af1467c09d8b73cdc667ec1fed",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e13687a5d92127353633e50da6bca3880154d40c"
        },
        "date": 1787035559075,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.695,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 193.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2706.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.58,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 562.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2977.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 540.874,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 597.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1848.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 29.773,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 887.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3358.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 250.361,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4853.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3994.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "b3111b5cbced6be05d2a5e77331b52e2e4dfff51",
          "message": "fix(assumptions): refuse lookups from a superseded Table object (#137)\n\n* fix(assumptions): refuse lookups from a superseded Table object\n\nTables resolve by name at execution time (last-writer-wins), so a\nscenario override built before load_assumptions() silently resolved to\nbase data and the sweep reported zero sensitivity — the run succeeded,\nthe numbers were plausible, and the shock never happened (#116, vm20\nclean room L8).\n\nRefuse at the point of guaranteed wrongness: lookup() on a Table whose\nname has since been re-registered with different content now raises\nTableSupersededError naming the hazard and the fix. Registration itself\nstays permissive — same-name tables across different models in one\nprocess and identical-content re-runs (#39 reentrancy) are legitimate\nand untouched, which is also why the issue's registration-time\nrefusal was rejected: table names like \"mortality\" are reused\npervasively across independent models.\n\nFixes #116\n\n* fix(assumptions): extend() re-stamps the content identity it registers\n\nReview catch (Greptile P1 on the PR): extend() appended to the Rust\nregistry and to self._df but left both compared content hashes at the\npre-extension value. A later registration of the ORIGINAL data then\nread as idempotent reentrancy, and a lookup from the extended object\npassed the superseded guard while resolving to data that had silently\nlost the appended rows — the exact class of silent wrong the guard\nexists to refuse.\n\nextend() now re-sorts the concatenated frame by its key columns\n(restoring the _process_data invariant) and re-stamps both the object's\nand the registry's content hash from it.\n\nRefs #116\n\n* fix(assumptions): record the registered hash only after registration succeeds\n\nReview catch (Greptile, second pass): _process_data wrote the new\ncontent hash into the supersession dict before calling the Rust\nregistry. A failed replacement left the dict holding a hash the\nregistry never accepted, and the guard then wrongly refused lookups\nfrom the still-valid previous table. The write ordering predates this\nPR, but it only became load-bearing when the guard started reading it.\n\nMove the write after the successful register_or_replace_table call;\nthe different-content warning still reads the previous hash first.\n\nRefs #116\n\n* fix(assumptions): make extend() commit registry and identity together\n\nReview catch (Greptile, third pass — same species as the first two):\nthe native append ran before the Python-side concat, so a concat\nfailure after an accepted append left the registry extended while the\nobject and the supersession dict still carried the pre-extension\nidentity — the audit surface attesting data the lookups no longer\nserve.\n\nBuild the post-extension frame and its hash before the native append;\nafter the append succeeds, commit self._df and both hashes with plain\nassignments that cannot fail. Either both sides move or neither does.\n\nRefs #116",
          "timestamp": "2026-08-18T20:05:33+12:00",
          "tree_id": "d58d21eeff1561ef70d36b3f622f83447be3493c",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b3111b5cbced6be05d2a5e77331b52e2e4dfff51"
        },
        "date": 1787041673682,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.668,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 209.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2726.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 40.108,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 552.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2493.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 524.803,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 604,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1905.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 27.141,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 897.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3684.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 237.954,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4899,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4202.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "7cbd2c540c8ac8cc09c4aa1c6147d27f3c16d800",
          "message": "feat(cli): docs/knowledge results get dedup and snippet windows by default (#138)\n\n* feat(cli): docs/knowledge results get dedup and snippet windows by default\n\nThe retrieval surface is a CLI chosen for token efficiency, and per-hit\npayload is part of that contract. Two costs broke it: near-identical\nchunks ingested under different doc_ids repeated the same preamble at\nthe top of the ranking (#120), and results inlined whole source\ndocuments — one default query returned ~16 KB, in a workflow whose\nskills mandate a docs lookup before every unfamiliar method (#130).\n\nBoth fixed client-side, after the API returns and before the JSON\nprints, with nothing hidden: near-duplicate hits collapse into the\nfirst-ranked copy and the response reports how many were dropped;\ntexts over the --max-chars budget (default 1500) keep a window around\nthe first query match and carry a marker naming --full. --full or\n--max-chars 0 restores the complete payload. Server-side index dedup\nremains open in the mix repo.\n\nFixes #120\nFixes #130\n\n* fix(cli): dedupe on full texts, anchor snippets at word boundaries\n\nReview catches (Greptile, both confirmed against the observed data):\n\n- The dedupe comparison was capped to the first 2,000 normalised chars,\n  but the observed boilerplate preambles run ~3.5 KB — two chunks\n  sharing the preamble with DIFFERENT substance after it compared\n  identical and the second was silently dropped. Compare the full\n  normalised texts; the quick-ratio gates keep the cost bounded.\n\n- The snippet anchor used str.find, so a query term inside a longer\n  word (\"rate\" in \"generated\") stole the window from the real\n  occurrence later in the document. Word-boundary matches now win;\n  a bare substring hit is kept as fallback (\"flow\" in \"cashflow\")\n  since it still beats windowing the head blindly.\n\nRefs #120 #130\n\n* fix(cli): snippet anchor prefers exact words over inflected prefixes\n\nReview catch (Greptile, second pass): the boundary regex had no\ntrailing check, so an earlier \"rates\" outranked a later standalone\n\"rate\" and the window omitted the passage the query actually names.\n\nThe bare exact-word suggestion would regress the other direction —\nwith only \"rates\" present, the anchor would fall to the substring tier\nwhere mid-word noise (\"generated\") wins again. Three tiers instead:\nexact word, then boundary prefix (inflected forms), then substring;\nthe strongest non-empty tier takes the earliest position.\n\nRefs #120 #130\n\n* fix(cli): judge dedupe on what remains after the shared prefix\n\nReview catch (Greptile, third pass on this surface): a global\nsimilarity ratio cannot separate \"mostly shared boilerplate\" from\n\"duplicate content\" — with a dominant shared preamble, distinct tails\nup to ~1/9 of its length keep the ratio above any fixed threshold, and\nthe observed #120 data shows a single load-bearing sentence is exactly\nwhat follows 3.5 KB of boilerplate.\n\nThe global ratio remains the fast gate; above it, the shared prefix is\nstripped and the remainders judged on their own — at or under 120\nnormalised chars they are trailing noise (a revision stamp) and the\nhits collapse, longer remainders are duplicate only if they are\nthemselves similar.\n\nRefs #120 #130\n\n* fix(cli): dedupe collapses only strict extensions without comparing tails\n\nReview catch (Greptile, fourth pass on this surface): the 120-char\nfloor collapsed both-sided short distinct tails without comparing\nthem, losing a short divergent passage after shared boilerplate.\n\nThe distinction is shape, not length: ingestion noise is a strict\nextension — one text exactly the other plus a trailing stamp — and\nonly that shape may collapse uncompared, with the addendum bounded at\nstamp size (40 chars). Divergent continuations, both texts carrying\ntheir own words past the shared prefix, are compared by ratio however\nshort. Where the heuristic cannot tell, it keeps both: a visible\nnear-duplicate is cheap, silently dropped content is not.\n\nRefs #120 #130",
          "timestamp": "2026-08-18T22:18:10+12:00",
          "tree_id": "2f6a8e11d7b6e9edd0b6e21321cc1acaa913378b",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/7cbd2c540c8ac8cc09c4aa1c6147d27f3c16d800"
        },
        "date": 1787049162762,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 1.965,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 250.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 5089.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 20.304,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 561.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 4925.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 270.273,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 613.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 3700,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 13.144,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 879.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 7608.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 119.219,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4871.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 8387.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "3d447ea7a4523777dd454fd75f5af9cdc06ed6ab",
          "message": "feat(skills): gaspatchio-workbook-conversion — the conversion discipline as a skill (#114)\n\n* feat(skills): gaspatchio-workbook-conversion — the conversion discipline as a skill\n\nThe dedicated conversion skill promised at #41's close, specced by #95\nfrom three independent conversions of the same workbook. It owns the\ndiscipline the other skills don't: the reader trust boundary (fastexcel\ntruncates floats to ~9 sig figs under a String dtype — proven against\nraw sheet XML before any value becomes gold standard), the three-proof\nstructure that makes any residual localise to one question, defined-name\nassumption extraction, faithful-quirk rules, and full-grid\nreconciliation over headline columns.\n\nRegistered in skills.toml between discovery and building; routing table,\ninstall count/list, and generated manifests updated.\n\nFixes #95\n\n* test(skills): execute the workbook-conversion skill's factual claims\n\nThe skill is a document of claims: fastexcel mangles float precision\nbehind a String-dtype inference, round_charge=/.clip()/.round() exist on\nthe API it names, the sibling skills and reference files sit where it\nsays. None of that was guarded — the skill could silently outlive\nreality. Six tests now execute the claims: the truncation repro from the\nHARD GATE table runs live (deliberately failing the day a fastexcel\nrelease fixes the truncation, which is the wanted signal to update the\nskill), cross-references are checked on disk, and the named API surface\nis pinned by signature. Probes are the two from the skill's own table\nthat survive xlsxwriter's %.16g write, so any measured loss belongs to\nthe reader alone; each test was proven red-capable by mutation.\n\nDesign note: ref/30-llm-helpers/specs/2026-08-18-workbook-conversion-\nskill-hardening-design.md.\n\nServes Audit-by-default: the skill's claims now carry executable proof.\nRefs #95.\n\n* docs(skills): xl-marinade 0.3.0 floor and the live caveat set\n\nThe discovery reference's install guidance predated 0.3.0: no version\nfloor, and a caveat paragraph describing #12's first-row formula_pattern\n— fixed upstream 2026-08-15 (formula_pattern is now the dominant\nformula, though it still cannot signal a mixed binding, so the\nread-the-distribution recipe stays). The floor matters because pre-0.3.0\nextracts differ in ways the recipes assume away. The two caveats still\nopen upstream (#14 agent_cells semantics, #16 invisible within-column\nrecurrences) are now stated where the recipes are, verified against the\nlive issue tracker 2026-08-18. The conversion skill gets a two-line\nTooling pointer only — the discovery reference owns the detail, per the\nskill's own ownership table.\n\nRefs #95.\n\n* chore(plugin): bump to 1.1.0 so installed plugins receive the new skill\n\n/plugin update no-ops on an unchanged version string even when skill\ncontent changed — observed twice (this plugin and xl-marinade's). At\n1.0.0 an installed user would never receive the eighth skill. Minor\nbump for a new skill; manifests regenerated via gen_skill_manifests.py\n(version-only diffs).\n\nRefs #95.",
          "timestamp": "2026-08-19T08:43:48+12:00",
          "tree_id": "f9c451603dbdbc86e42a50a3bb605a904a4c5ae7",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/3d447ea7a4523777dd454fd75f5af9cdc06ed6ab"
        },
        "date": 1787087145840,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.628,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 208.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2756.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.701,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 578.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2967.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 526.679,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 584.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1898.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.616,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 875.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4062.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 255.933,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4831.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3907.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "88f8f1dcf72978e8cc1d963517c1d48b8f185e9a",
          "message": "chore(deps): bump ruff 0.11.12 → 0.16.3, with the lockfile (#144)\n\n* chore(deps): bump ruff 0.11.12 -> 0.16.3, with the lockfile\n\nReplaces the ruff half of dependabot #124, which died in CI at uv sync\n--locked because the bump landed without a lockfile update. The pip\ngroup also bundled polars 1.42.1 -> 1.43.2 into the same PR — polars is\nthe engine under everything and gets its own deliberately-tested pass\n(with cargo #1), so the group PR is being split rather than merged.\n\nVerified under 0.16.3: uv sync --locked clean; skills suite 144 passed;\nthe 5 excel.py doctest failures in the local --doctest-modules\ninvocation are byte-identical on main under the old pin (pre-existing,\ndate-dependent, not the bump). Formatter drift measured, not applied:\n0.16.3 wants to reformat 20 more files and reports ~21 new findings on\nthe existing debt baseline — CI does not gate ruff, and that churn\nbelongs to a deliberate cleanup commit, not a version bump.\n\n* fix(docstrings): pin the snippet gate's rule set — it floated on ruff defaults\n\nThe docstring harness lints every example with 'ruff check --isolated',\nwhich inherits whichever rule set the installed ruff defaults to. Ruff\n0.16 added import-sorting to its defaults, so the version bump turned\n70 examples red in CI — I001 on two-line import blocks — with no code\nhaving changed. Same species as the #137 lesson: state a gate reads\nmust be written on the gate's own schedule, and a dependency's default\nselect is someone else's schedule.\n\nThe invocation now pins --select E4,E7,E9,F — the correctness rules the\ngate has always actually enforced (syntax errors, undefined names,\nunused imports). Import-order style in examples becomes a deliberate\nchoice for a future cleanup, not a side effect of an upgrade. A new\nharness test locks this: an unsorted-but-valid import block must lint\nclean, red-first verified under 0.16.3 before the pin.\n\nVerified after: 15 harness tests green; 74 examples across the\npreviously-failing files (date.py, excel_functions/, projection.py)\ngreen under 0.16.3.",
          "timestamp": "2026-08-19T16:15:25+12:00",
          "tree_id": "10999482167a0fd61b8b7ed7bfa69410e5ecafb7",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/88f8f1dcf72978e8cc1d963517c1d48b8f185e9a"
        },
        "date": 1787114270949,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.63,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 202.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2754.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 39.958,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 556.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2502.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 523.651,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 599,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1909.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.678,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 878.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4052.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 260.676,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4820.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 3836.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "942513b92feb2ac449482f9852208900d7fe3660",
          "message": "feat(projection): cumulative_survival accepts survival-shaped input (#143)\n\nA reserving workbook hands you a combined persistency px = (1-qx)(1-lapse)\nfar more often than a bare decrement rate — and the only way to feed it\nto cumulative_survival was to invert it so the method could undo the\ninversion. 1-(1-px) is exact only while px >= 0.5 (Sterbenz); a VM-20\nshock-lapse year sits at px = 0.199, where the round trip loses bits\nthat a strict tie-out sees (vm20 room: 2.1e-17 vs the workbook's cached\nvalues where the direct product is 0.0e0). The error is tiny and\navoidable for free — and it lived in the method whose name is exactly\nwhat a reserving model reaches for.\n\ncumulative_survival(from_survival=True) cumulates the factors directly,\nno inversion anywhere, list and scalar paths both; the timing parameters\nmean the same thing in both shapes. The docstring documents the\ninversion hazard next to the timing notes (per the #42 precedent that\nadjacent traps belong in the method's own contract) and carries an\nexecutable example whose output table is identical to the rate-shaped\nexample — same numbers, honest input shape.\n\nServes Meet-you-where-you-are (accept the shape the source hands you)\nand Audit-by-default (bit-exact against the gold standard where the\nround trip is not). Closes #118.\n\nVerified: 65 projection tests + 42 docstring examples green; stubtest\nclean across 266 modules; ruff/mypy/format deltas zero vs baseline\n(1/51/4 findings and 4 mypy errors are main's pre-existing debt).",
          "timestamp": "2026-08-19T16:45:12+12:00",
          "tree_id": "9f272ed53a46bb148e179edcb2b943a231e23289",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/942513b92feb2ac449482f9852208900d7fe3660"
        },
        "date": 1787116132475,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.754,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 201.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2663.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 41.357,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 541.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2418,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 552.243,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 583,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1810.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 31.586,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 305.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3165.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 242.763,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4873.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4119.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "a61ed0032da0e2aae3248a46f65517986646f436",
          "message": "test(docstrings): make the pinned rule-set guard fully binding (#146)\n\n* test(docstrings): make the rule-set guard fully binding\n\nCode review on the pin surfaced three gaps. The guard test's\nexcept-ImportError skip was dead code — lint() reports a missing ruff\nas an issue string, never an exception — so a ruff-less environment\nwould have failed with the misleading floating-defaults message; the\nskip now keys off the issue text. The pin was also only half-guarded:\nnothing proved E4 or E7 actually fire, so a trimmed select would pass\nthe suite silently — the new families test pins all four (E401, E711,\nE999, F821) and goes red under a mutated select (verified). And the\nfixture was mislabelled unsorted_imports when its imports are correctly\nordered — I001 fires on the missing blank line between sections.\n\n* docs(ref): align the docstring README with the correctness-only gate\n\nThe README still told authors that import ordering, formatting, and\nline length fail CI — contradicting the gate's pinned E4,E7,E9,F rule\nset. A contributor following it would re-add style rules to the select\nand re-red the ~70 examples the pin just rescued. Style guidance stays\nas recommendation; only correctness is stated as gated.\n\n* test(docstrings): pin what E999 actually guards — the rewrite, not the select\n\nGreptile round 2: ruff's parser diagnostics are select-independent\n(verified at 0.16.3 — identical invalid-syntax output with and without\nE9), so the families test's E999 case could never detect E9's removal.\nE9 leaves the firing cases; syntax surfacing gets its own test pinning\nthe harness's rewrite to the stable E999 prefix — which is genuinely\nversion-fragile: 0.11.12 emits code null for the same input and the\nrewrite misses it, observed live when a stray resync downgraded the\nvenv. That pin now reds at the bump that changes the shape again.\n\n* docs(ref): imports that do not resolve are the execution check's catch\n\nThe lint bullets implied the pinned rules detect broken imports — ruff\nnever imports anything, so an unresolvable import passes the lint and\nonly fails at execution. Say which gate catches what.",
          "timestamp": "2026-08-19T19:38:02+12:00",
          "tree_id": "bddd74db56de4b32538e4ad037fe38246d092c1d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/a61ed0032da0e2aae3248a46f65517986646f436"
        },
        "date": 1787126503078,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.701,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 199.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2702.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 42.053,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 549.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2378,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 557.139,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 590.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1794.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 24.427,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 897,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4093.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 240.593,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4851.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4156.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1b7e7103f28a1c5414e80de5709b4b39175f31a8",
          "message": "chore(deps): bump the github-actions group with 2 updates (#123)\n\nBumps the github-actions group with 2 updates: [google/osv-scanner-action/.github/workflows/osv-scanner-reusable-pr.yml](https://github.com/google/osv-scanner-action) and [google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml](https://github.com/google/osv-scanner-action).\n\n\nUpdates `google/osv-scanner-action/.github/workflows/osv-scanner-reusable-pr.yml` from 2.3.8 to 2.5.0\n- [Release notes](https://github.com/google/osv-scanner-action/releases)\n- [Commits](https://github.com/google/osv-scanner-action/compare/v2.3.8...v2.5.0)\n\nUpdates `google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml` from 2.3.8 to 2.5.0\n- [Release notes](https://github.com/google/osv-scanner-action/releases)\n- [Commits](https://github.com/google/osv-scanner-action/compare/v2.3.8...v2.5.0)\n\n---\nupdated-dependencies:\n- dependency-name: google/osv-scanner-action/.github/workflows/osv-scanner-reusable-pr.yml\n  dependency-version: 2.5.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml\n  dependency-version: 2.5.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Matt Wright <1277725+mrmattwright@users.noreply.github.com>",
          "timestamp": "2026-08-21T15:57:38+12:00",
          "tree_id": "1b77f2ffc0fe3b0fa123ce68ba7ca7bb58e145a5",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/1b7e7103f28a1c5414e80de5709b4b39175f31a8"
        },
        "date": 1787285989707,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.801,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 206.9,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2630.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 34.521,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 571.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2896.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 519.688,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 594.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1924.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 23.612,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 903.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4235.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 238.14,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4850.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4199.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "5a2d4fa1ee4603f5fe9f84b9ba11e55fcbaf83a5",
          "message": "fix: the docs tell the truth — GSP-128 batch (runner point_id, L2 data, skill examples, nits, pickle wire) (#148)\n\n* fix(cli): auto-detect point_id as a policy-ID column (GSP-134)\n\nEvery tutorial model-point file names its ID column point_id, but the\nrunner's auto-detect candidates only knew policy-flavoured names — so\nall seven documented run-single-policy commands failed unless the user\nadded --policy-id-column. point_id joins the candidates ahead of the\ngeneric id, so a frame carrying both resolves to the domain name.\n\nServes Meet-you-where-you-are: the documented commands now run as\nprinted against the data shapes we ourselves ship.\n\n* fix(tutorials): L2 lapse tables cover the timeline they project (GSP-135)\n\nprojection.set materialises months 0..n inclusive — the n+1 boundary —\nbut step 03's lapse table stopped at month 11 (12-month projection) and\nstep 04's at month 23 (24-month projection), so both steps crashed on\ntheir own documented 'uv run python model.py' with a lookup miss at the\nboundary month. Each table gains its boundary month at the flat ultimate\nrate, the READMEs' row counts and month-list claims move with the data,\nand Tutorial Smoke now runs both steps so data/model drift goes red in\nCI instead of in a reader's terminal.\n\nThe crash itself is Sharp-knives working as designed (on_missing raises\nrather than silently NaN-ing) — the data was lying, not the lookup.\n\n* docs(skills): four model-building examples now run as printed (GSP-136)\n\nEach crashed verbatim, proven by execution in the 2026-08-20 skills\nsweep, and each fix was re-executed before landing:\n\n- from_par_rates example used non-contiguous tenors, violating the\n  constraint stated two lines below it — now 1..10 annual.\n- fit_svensson example passed 5 knots against a 6-parameter form —\n  now 6, with the >=6 constraint stated inline.\n- accumulate(multiply=1.0) scalar shorthand documented in three places;\n  the kernel requires a list-shaped multiply — all three now build the\n  ones from the flow column and say why. The neighbouring\n  '.list.cumsum()' claim fell to the same execution check (no such\n  attribute) and is corrected alongside.\n- The select-ultimate snippet imported TableBuilder but called Table —\n  imports now match the calls.\n\nA new claims-as-tests module executes the fenced code straight out of\nthe markdown (the #114 pattern), including a pin that scalar multiply\nstill raises — if the kernel starts broadcasting it, the caveats become\nfiction and the suite says so. The recursive-patterns relative link to\ngaspatchio-docs also gains its missing '../' (GSP-137 checklist item)\nsince the surrounding lines were already under edit.\n\n* docs: six documentation nits — paths, ladder numbering, stale names (GSP-137)\n\nAll pre-existing, all verified against the tree before fixing:\n\n- Discovery's CLI reference pointer now names the real path\n  (bindings/python/docs/cli-knowledge-command.md).\n- The extending skill and its performance ladder disagreed on level\n  numbering (SKILL said Rust=L6/accessors=L4-5; the ladder's headers\n  and all four decision examples say Rust=L4, column=L5, frame=L6).\n  The ladder's internally consistent numbering wins — SKILL.md's four\n  mentions and the ladder's one self-contradicting table row move to it.\n- Non-canonical skill names in prose (gaspatchio-discovery,\n  gaspatchio-building, gaspatchio-reconciliation, extending-gaspatchio)\n  now use the canonical directory names the routing table teaches.\n- Stale 'gaspatchio-core' repo naming in AGENTS.md's contributor half\n  and the accessor template — the repo is gaspatchio/gaspatchio and the\n  import is gaspatchio (copilot-instructions regenerated).\n- tutorials/README's directory tree claimed a level-5 README.md and\n  charts.py that do not exist and missed the 05-stochastic step — the\n  tree now matches the tree.\n- L3-typed step 07's run block used a source-tree path; it now follows\n  the tutorial/... convention every sibling step documents.\n\n* docs(rollforward): the kwargs wire is pickle, not JSON (GSP-138)\n\nTwo docstrings in the lowering pass described plugin_kwargs as\nJSON-serialisable. The dict actually crosses the plugin boundary as\npickle protocol 5 — Polars pickles plugin kwargs and the Rust kernel\ndeserialises them via serde into RollforwardKwargs — and JSON appears\nonly in the fingerprint path's canonical form. The serialization\ncontract is exactly what an extender must get right, so the docstring\nnow states the real one. Divergence #7 from the rollforward deep-read;\nthe remaining six carry roadmap verdicts under GSP-131.\n\n* fix(tutorials): the L2 truth cluster and step-07 command the review caught\n\nReview round on the batch (15 verified findings; this commit takes the\ntutorial half). The serious ones were mine: the step-04 sentence this PR\nintroduced conflated duration_mth_t with af.month — duration counts from\nISSUE, so only a valuation-date policy sees [0..24]; POL003 (issued 22\nmonths earlier) sees [22..46] and matures at projection month 2. That\nalso fell the neighbouring pre-existing lies, all fixed against executed\nvalues: 'full 24 months of cash flows' (POL002 contributes months 0–16,\nPOL003 months 0–1), the 'high claims' misattribution of POL003's small\npv_net_cf (claims ~25.6 vs ~231.9 commissions — the driver is maturity\ntruncation), the phantom '20' maturity_month, and every remaining\n[0..23]/(0–11) range in both steps' READMEs and models.\n\nThe step guard moves to where it runs locally too: both step models now\ncarry expected_output.txt and tests/skills/test_tutorial_outputs.py\ndiffs them (numeric drift reds, not just crashes — the CI loop's comment\nnow claims exactly what it delivers). Step-07's run command is restored\nto a form that works from a repo checkout — its only real audience,\nsince tutorial init never ships steps. The tutorials README tree now\nmatches the tree: typed L3, 07-rollforward, reconcile_full, benchmark,\nstress. The point_id test docstring no longer overclaims 'every'\ntutorial (the L2 steps use policy_id).\n\n* docs(skills): a running balance is a cumulative sum, not an accumulate incantation\n\nThe review's best catch: af.x.cum_sum() is a first-class proxy method\nthat applies within each policy's list, and its own docstring names\nrunning balances as a use case — so the three sites that taught\nmultiply=flow*0.0+1.0 now teach the closed form instead\n(initial + flow.cum_sum(), verified equal to the kernel result). That\nalso retires the NaN-poisoning hazard the ones-vector carried: a null\nor NaN in the flow no longer infects the multiplier. accumulate() keeps\none canonical statement of its list-shaped multiply constraint, where\nthe method is actually taught.\n\nThe guards tighten to match their stated guarantee: the scalar-multiply\nscan now catches multiply=1 / 1.0 / pl.lit(1.0) across every skill\nmarkdown file (multiply=1 raises the identical ComputeError, verified),\nand the fence extractor adopts the evals oracle grammar (case-insensitive\ntag, CRLF, trailing whitespace) with a keep-in-sync note. The\nbroadcast-vs-better-error framework question is out-scoped to GSP-156.",
          "timestamp": "2026-08-21T20:27:54+12:00",
          "tree_id": "19652f0d276e1e467e31203f425a52f83ff4ee62",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5a2d4fa1ee4603f5fe9f84b9ba11e55fcbaf83a5"
        },
        "date": 1787301899483,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 1.871,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 242,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 5345.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 20.011,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 573.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 4997.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 539.133,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 572.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1854.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 11.136,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 911.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 8980.1,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 115.104,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4903,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 8687.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "4c897e0500e7fb0e2d944b9c7f9344ca25beaf39",
          "message": "chore(deps): bump transitive h2 0.4.12 → 0.4.16 for RUSTSEC-2026-0258 (#149)\n\nThe scheduled Security Scan went red on 2026-08-21 when the advisory\npublished — h2 reaches us only through object_store ← polars's cloud\nreaders, a path gaspatchio never exercises (local parquet/CSV only),\nbut unlike the quick-xml pair the fixed version is inside our semver\nrange, so the honest remediation is the bump, not a filter entry.\nLockfile-only change; cargo check clean.",
          "timestamp": "2026-08-22T09:45:14+12:00",
          "tree_id": "d31c34a5c3b23fa96438426053ac613dab43f507",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/4c897e0500e7fb0e2d944b9c7f9344ca25beaf39"
        },
        "date": 1787350822942,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.988,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 213.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2507.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 66.991,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 558.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 1492.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 1237.842,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 560.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 807.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 29.274,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 907.7,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3416,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 241.537,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4880.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4140.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "2c96d1a7f0cede444da413eacf43267ec54cb463",
          "message": "chore(lint): tier 1 config truth — CPY001 matches the SPDX convention, tests ignores match enforcement (#150)\n\nTwo config-only changes (GSP-148), zero code edits. All 510 Python files\ncarry REUSE-style SPDX-FileCopyrightText headers, but CPY001's default\npattern doesn't recognise them — 557 findings against fully-compliant\nfiles, and a genuinely missing header invisible in the noise. notice-rgx\nnow matches the real convention; the residue is zero, so the rule is a\nworking local gate. The tests tree adds D101/D102/D103/PLC0415 to its\nignores — test names are the documentation (the tests/rollforward block\nalready said so) and per-test local imports are deliberate; D100 stays\nenforced because a module docstring in a test file is worth writing.\n\nFindings: 7134 -> 5928. Every remaining finding is one we'd accept a\npatch for, which is what makes tiers 2-4 measure real debt.",
          "timestamp": "2026-08-22T16:23:27+12:00",
          "tree_id": "adf9e943bbc46d3b693a17f22e091ec88b990894",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/2c96d1a7f0cede444da413eacf43267ec54cb463"
        },
        "date": 1787375261846,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.871,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 205.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2583.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 43.927,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 547.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2276.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 25.038,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 870.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3993.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 246.023,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4832.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4064.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
          "id": "67f07b65913e088b880c231b571863bf003ab848",
          "message": "chore(lint): tier 2 — apply the safe autofixables, driven to the fix/format fixpoint (#151)\n\nOne ruff check --fix pass (safe fixes only; the 1,393 unsafe-fixables are\ndeliberately untouched) on top of tier 1's config: 1,730 fixes across 55\nrule families, 5,928 findings -> 4,200, zero safe fixes remaining. The\nfix set was driven to a joint fix/format fixpoint: 15 files the fixer\nmade format-dirty were formatted; pre-existing format debt shrank 164 ->\n156 files and the tier-3 sweep stays untouched.\n\nThree fixer-vs-reality conflicts resolved by hand, each with the intent\nnow stated in place so it cannot be 'fixed' away again:\n\n- test_excel_round: F401 replaced the import inside pytest.raises with\n  pass — the import IS the assertion (the dead plugins.round wrapper\n  must stay gone). Restored with noqa and a comment.\n- _dispatch_autopatch: B010 rewrote the deliberate setattr of __dir__\n  into direct method assignment — runtime-identical, but mypy rejects\n  method-assign and stubtest then refuses the whole package. Reverted\n  with the reason documented.\n- D413 retired to extend-ignore: its fix and docstring-code-format\n  oscillate forever (proven — fix 28, format strips 3 files, repeat).\n  The formatter wins, same policy as COM812.\n\nSuite: 3064 passed, 0 failed on this tree (GSP-149).",
          "timestamp": "2026-08-23T16:58:48+12:00",
          "tree_id": "310f5639712f279d2096c46ab6923547b443ebfc",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/67f07b65913e088b880c231b571863bf003ab848"
        },
        "date": 1787462601125,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.682,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 196.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 2716,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 33.689,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 560.2,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 2968.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 511.306,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 599.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 1955.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 29.828,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 885.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 3352.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 248.519,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 4842.5,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4023.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          }
        ]
      }
    ]
  }
}