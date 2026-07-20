window.BENCHMARK_DATA = {
  "lastUpdate": 1784527447754,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Aggregation Surface Benchmarks": [
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
          "id": "b89205ba8938cedd55067243082eefe26af2cb65",
          "message": "ci(evals): run OSS benchmarks on free standard runners; gate private suites\n\nThe benchmark jobs requested larger runners (ubuntu-latest-m / windows-m) that\nare only defined on the private org, so they queued forever on the public repo.\nSwitch the public-safe suites (Criterion, Model, Aggregation) to free standard\nrunners (ubuntu-latest / windows-latest), which are unlimited for public repos.\n\nGate the jobs that cannot run publicly to the private repo:\n- comparison-benchmarks (Gaspatchio vs Lifelib) clones the private\n  opioinc/gaspatchio-benchmarks reference data via a deploy key;\n- skill-evals + capability-matrix need paid ANTHROPIC/OPENAI API keys.\nThese stay disabled on the public repo until their secrets are provisioned.",
          "timestamp": "2026-07-07T14:42:36+12:00",
          "tree_id": "a424805d092e630ba336b1c3aaee85beae6b2325",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b89205ba8938cedd55067243082eefe26af2cb65"
        },
        "date": 1783392596786,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.277,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.283,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.318,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3610.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3144.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 45.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 9.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 4.66,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.89,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.391,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2557.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 41.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.266,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.291,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.314,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4413.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4321.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 314.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 105.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.98,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.166,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3158.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 504.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.693,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.847,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.974,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4609.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4550.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3113.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 840.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.71,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.083,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3217.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3105.9,
            "unit": "MB"
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
          "id": "e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7",
          "message": "ci(evals): enable Gaspatchio vs Lifelib comparison on the public repo\n\nBENCHMARKS_DEPLOY_KEY (read-only deploy key for opioinc/gaspatchio-benchmarks)\nis now configured as an Actions secret on gaspatchio/gaspatchio, so the\ncomparison job can clone the lifelib reference data. Restore its normal trigger\n(schedule / dispatch / push-main / benchmark label); it runs on the free\nstandard runners with the other public suites and publishes to dev/comparison.",
          "timestamp": "2026-07-07T14:57:55+12:00",
          "tree_id": "9765b961fc48b4d840b2c4c8a2229bb01a04a978",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7"
        },
        "date": 1783393506696,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.238,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.245,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.283,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 4201.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3533.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 50.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.38,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.87,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.363,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2754.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 32.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 1.985,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.015,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.107,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 5037.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4746.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 314,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 97.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.23,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 2.925,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3418.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 506.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 19.287,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 19.486,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 19.685,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 5184.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 5080,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3064.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 750,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.09,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 29.096,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3436.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3193.9,
            "unit": "MB"
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
        "date": 1783395014163,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.281,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.287,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.324,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3558.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3086.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 46.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 8.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 5.57,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.89,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.396,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2525.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 41.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.288,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.312,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.383,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4370.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4196.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 310.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 105.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.95,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.198,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3127,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 500.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 22.013,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.24,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.269,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4542.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4490.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3110.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 887.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.5,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.152,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3210.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3189,
            "unit": "MB"
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
          "id": "2a761959f16118a54710c92dcaefbe319aad46d1",
          "message": "ci(evals): give Criterion Windows headroom (40m timeout + rust-cache)\n\nThe Criterion benchmark job timed out at 20 minutes on the free\nwindows-latest runner: an uncached cargo bench compiles polars +\ncriterion from scratch, which exceeds 20m on Windows (Linux fits).\nGitHub cancelled the job, so dev/bench-windows never populated.\n\nBump the job timeout to 40m and add Swatinem/rust-cache. Only compiled\ndependencies are cached; the bench crate is rebuilt and run fresh each\ntime, so measured numbers stay accurate while warm builds land well\ninside the window.",
          "timestamp": "2026-07-07T03:22:29Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/2a761959f16118a54710c92dcaefbe319aad46d1"
        },
        "date": 1783397087885,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.27,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.275,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.321,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3703.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3115.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 45.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 5.03,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.86,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.39,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2564.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 39.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.27,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.294,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.391,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4405.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4182.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 313,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 96.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.25,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.16,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3164.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 498.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.915,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.095,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.243,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4563.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4495.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3076.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 739.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.16,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.168,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3208.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3180.6,
            "unit": "MB"
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
        "date": 1783418813833,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.25,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.255,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.309,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 4000,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3236.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 45.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 11.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 3.83,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.83,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.377,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2652.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 39.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.068,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.104,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.17,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4835.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4608.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 314,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 119.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.63,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.01,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3322.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 495.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 19.96,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 20.199,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 20.305,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 5010,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4924.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3068.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 829.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.7,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 29.395,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3401.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3069.7,
            "unit": "MB"
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
        "date": 1783418856694,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.294,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.301,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.334,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3401.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 2994,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 46.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 6.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 7.4,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.9,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.406,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2463.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 40.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.251,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.279,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.379,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4442.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4203.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 311.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 104.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.98,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.159,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3165.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 509.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.654,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.797,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.964,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4618.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4552.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3062.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 788,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.89,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 30.661,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3261.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3059.6,
            "unit": "MB"
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
        "date": 1783459758984,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.266,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.271,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.324,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3759.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3086.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 46.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.63,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.84,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.383,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2611,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 34.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.242,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.263,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.306,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4460.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4336.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 313.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 110.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.83,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.98,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.122,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3203.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 508.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.577,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.777,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.711,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4634.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4606,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3068.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 702.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.37,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 30.526,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3275.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3129.4,
            "unit": "MB"
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
        "date": 1783459766997,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.278,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.284,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.331,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3597.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3021.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 45.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 12.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 3.66,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.86,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.397,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2518.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 33.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.243,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.266,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.366,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4458.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4226.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 307.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 108.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.83,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.161,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3163.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 492.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.807,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.001,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.205,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4585.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4503.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3079.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 711.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.33,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.219,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3203.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3007.2,
            "unit": "MB"
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
        "date": 1783464113927,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.268,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.274,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.306,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3731.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3268,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 48.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.75,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.9,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.363,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2754.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 33.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.167,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.194,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.273,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4614.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4399.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 313.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 111.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.82,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 2.992,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3342.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 497.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 20.895,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.093,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.198,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4785.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4717.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3106.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 685.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.53,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 29.663,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3371.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3259.9,
            "unit": "MB"
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
          "id": "56797ef297e3cd76a5a9de4b474a89ce1fe7d28e",
          "message": "fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes (#11)\n\n* fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes\n\nThird and deepest layer of the auto-search OOM fix: the gate's INPUT was\nbroken. Probe peaks are measured as RSS delta-over-baseline -- but in a\nprocess with retained allocator pools, a batch can be served entirely\nfrom pooled memory: RSS never grows and the sampler reads ~0. Observed\nlive on CI (probes: [b1/streaming=0MB+fits]) -- any prediction\nmultiplied from that zero is blind, so the gate launched an unaffordable\nprobe and the runner died again. The budget also collapsed across bench\ncells (7148 -> 3094 MB) because base RSS includes the pools.\n\nLibrary: floor each batch's measured peak with the materialised frame's\nestimated_size() -- the frame's bytes are live memory at peak regardless\nof where the allocator got them. This is the same floor the policy axis\nhas always applied to its seed measurement (_spill/_aggregated).\n\nBench: run each grid cell of run_scenario_benchmarks.py in a fresh\ninterpreter (the pattern scenario_batch_search_bench already uses for\nits floor workers): clean allocator baseline, honest probe measurements,\nfull budget per cell -- and a kernel-killed cell now loses one cell, not\nthe whole run. Child stderr is inherited so probe-ladder lines stream\ninto the CI log.\n\nNew test pins the pool-reuse lie: with the sampler forced to read 0 and\na budget the frame fits at b=1, the b=4 rung must still be gated and the\nrecorded rung peak must be the floor, not the lie.\n\n* fix(evals): distinguish cell kills from cell errors; bound cell wall clock\n\nReview feedback (Greptile, both accepted): the subprocess wrapper treated\nevery childless exit as a benign skip and had no per-cell timeout.\n\n- A clean nonzero exit with no result is a real error (import failure,\n  bug) -- raise so CI fails instead of publishing an incomplete benchmark\n  as green. Only signal kills (negative returncode, e.g. kernel OOM) and\n  timeouts are tolerated as one-cell losses, which is what the isolation\n  is for.\n- Cap each cell at 30 min (heaviest legitimate cell ~6 min) so one wedged\n  cell cannot eat the job timeout and lose every other cell's output.\n\nVerified: happy path returns metrics; a crashing child (missing points\nfile) raises RuntimeError in the parent.",
          "timestamp": "2026-07-07T22:34:49Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/56797ef297e3cd76a5a9de4b474a89ce1fe7d28e"
        },
        "date": 1783464184411,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.269,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.274,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.298,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3717.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3355.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 47.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 12.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 3.69,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.92,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.383,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2611,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 31.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.137,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.164,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.262,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4679.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4420.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 319.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 99.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.21,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 2.988,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3346.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 499.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 20.792,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 20.958,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.059,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4809.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4748.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3099.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 598.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 5.18,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 29.603,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3378,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3113.2,
            "unit": "MB"
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
        "date": 1783465426005,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.279,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.285,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.314,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3584.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3184.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 46.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 10.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 4.63,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.91,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.387,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2584,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 33.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.233,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.256,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.336,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4478.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4280.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 311.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 104.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.112,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3213.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 502.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.613,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.8,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.964,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4626.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4552.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3082.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 645.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.77,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.021,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3223.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3040,
            "unit": "MB"
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
        "date": 1783469610667,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.28,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.285,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.336,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3571.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 2976.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 51.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 7.24,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.85,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.389,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2570.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 36,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.237,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.259,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.329,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4470.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4293.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 312.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 114.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.74,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.114,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3211.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 503.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.57,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.753,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.757,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4636.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4596.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3068.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 865.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.55,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 30.499,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3278.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 3139.1,
            "unit": "MB"
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
        "date": 1783474683035,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.265,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.271,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.302,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3773.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3311.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 46,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.22,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.9,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.375,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2666.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 34.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.179,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.2,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.231,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4589.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4482.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 315.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 106.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.009,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3323.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 501.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 20.848,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.01,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.171,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4796.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4723.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 3095.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 713,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.34,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 29.647,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3373,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2958.3,
            "unit": "MB"
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
        "date": 1783486288639,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.297,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.303,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.327,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3367,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3058.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 51.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 10.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 5.14,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.93,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.404,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2475.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 31.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.352,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.381,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.406,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4251.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4156.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 264.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 85,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.12,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.242,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3084.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 382.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 22.064,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.243,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.535,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4532.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4437.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2610.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 502.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 5.19,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.424,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3182.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2689.2,
            "unit": "MB"
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
        "date": 1783501420347,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.296,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.302,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.326,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3378.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3067.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 50.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 7.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.79,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.93,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.402,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2487.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 37.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.266,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.293,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.383,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4413.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4196.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 269.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 112.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.39,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.96,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.216,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3109.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 329.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.82,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.977,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.263,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4583,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4491.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2633.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 747.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.52,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 31.621,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3162.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2225.7,
            "unit": "MB"
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
        "date": 1783922670345,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.262,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.268,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.298,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3816.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3355.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 50.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 9.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 5.18,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.9,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.369,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2710,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 43.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.083,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.116,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.192,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4800.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4562,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 272.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 54.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 5.04,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.97,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.058,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3270.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 378.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 20.124,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 20.318,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 20.497,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4969.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4878.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2628.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 478.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 5.5,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 30.175,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3314,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2799.4,
            "unit": "MB"
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
        "date": 1784527447091,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.154,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.159,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.185,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 6493.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 5405.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 54.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 12.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 4.31,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.86,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.254,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 3937,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 38.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 1.225,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 1.246,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 1.313,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 8163.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 7616.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 281.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 93,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.03,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 0.95,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 2.38,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 4201.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 388.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 12.036,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 12.23,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 12.354,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 8308.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 8094.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2708.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 641.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.22,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/100K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/100K-spill-wall",
            "value": 22.321,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 4480.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2754.4,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}