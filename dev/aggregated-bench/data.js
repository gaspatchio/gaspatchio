window.BENCHMARK_DATA = {
  "lastUpdate": 1785302799386,
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
        "date": 1785035784857,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.294,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.302,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.304,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3401.4,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3289.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 56.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 5.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 9.64,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.372,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2688.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 39,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.103,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.183,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.175,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4755.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4597.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 280.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 74.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.78,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-speedup",
            "value": 1,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/10K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/10K-spill-wall",
            "value": 3.045,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3284.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 422.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 20.1,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 20.34,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 20.56,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4975.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4863.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2615.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 702.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.72,
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
            "value": 29.684,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3368.8,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2128.7,
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
          "id": "e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd",
          "message": "Issue-tracking scheme: triage labels, templates, release notes, public roadmap policy (#34)\n\n* chore(github): issue templates with auto-triage labels and release-notes config\n\nBug reports now open with bug + needs-triage applied automatically, and the\ntemplate points insurer-employed reporters at the private email intake from\nSECURITY.md. release.yml gives auto-generated release notes keyed off PR\nlabels (bug / enhancement / documentation), with ignore-for-release as the\nopt-out.\n\n* docs: public roadmap policy and bug-lifecycle trail\n\nDocuments the label lifecycle a reporter can watch (needs-triage -> confirmed\n-> pending-release -> released via milestone) and the placeholder-issue model\nfor larger features (roadmap + exploring/building/shipped), including the\ncomment-before-building note for contributors and a non-commitment disclaimer.",
          "timestamp": "2026-07-27T10:20:08+12:00",
          "tree_id": "069536837f93ad61d285546ce8eed09794dec759",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd"
        },
        "date": 1785104873996,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.325,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.334,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.321,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3076.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3115.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 56.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 11.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 4.83,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 1.04,
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
            "value": 42.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.274,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.3,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.338,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4397.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4277.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 275.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 98.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.79,
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
            "value": 3.13,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3194.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 354.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.54,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.697,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.954,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4642.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4555,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2601.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 624.5,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.17,
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
            "value": 30.313,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3298.9,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2419.8,
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
          "id": "e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd",
          "message": "Issue-tracking scheme: triage labels, templates, release notes, public roadmap policy (#34)\n\n* chore(github): issue templates with auto-triage labels and release-notes config\n\nBug reports now open with bug + needs-triage applied automatically, and the\ntemplate points insurer-employed reporters at the private email intake from\nSECURITY.md. release.yml gives auto-generated release notes keyed off PR\nlabels (bug / enhancement / documentation), with ignore-for-release as the\nopt-out.\n\n* docs: public roadmap policy and bug-lifecycle trail\n\nDocuments the label lifecycle a reporter can watch (needs-triage -> confirmed\n-> pending-release -> released via milestone) and the placeholder-issue model\nfor larger features (roadmap + exploring/building/shipped), including the\ncomment-before-building note for contributors and a non-commitment disclaimer.",
          "timestamp": "2026-07-26T22:20:08Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd"
        },
        "date": 1785133412058,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.338,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.348,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.333,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 2958.6,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3003,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 59.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 9.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 6.43,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 1.05,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.409,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2445,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 40.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.325,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.353,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.43,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4301.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4115.2,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 260.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 89,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.92,
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
            "value": 3.234,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3092.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 363.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 22.309,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.466,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.729,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4482.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4399.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2621.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 629.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.17,
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
            "value": 31.436,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3181.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2493,
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
          "id": "0fd6835f1968741dc6e09a2194d9ca85922449a0",
          "message": "Load the principles into agent context; make CI dependency resolution reproducible (#33) (#44)\n\n* docs(principles): load the north star into every agent session\n\nThe published principles (gaspatchio.dev/principles) lived only in the docs\nrepository. CLAUDE.md imported the AGENTS.md rule sets and nothing else, so\nneither a contributor nor a coding agent working in this repo ever saw the\npositions the framework actually takes — design decisions and bug triage were\nbeing argued without the thing they should be argued against.\n\nAdd PRINCIPLES.md as the in-repo copy (the published page stays canonical for\nwording) and import it from CLAUDE.md ahead of the rule sets. The seven\none-liners also go inline in AGENTS.md, so agents that do not follow links\nstill get the north star.\n\nTwo things the source document leaves implicit are made explicit here: the\nresolution of its central tension — be liberal about the shapes you accept, be\nstrict about the meanings you infer — and that\nref/21-kaizen/01-rails-inspired-principles.md is superseded where it conflicts,\nnotably its \"Magic That Makes Sense\" section, which \"Sharp knives, no magic\"\nrejects.\n\n.github/copilot-instructions.md is generated from AGENTS.md; regenerated.\n\n* ci(deps): track uv.lock and install with --locked (#33)\n\nCI resolved dev dependencies fresh on every run, so a pull request's result\ndepended on what PyPI had released that morning rather than on its own diff.\nOn 2026-07-25 ruff floated to 0.16.0 and its changed I001 behaviour failed\n~70 docstring-example tests on a PR that touched none of them, and would have\nfailed every later PR and push to main identically. The lockfile already\nexisted but was gitignored, so laptops were reproducible and CI was not — the\nworst arrangement, because it hid the problem locally.\n\nTrack bindings/python/uv.lock and install it with `uv sync --locked` at all\ntwelve sync sites. Eleven were still floating, including evals.yml, which runs\non every push to main. The ruff pin comment in bindings/python/pyproject.toml\nsaid \"no lockfile ships in this repo\"; that is no longer true, so it now\ndescribes what the pin is actually for.\n\nAlso add a repository-root pyproject.toml declaring the workspace boundary.\nWithout it uv walks up out of the repository looking for a workspace root and,\nin a local multi-repo checkout, resolves against sibling repositories — so\n`uv run` from the repository root failed with a dependency conflict belonging\nto another project entirely, which is the first thing AGENTS.md's bare\n`uv run` examples would hit. bindings/python is excluded rather than made a\nmember: as a member, uv relocates the environment and lockfile to the\nrepository root, orphaning the lockfile CI expects and forcing every\ncontributor into a full Rust rebuild. AGENTS.md now states the working\ndirectory instead of leaving it implied.\n\nVerified: 2644 passed, 8 skipped, 5 xfailed, 1 xpassed.\n\n* docs(ref): design for the v0.6.0 outstanding-issue batch\n\nTriage of the ten issues left open after #21-#30 merged: eight to fix, one\nalready done on this branch, one deferred. Every verdict is justified against\nPRINCIPLES.md by name, which is newly possible now that the principles load\nwith the repository rules.\n\nTwo verdicts depart from what the issues themselves propose, and the reasoning\nis recorded rather than left implicit:\n\n- #37 takes the targeted-error option over auto-wrapping bare strings as\n  literals. Auto-wrapping infers a meaning from a shape, which \"Sharp knives,\n  no magic\" forbids, and would silently change behaviour for anyone passing a\n  column name as a string.\n- #36 materialises `month` and `proj_year`, not `year`. A framework-owned\n  `year` column would collide with the calendar year that model points\n  routinely carry, and Gotcha #7 already names `proj_year` vs `year` as a\n  cause of silently-wrong stress scenarios — a fix that worsens a documented\n  trap is not a fix.\n\n#31 turned out to be narrower than \"wrong convention\": `extrapolation` is\nalready declared, defaulted, serialised across the plugin boundary, and read\nby nothing, and \"flat\" is simply applied in the wrong space for log_linear\nalone. The work is making a dead parameter live, with \"flat\" clamping the spot\nrate (coherent with linear/pchip) and \"forward\" available for market-consistent\nlong-tail discounting.\n\n#41 is deferred on capacity, not disagreement: an Excel-port path is a whole\nskill, and a bad one is worse than none.\n\n* docs(ref): drop the two-day window; every fix ships in v0.6.0\n\nThe batch was originally scoped to a two-day window, which forced a\npre-designated item to drop if the estimate proved optimistic (#39, error\nattribution). That constraint is lifted: the release is cut when the work is\ndone rather than to a date, so nothing is expendable.\n\n#39 stays last in the order, but for a different reason — it is the one item\nwhose cost cannot be estimated before starting, so it belongs off the critical\npath rather than at the front of it. PRs 1 and 2 also touch surfaces that 3-5\nbuild on (the AGENTS.md examples, the lookup error path), so landing them first\nmeans the harder work rebases onto corrected foundations.\n\nThe accepted trade-off is now recorded as a risk rather than left implicit: two\nbreaking changes (#24, #28) stay unreleased for longer, mitigated by telling\nthe field reporter directly what is coming and what it changes.\n\n* docs(ref): implementation plan for the v0.6.0 issue batch\n\nTwelve tasks across five pull requests, each with the failing test written\nfirst, the exact command to run it, and the implementation to make it pass.\nFile paths and signatures were verified against the tree rather than assumed:\nthe proxy dunders delegate to a dispatch method (so __neg__ is self.mul(-1.0)\nand inherits list shimming), the bare-string lookup key originates at\n_api.py:993, and projection.set's real signature is until=/until_value=/\nfrequency= rather than the projection_end_* names the docs still show.\n\nTwo steps deliberately direct the implementer to read code before writing:\nlocating the describe() raise from its traceback, and reading the replay\nmachinery before attempting collect-time attribution. Inventing call sites\nthat cannot be verified would be worse than pointing at the evidence.\n\n* fix(deps): bump pyasn1 to 0.6.4; document the pymdown-extensions exception\n\nTracking bindings/python/uv.lock gave the PR scanner a Python lockfile to read\nfor the first time. It reported six advisories across two packages as\n\"introduced\" by that commit — the scan of main returned an empty result set\nbecause there was nothing to scan. The risk was not new, only unmeasured,\nwhich is the argument for tracking the lockfile rather than against it.\n\npyasn1 0.6.3 -> 0.6.4 clears PYSEC-2026-3455/3456/3457, GHSA-8ppf-4f7h-5ppj\nand GHSA-hm4w-wwcw-mr6r outright — remediation by lockfile bump, as this\nfile's own policy prefers.\n\nGHSA-9xwg-3r6f-jcx2 (pymdown-extensions path traversal in the b64 extension)\ncannot be remediated: the fix is 11.0.0 and marimo 0.23.13 pins\npymdown-extensions>=10.21.2,<11. It is recorded as an exception with its\nreachability stated — the package arrives through the optional `recipes`\nextra so it is absent from the published wheel's runtime closure, and\nexploitation needs the b64 extension enabled over attacker-controlled\nmarkdown, which gaspatchio never renders.\n\nVerified: uv lock --check and uv sync --locked exit 0; 2644 passed, 8 skipped,\n5 xfailed, 1 xpassed.\n\n* ci(security): apply osv-scanner.toml to every scanned lockfile\n\nosv-scanner resolves its config relative to each scanned file's own directory,\nso the root osv-scanner.toml governed Cargo.lock but never\nbindings/python/uv.lock. The GHSA-9xwg-3r6f-jcx2 exception added in the\nprevious commit was therefore inert — the scanner reported it under \"unused\nignores\" while still failing on the very advisory it named.\n\nPassing --config makes the one file authoritative for every lockfile, which\nkeeps a single reviewed exception list rather than scattering a second\nosv-scanner.toml into bindings/python.\n\nVerified locally against the real scanner image (ghcr.io/google/osv-scanner\n:v2.3.8, the version the workflow pins): without the flag it reports\nGHSA-9xwg-3r6f-jcx2 and lists the ignore as unused; with it, \"9 vulnerabilities\nfiltered, No issues found\".",
          "timestamp": "2026-07-29T11:42:06+12:00",
          "tree_id": "a9d5a2701820f06e59b432ffbdeb1fd7d5d86555",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0fd6835f1968741dc6e09a2194d9ca85922449a0"
        },
        "date": 1785282599004,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.3,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.308,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.329,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3333.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 3039.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 59,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 10.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 5.57,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.94,
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
            "value": 40.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.27,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.296,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.334,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4405.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4284.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 264.1,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 80.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 3.29,
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
            "value": 3.126,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3199,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 365.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 21.531,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 21.685,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 21.992,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4644.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4547.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2616.3,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 717.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 3.64,
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
            "value": 30.532,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3275.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 2395,
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
          "id": "0863a9ce7464d48d7566ddcd787257d40f98509b",
          "message": "Papercuts: unary negation, stale quickstart, describe on list columns, timing signpost (#45)\n\n* fix(column): support unary negation on list columns (#38)\n\n`-af.some_list_column` raised \"neg operation not supported for dtype\nlist[f64]\" while `0.0 - col` and `col * -1.0` both worked, as did `.abs()`,\n`.floor()`, casts and `** 2`. Both proxies define the full arithmetic dunder\nset but omitted `__neg__`, so Python fell through to Polars' native `neg`,\nwhich has no list kernel.\n\nNegation now multiplies by -1 through the same dispatch method the other\noperators use, so it inherits list-column shimming rather than reimplementing\nit. Added to ColumnProxy and ExpressionProxy alike — the second matters because\n`-(af.col * 2.0)` negates an expression, not a column.\n\n* docs: correct the removed projection API and make the quickstart executable (#35)\n\nAGENTS.md is auto-loaded by every agent session, so its quickstart calling\n`af.date.create_projection_timeline(...)` — removed some releases ago — made\nevery downstream session start from a false premise. The parameter names had\ndrifted too, so Gotcha #2's `projection_end_value=99` was stale in the same\nway.\n\nThe sweep found four more occurrences beyond the two known ones:\n\n- skills/gaspatchio-model-building/references/mortality-tables.md\n- schedule/_schedule.py, whose docstring pointed at\n  `date.create_timeline(projection_end_value=N)`. That method does still\n  exist, but takes (start_col, end_col, freq, ...) and has never had that\n  parameter, so the reference was wrong in a way that reads as correct.\n- errors/constants.py, whose projection-end reference set predates\n  `next_anniversary` being accepted.\n\nCorrecting prose fixes today and drifts again next release, so the documented\nshape is now executed by a test, together with an assertion that the removed\nentry point stays removed.\n\n* fix(cli): describe parquet files containing list columns (#40)\n\n`gspio describe` on a file with a list<f64> column printed \"Unsupported key\ntype for array storage: List(Float64)\" and logged an ERROR, because it fed\nevery file through assumption-table detection. Reading back a run's own output\nis what the CLI's agent workflow instructs, so the documented happy path was\nthe one that misbehaved.\n\nList columns are now partitioned out before table-structure detection and\nsummarised on their own terms — inner dtype and length range. A file carrying\nthem is projection output, so describe says so and stops, rather than\nsuggesting a Table() constructor that cannot run against it. The printed\nexample now shows how to read the file back and explode a period column.\n\nTwo further problems surfaced while fixing it:\n\n- The --json payload reported list columns inside detected_dimensions, so an\n  agent following the documented workflow would have tried to key a lookup on\n  a per-period column. They now have their own `list_columns` field and are\n  excluded from the dimension analysis.\n- A frame of nothing but list columns reached value-column detection with no\n  columns left; that case now short-circuits.\n\n* docs: signpost timing conventions in the top-level guide (#42)\n\nprospective_value's beginning/end-of-period semantics were documented only in\nits docstring, so the read-AGENTS-first path could miss that timing is a choice\nat all.\n\nTwo things made this worth more than a cross-reference. The defaults are\nopposite — prospective_value defaults to end_of_period while\ncumulative_survival's rate_timing defaults to beginning_of_period — and with\nconstant rates both conventions give identical answers, so a wrong choice\nsurvives testing and only diverges once rates vary at age boundaries or on a\nreal curve. Both are now stated in a table, with the discount-factor anchoring\ncontract from #28 alongside: passing discount_factor= rather than\ndiscount_rate= means the factors must share the convention you asked for, and\nunder per-period rates the two are not a single multiplication apart.\n\nDefaults were read from accessors/projection.py rather than from `gspio docs`,\nwhose index is currently stale.\n\n* fix(cli): three defects in the list-column describe path (#40)\n\nAll three found in review, all three confirmed by reproducing them before\nfixing. Each had slipped through because the original tests only ever\nexercised a file with ONE list column, only checked the text path for an\nall-list file, and never passed --value-column at all.\n\n1. The generated example was broken for more than one list column.\n   `pl.col(\"a\", \"b\").list.len().alias(\"n_periods\")` expands to two outputs\n   sharing a name and raises DuplicateError, so the snippet printed for any\n   real projection output did not run. Each column now gets its own alias.\n   This is the defect #35 exists to prevent, shipped in the commit that fixes\n   #35.\n\n2. `--json` on a file of nothing but list columns reported a value column\n   named \"rate\" that appears nowhere in the file, and suggested code\n   referencing it. analyze_table falls back to that default on an empty\n   frame; the short-circuit added earlier covered only the text path. With no\n   scalar columns the file cannot be an assumption table, so the value column\n   is empty and the suggested code reads the parquet back instead.\n\n3. `--value-column` naming a list column was validated against the full frame\n   and accepted, then reported as an assumption-table value. It is now\n   rejected with an error naming the scalar columns that are available.\n\nEach fix ships a test verified to fail against the previous commit.\n\n* fix: address self-review findings across the papercuts batch (#38, #35, #40)\n\nFourteen findings, all in this branch's own changes. Each was reproduced\nbefore being fixed.\n\nThe serious one is #38's. `__neg__` was implemented as `mul(-1.0)`, which\nsilently widened Int64 to Float64 (and List(Int64) to List(Float64)) where\n`0 - col` had always preserved the dtype. A negated duration could no longer\nkey an integer assumption table. `mul(-1)` preserves it; a dtype assertion now\npins that. `__neg__` was also missing from _BaseProxy in proxy.pyi, so `-col`\nremained a pyright error for every user with type checking on — the fix was\ninvisible to exactly the audience that reported it.\n\n#40's list-column handling had been threaded through describe as six\nindependent special cases, and the console and JSON modes had already drifted\napart as a result. Replaced with one classification (_partition_nested_columns)\nand one shared example generator, which removes four symptoms by construction:\n\n- Array and Struct columns still reproduced the original bug verbatim;\n  is_nested() covers what isinstance(dtype, pl.List) missed, and gaspatchio's\n  own rollforward machinery puts Struct columns in frames.\n- --json still fabricated a \"rate\" value column for the realistic shape (a\n  scalar policy id alongside list columns); the previous guard only caught\n  files that were entirely lists, which no real output is.\n- sample_rows dumped whole per-period lists: a 10-column x 1200-period file\n  produced ~900 KB of JSON, destroying the context of the agent that follows\n  the documented workflow. Now 2.9 KB.\n- The printed example was not runnable for more than one list column\n  (duplicate alias) nor when the resolved path made Rich wrap it mid-statement.\n- A zero-column parquet raised IndexError; --value-column naming a scalar on a\n  mixed file silently dropped the Table example the user had asked for; the\n  console printed a value column before disclaiming it applied.\n\n#35's fix stopped one line short. Phase 1 creates `issue_age` and Phase 3 read\n`af.age`, so the documented model still failed immediately after the corrected\ncall — and looking up on a scalar age yields one rate with nothing for\ncumulative_survival() to accumulate. Phase 3 now derives attained age and the\ntest executes the whole three-phase shape rather than the single line that had\nbeen reported. Writing it surfaced a real gotcha, now documented: maximum_age\nsizes one grid from the youngest life, so a 55-year-old reaches attained age\n115 and the lookup raises.\n\nAlso: errors/constants.py carried a \"keep in sync\" comment naming an invariant\nnothing enforced, which is how it drifted; a test now asserts it against the\nLiteral. pyright on cli.py goes 6 errors to 0, ruff on tests/api 4 to 0.\n\nVerified: 2661 passed, 8 skipped, 5 xfailed, 1 xpassed; stubtest clean across\n263 modules; manifests regenerated with no drift.",
          "timestamp": "2026-07-29T17:19:04+12:00",
          "tree_id": "ff70a6817a9091f43e02033b2265ed37dc3b955a",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0863a9ce7464d48d7566ddcd787257d40f98509b"
        },
        "date": 1785302798542,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "L4 Aggregation/1K-baseline-wall",
            "value": 0.321,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-agg-wall",
            "value": 0.33,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-wall",
            "value": 0.335,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-baseline-throughput",
            "value": 3115.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-throughput",
            "value": 2985.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-baseline-peak",
            "value": 59.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-baseline-data-mb",
            "value": 24.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-aggregated-peak",
            "value": 6.4,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/1K-memory-ratio",
            "value": 9.28,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-speedup",
            "value": 0.99,
            "unit": "x"
          },
          {
            "name": "L4 Aggregation/1K-correct",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "L4 Aggregation/1K-spill-wall",
            "value": 0.447,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/1K-spill-throughput",
            "value": 2237.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/1K-spill-peak",
            "value": 34.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-wall",
            "value": 2.34,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-agg-wall",
            "value": 2.367,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-wall",
            "value": 2.398,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-baseline-throughput",
            "value": 4273.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-throughput",
            "value": 4170.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-baseline-peak",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-baseline-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-aggregated-peak",
            "value": 107.6,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/10K-memory-ratio",
            "value": 2.35,
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
            "value": 3.256,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/10K-spill-throughput",
            "value": 3071.3,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/10K-spill-peak",
            "value": 357.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-wall",
            "value": 22.361,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-agg-wall",
            "value": 22.513,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-wall",
            "value": 22.843,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-baseline-throughput",
            "value": 4472.1,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-throughput",
            "value": 4377.7,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-baseline-peak",
            "value": 2633.2,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-baseline-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-aggregated-peak",
            "value": 597.7,
            "unit": "MB"
          },
          {
            "name": "L4 Aggregation/100K-memory-ratio",
            "value": 4.41,
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
            "value": 31.581,
            "unit": "seconds"
          },
          {
            "name": "L4 Aggregation/100K-spill-throughput",
            "value": 3166.5,
            "unit": "points/sec"
          },
          {
            "name": "L4 Aggregation/100K-spill-peak",
            "value": 1777.7,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}