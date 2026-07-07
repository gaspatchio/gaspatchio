window.BENCHMARK_DATA = {
  "lastUpdate": 1783419012219,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Model Benchmarks (Windows)": [
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
        "date": 1783392787835,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.248,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 32.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 131.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 10.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.399,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2506.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 60.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 191.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.329,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4293.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 289.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 460.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 22.567,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4431.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2730.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3094.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.165,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 48.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -614.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1371.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 21.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.906,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1103.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 90.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1459.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 82.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.272,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1594.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 543.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1956.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 62.648,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1596.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7402.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9101,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.5,
            "unit": "%"
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
        "date": 1783393692683,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.26,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 30.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 132,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 13.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.402,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2487.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 190.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 52.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.329,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4293.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 288,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 458.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 22.362,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4471.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2694.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3064,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.216,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 37,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -924.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1154.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 49.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.149,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 870.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 117.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1244,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 85,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.954,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1438,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 543.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1742.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 64.244,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1556.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7475.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8960,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.5,
            "unit": "%"
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
        "date": 1783395160492,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.16,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 50,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 131.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 22,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.408,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2451,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 60,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 192.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 64.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.33,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4291.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 290.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 461.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.06,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4156.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2753.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3113.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.212,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 37.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -1008,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1121.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 39.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.008,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 992.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 86.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1200.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 80,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 7.165,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1395.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 552.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1706.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 66.304,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1508.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7606,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9033.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.5,
            "unit": "%"
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
        "date": 1783419009831,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.257,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 31.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 131.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 13.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.39,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2564.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 190.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 49.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.297,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4353.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 286,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 455.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 22.155,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4513.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2736.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3103,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.192,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 41.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -855.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1262.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 17.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.918,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1089.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 34.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1295,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 83.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.533,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1530.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 559.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1804.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 62.752,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1593.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7506.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9052,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.6,
            "unit": "%"
          }
        ]
      }
    ]
  }
}