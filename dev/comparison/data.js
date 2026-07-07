window.BENCHMARK_DATA = {
  "lastUpdate": 1783418926786,
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
      }
    ]
  }
}