window.BENCHMARK_DATA = {
  "lastUpdate": 1783419187645,
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
      }
    ]
  }
}