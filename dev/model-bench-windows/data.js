window.BENCHMARK_DATA = {
  "lastUpdate": 1786153777044,
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
        "date": 1783460010053,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.2,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 40,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 131.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.447,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2237.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 189.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 65.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.584,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3870,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 288.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 457.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.473,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4260.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2714.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3082.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.18,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 44.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -777.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1320.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 25.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.924,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1082.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 17.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1336,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 80.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.238,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1603.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 550.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1837.7,
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
            "value": 62.959,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1588.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7505.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9080.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.4,
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
          "id": "56797ef297e3cd76a5a9de4b474a89ce1fe7d28e",
          "message": "fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes (#11)\n\n* fix(scenarios): floor probe peaks at frame size; bench cells get fresh processes\n\nThird and deepest layer of the auto-search OOM fix: the gate's INPUT was\nbroken. Probe peaks are measured as RSS delta-over-baseline -- but in a\nprocess with retained allocator pools, a batch can be served entirely\nfrom pooled memory: RSS never grows and the sampler reads ~0. Observed\nlive on CI (probes: [b1/streaming=0MB+fits]) -- any prediction\nmultiplied from that zero is blind, so the gate launched an unaffordable\nprobe and the runner died again. The budget also collapsed across bench\ncells (7148 -> 3094 MB) because base RSS includes the pools.\n\nLibrary: floor each batch's measured peak with the materialised frame's\nestimated_size() -- the frame's bytes are live memory at peak regardless\nof where the allocator got them. This is the same floor the policy axis\nhas always applied to its seed measurement (_spill/_aggregated).\n\nBench: run each grid cell of run_scenario_benchmarks.py in a fresh\ninterpreter (the pattern scenario_batch_search_bench already uses for\nits floor workers): clean allocator baseline, honest probe measurements,\nfull budget per cell -- and a kernel-killed cell now loses one cell, not\nthe whole run. Child stderr is inherited so probe-ladder lines stream\ninto the CI log.\n\nNew test pins the pool-reuse lie: with the sampler forced to read 0 and\na budget the frame fits at b=1, the b=4 rung must still be gated and the\nrecorded rung peak must be the floor, not the lie.\n\n* fix(evals): distinguish cell kills from cell errors; bound cell wall clock\n\nReview feedback (Greptile, both accepted): the subprocess wrapper treated\nevery childless exit as a benign skip and had no per-cell timeout.\n\n- A clean nonzero exit with no result is a real error (import failure,\n  bug) -- raise so CI fails instead of publishing an incomplete benchmark\n  as green. Only signal kills (negative returncode, e.g. kernel OOM) and\n  timeouts are tolerated as one-cell losses, which is what the isolation\n  is for.\n- Cap each cell at 30 min (heaviest legitimate cell ~6 min) so one wedged\n  cell cannot eat the job timeout and lose every other cell's output.\n\nVerified: happy path returns metrics; a crashing child (missing points\nfile) raises RuntimeError in the parent.",
          "timestamp": "2026-07-08T10:34:49+12:00",
          "tree_id": "78eea24f36fce56777dfd384309a09753d470d54",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/56797ef297e3cd76a5a9de4b474a89ce1fe7d28e"
        },
        "date": 1783464334536,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.297,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 26.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.1,
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
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 14,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.4,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2500,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 190.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.344,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4266.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 291.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 461.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.159,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4139.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2731,
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
            "value": 0.15,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 53.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -302.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1489.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 22.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.91,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1098.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 74.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1562,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 83.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.277,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1593.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 488.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 2000.4,
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
            "value": 64.318,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1554.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7414.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9116,
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
          "id": "ec906df4330539df20b2913be4e9c199e4e1f1e8",
          "message": "ci(evals): run scenario benchmarks on every push to main\n\nThe scenario suite now completes reliably on free standard runners: the\nauto-search OOM chain is fixed (#8/#10/#11 gate + inflation + frame\nfloor) and the bench tolerates irreducible cells and isolates each cell\nin a fresh process (#9/#11). Validated on dispatch run 28903417786 --\nthe 10sc x 100K cell completes at batch=1 in 209s/6.5GB with the gate\nblocking the b=4 probe (probes: [b1/streaming=3198MB+fits] budget=7275MB).\n\nAdd push-to-main to the job's trigger so dev/scenario-bench{,-windows}\naccumulate a data point per merge, like the other benchmark suites.",
          "timestamp": "2026-07-08T10:56:32+12:00",
          "tree_id": "bf4e7d57e8e151dc257a9212034540677f13eb31",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ec906df4330539df20b2913be4e9c199e4e1f1e8"
        },
        "date": 1783465560744,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.19,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 42.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 132.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 14.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.392,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2551,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 191.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.298,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4351.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 287.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 457.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 22.395,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4465.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2765.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3126.3,
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
            "value": 0.147,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 54.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -518.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1419.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 17.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.902,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1108.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 39.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1400.8,
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
            "value": 6.197,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1613.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 561.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1914.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 63.002,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1587.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7531.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9172.6,
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
          "id": "ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4",
          "message": "release: v0.5.3",
          "timestamp": "2026-07-08T12:06:26+12:00",
          "tree_id": "1f26e1d201ebd4d1b166b0280e6c9f758cccbe90",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4"
        },
        "date": 1783469825550,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.204,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 39.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 132.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 8.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.397,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2518.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 190.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.303,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4342.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 288.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 458.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 27.175,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3679.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2688.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3052.8,
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
            "value": 0.175,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 45.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -730.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1336.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 26.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.161,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 861.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 16.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1350.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 82.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 8.054,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1241.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 493.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1798.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 64.055,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1561.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7578.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9112.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.4,
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
          "id": "a4bfc5580c9525d19b28149ccc143914010a4597",
          "message": "ci: drop develop from workflow triggers\n\nThe public repo is trunk-based: develop was a launch-era leftover whose\ncontent is fully contained in main (post-release fixes landed via squash\nPR #7), and the branch has been deleted. Feature branches PR straight to\nmain; releases are signed tags on main.",
          "timestamp": "2026-07-08T13:30:41+12:00",
          "tree_id": "81d5b3dcfb5f2545f7642c835393e05f38f4c47d",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/a4bfc5580c9525d19b28149ccc143914010a4597"
        },
        "date": 1783474886671,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.253,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 31.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 35.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 131.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 11.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.4,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2500,
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
            "value": 191.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.343,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4268,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 287.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 457.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.994,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4167.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2725.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3088.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.206,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 38.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -931.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1173.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 18.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.924,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1082.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 95.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1266.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 78.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.302,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1586.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 511.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1727.8,
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
            "value": 64.779,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1543.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7467.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8935.8,
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
        "date": 1783486512512,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.262,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 30.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 28.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 125.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 20.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.432,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2314.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 184.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 60.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.47,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4048.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 301.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 467.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.919,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4013,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2695,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3062.9,
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
            "value": 0.138,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 58,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2089.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 13.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.068,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 936.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1701.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 388.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 78.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.547,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1527.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 761.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1103.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 68.394,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1462.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7754.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8599.1,
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
          "id": "5a02e98c45f779e8734e9567afb0e326a8c50223",
          "message": "ci(release): build windows/macos wheels one interpreter per matrix leg (#15)\n\nThe v0.5.3-era wheel jobs built cp312/313/314 sequentially in one job via\n--find-interpreter. Measured on the first warm run after #12: the rust-cache\nhit exactly but windows still took 44 min (vs 51 cold), because the polars\nstack sits inside pyo3's dependency cone — every interpreter change\nrecompiles all 29 crates (~14 min), and the three sequential builds thrash\none target dir, so the saved cache only ever holds the last interpreter's\nartifacts and the expensive layer never hits.\n\nSplitting the interpreter into the matrix makes each leg build exactly one\nCPython (-i pinned to setup-python's interpreter), with its own cache key\nand artifact name. Legs run in parallel (~15 min wall-clock cold), and each\ncache holds one config so warm runs rebuild only the gaspatchio crates.\nThe release job's wheels-* download pattern picks up the renamed artifacts\nunchanged; the wheel set stays exactly cp312/313/314 per platform.",
          "timestamp": "2026-07-08T20:56:25+12:00",
          "tree_id": "ccc463340528e69b4b6820ec2f7842b994fc3ce0",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5a02e98c45f779e8734e9567afb0e326a8c50223"
        },
        "date": 1783501625168,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.291,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 27.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 28.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 125.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.414,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2415.5,
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
            "value": 183.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 56.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.37,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4219.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 303.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 469.8,
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
            "value": 24.144,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4141.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2847.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3029.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.129,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 62,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 8.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2059.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 22.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.026,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 974.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1691.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 368,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 79.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.386,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1565.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 752.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1074.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 67.488,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1481.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7677.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8491.6,
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
        "date": 1783922868565,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.215,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 37.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 28.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 125.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.414,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2415.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 185.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.42,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4132.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 303.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 470.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.361,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4280.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2851.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3036.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.145,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 55.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 5.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2060.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 34.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.292,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 774,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1696.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 363.8,
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
            "value": 6.697,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1493.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 753.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1073,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 84.122,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1188.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7608,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8420.3,
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
        "date": 1784527530834,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.136,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 58.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 28.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 125.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 8.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.213,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 4694.8,
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
            "value": 184.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 36,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.212,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 8250.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 304.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 470.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 84.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 11.558,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 8652,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2689.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3062.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.115,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 69.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -581.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1500.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 14.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.453,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 2207.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 102,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 1602.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 69.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 3.117,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 3208.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 169.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1098,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 94.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 32.279,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 3098,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7849.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8687.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.1,
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
          "id": "f7b2b0e8b14d9c2615b8304faf62cec38bb84502",
          "message": "Apply the documented dimensions rename mapping; invite private bug reports (#32)\n\n* fix(assumptions): apply the documented dimensions rename mapping\n\nThe dimensions dict is documented as mapping YOUR name -> SOURCE column\nname, but the string-shorthand conversion built DataDimension(source)\nand discarded the dict key: rename_to was never set, the processed\ntable kept the source column names, and lookup() failed with \"No value\nprovided for key column '<source name>'\". Every shipped example uses\nidentity mappings, so the rename path had never worked.\n\n- Shorthand entries now wire rename_to=dim_name (identity mappings are\n  a no-op).\n- An explicit DataDimension under a differing dict key gets the same\n  default; a user-set rename_to still controls the processed column\n  name, and lookup() translates it back so lookups always speak the\n  dimension-dict vocabulary.\n- The 'shouldn't happen' error now reports both vocabularies when a\n  custom dimension produces an unmatched column name.\n\nFixes #30. Reported via a private field report.\n\n* docs(security): invite private bug reports with an anonymisation promise\n\nMany gaspatchio users work at insurers and cannot post code publicly.\nDocument the intake path: any bug may be reported by email; confirmed\nbugs get a public tracking issue with a rewritten neutral reproduction,\nno names, employers, or model details, and opt-in-only credit.\n\n* fix(assumptions): preserve renamed dimensions through shock reconstruction\n\nReview follow-up (greptile P1 on #32): with_shock/from_shocks rebuild a\nTable from its PROCESSED frame but generated identity dimension specs\nfrom the dict keys (with_shock via a column_name attribute that\nDataDimension does not even have), so any dimension whose processed\ncolumn name differs from its key — an explicit\nDataDimension(rename_to=...) — failed reconstruction with 'Column not\nfound'.\n\n_reconstruction_dimensions() maps each dimension key to its processed\ncolumn name; all three reconstruction sites use it, computed from the\ntable actually supplying the source frame (after with_shock, an\nexplicit rename_to has already collapsed to the dimension name). The\nlookup vocabulary is preserved through arbitrary shock chains.\n\n* fix(assumptions): honour non-Data dimension output names in lookup and reconstruction\n\nReview follow-up (second greptile P1 on #32): Melt/Categorical/Computed\ndimensions surface their processed column via their  field, which\nmay differ from the dimensions-dict key. The lookup translation and\n_reconstruction_dimensions() only handled DataDimension, so such tables\nfailed lookup('No value provided for key column') and failed shock\nreconstruction against a nonexistent column.\n\nBoth now map , so the lookup\nvocabulary (the dict keys) holds for every dimension type, through\nwith_shock and both from_shocks branches. Regression test: a\nMeltDimension named differently from its dict key, looked up and\nshocked.\n\n* chore(deps): pin ruff — the docstring-example linter is version-sensitive\n\nCI resolves dev dependencies fresh (no lockfile ships in this repo), so\nruff>=0.11.10 floated to yesterday's 0.16.0 release, whose changed I001\nimport-sorting behaviour failed ~70 docstring-example lint tests on\nevery PR regardless of its diff. Pin to the version the examples are\nwritten against; the systemic reproducibility fix is tracked in #33.",
          "timestamp": "2026-07-26T15:07:38+12:00",
          "tree_id": "ff0d146f3b39a49d30ba833252f1dea60226af9f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/f7b2b0e8b14d9c2615b8304faf62cec38bb84502"
        },
        "date": 1785035987318,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.299,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 26.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 133.8,
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
            "value": 0.421,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2375.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 192,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 59.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.418,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4135.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 291.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 465.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.171,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4137.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2707.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3075.3,
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
            "value": 0.132,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 60.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 7.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2100.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 19.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.064,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 939.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1713.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 387.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 76.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.503,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1537.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 751.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1092.3,
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
            "value": 65.803,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1519.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7588.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8418.9,
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
          "id": "e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd",
          "message": "Issue-tracking scheme: triage labels, templates, release notes, public roadmap policy (#34)\n\n* chore(github): issue templates with auto-triage labels and release-notes config\n\nBug reports now open with bug + needs-triage applied automatically, and the\ntemplate points insurer-employed reporters at the private email intake from\nSECURITY.md. release.yml gives auto-generated release notes keyed off PR\nlabels (bug / enhancement / documentation), with ignore-for-release as the\nopt-out.\n\n* docs: public roadmap policy and bug-lifecycle trail\n\nDocuments the label lifecycle a reporter can watch (needs-triage -> confirmed\n-> pending-release -> released via milestone) and the placeholder-issue model\nfor larger features (roadmap + exploring/building/shipped), including the\ncomment-before-building note for contributors and a non-commitment disclaimer.",
          "timestamp": "2026-07-27T10:20:08+12:00",
          "tree_id": "069536837f93ad61d285546ce8eed09794dec759",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e4d56ffbf66afaf6eedf366d53a4c3e9a676a8cd"
        },
        "date": 1785105091554,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.282,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 28.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 134.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 30.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.525,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 1904.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 192.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.689,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3718.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 293.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 468.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.379,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4101.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2729.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3096.7,
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
            "value": 0.218,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 36.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -655.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1462.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 21.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.023,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 977.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1051.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 410.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 80.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.7,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1492.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 759.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1121.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 67.866,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1473.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7680.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8543.9,
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
        "date": 1785133595455,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.526,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 15.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 133.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 10.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.349,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2865.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 192.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 51.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.178,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4591.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 279,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 453.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 19.175,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 5215.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2702.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3058.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 92.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.101,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 79.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 5.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2084.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 0,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 0,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.913,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1095.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1728.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 355.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 72.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 5.059,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1976.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 765.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1075.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 95.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 51.74,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1932.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7694.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8509.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.4,
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
          "id": "0fd6835f1968741dc6e09a2194d9ca85922449a0",
          "message": "Load the principles into agent context; make CI dependency resolution reproducible (#33) (#44)\n\n* docs(principles): load the north star into every agent session\n\nThe published principles (gaspatchio.dev/principles) lived only in the docs\nrepository. CLAUDE.md imported the AGENTS.md rule sets and nothing else, so\nneither a contributor nor a coding agent working in this repo ever saw the\npositions the framework actually takes — design decisions and bug triage were\nbeing argued without the thing they should be argued against.\n\nAdd PRINCIPLES.md as the in-repo copy (the published page stays canonical for\nwording) and import it from CLAUDE.md ahead of the rule sets. The seven\none-liners also go inline in AGENTS.md, so agents that do not follow links\nstill get the north star.\n\nTwo things the source document leaves implicit are made explicit here: the\nresolution of its central tension — be liberal about the shapes you accept, be\nstrict about the meanings you infer — and that\nref/21-kaizen/01-rails-inspired-principles.md is superseded where it conflicts,\nnotably its \"Magic That Makes Sense\" section, which \"Sharp knives, no magic\"\nrejects.\n\n.github/copilot-instructions.md is generated from AGENTS.md; regenerated.\n\n* ci(deps): track uv.lock and install with --locked (#33)\n\nCI resolved dev dependencies fresh on every run, so a pull request's result\ndepended on what PyPI had released that morning rather than on its own diff.\nOn 2026-07-25 ruff floated to 0.16.0 and its changed I001 behaviour failed\n~70 docstring-example tests on a PR that touched none of them, and would have\nfailed every later PR and push to main identically. The lockfile already\nexisted but was gitignored, so laptops were reproducible and CI was not — the\nworst arrangement, because it hid the problem locally.\n\nTrack bindings/python/uv.lock and install it with `uv sync --locked` at all\ntwelve sync sites. Eleven were still floating, including evals.yml, which runs\non every push to main. The ruff pin comment in bindings/python/pyproject.toml\nsaid \"no lockfile ships in this repo\"; that is no longer true, so it now\ndescribes what the pin is actually for.\n\nAlso add a repository-root pyproject.toml declaring the workspace boundary.\nWithout it uv walks up out of the repository looking for a workspace root and,\nin a local multi-repo checkout, resolves against sibling repositories — so\n`uv run` from the repository root failed with a dependency conflict belonging\nto another project entirely, which is the first thing AGENTS.md's bare\n`uv run` examples would hit. bindings/python is excluded rather than made a\nmember: as a member, uv relocates the environment and lockfile to the\nrepository root, orphaning the lockfile CI expects and forcing every\ncontributor into a full Rust rebuild. AGENTS.md now states the working\ndirectory instead of leaving it implied.\n\nVerified: 2644 passed, 8 skipped, 5 xfailed, 1 xpassed.\n\n* docs(ref): design for the v0.6.0 outstanding-issue batch\n\nTriage of the ten issues left open after #21-#30 merged: eight to fix, one\nalready done on this branch, one deferred. Every verdict is justified against\nPRINCIPLES.md by name, which is newly possible now that the principles load\nwith the repository rules.\n\nTwo verdicts depart from what the issues themselves propose, and the reasoning\nis recorded rather than left implicit:\n\n- #37 takes the targeted-error option over auto-wrapping bare strings as\n  literals. Auto-wrapping infers a meaning from a shape, which \"Sharp knives,\n  no magic\" forbids, and would silently change behaviour for anyone passing a\n  column name as a string.\n- #36 materialises `month` and `proj_year`, not `year`. A framework-owned\n  `year` column would collide with the calendar year that model points\n  routinely carry, and Gotcha #7 already names `proj_year` vs `year` as a\n  cause of silently-wrong stress scenarios — a fix that worsens a documented\n  trap is not a fix.\n\n#31 turned out to be narrower than \"wrong convention\": `extrapolation` is\nalready declared, defaulted, serialised across the plugin boundary, and read\nby nothing, and \"flat\" is simply applied in the wrong space for log_linear\nalone. The work is making a dead parameter live, with \"flat\" clamping the spot\nrate (coherent with linear/pchip) and \"forward\" available for market-consistent\nlong-tail discounting.\n\n#41 is deferred on capacity, not disagreement: an Excel-port path is a whole\nskill, and a bad one is worse than none.\n\n* docs(ref): drop the two-day window; every fix ships in v0.6.0\n\nThe batch was originally scoped to a two-day window, which forced a\npre-designated item to drop if the estimate proved optimistic (#39, error\nattribution). That constraint is lifted: the release is cut when the work is\ndone rather than to a date, so nothing is expendable.\n\n#39 stays last in the order, but for a different reason — it is the one item\nwhose cost cannot be estimated before starting, so it belongs off the critical\npath rather than at the front of it. PRs 1 and 2 also touch surfaces that 3-5\nbuild on (the AGENTS.md examples, the lookup error path), so landing them first\nmeans the harder work rebases onto corrected foundations.\n\nThe accepted trade-off is now recorded as a risk rather than left implicit: two\nbreaking changes (#24, #28) stay unreleased for longer, mitigated by telling\nthe field reporter directly what is coming and what it changes.\n\n* docs(ref): implementation plan for the v0.6.0 issue batch\n\nTwelve tasks across five pull requests, each with the failing test written\nfirst, the exact command to run it, and the implementation to make it pass.\nFile paths and signatures were verified against the tree rather than assumed:\nthe proxy dunders delegate to a dispatch method (so __neg__ is self.mul(-1.0)\nand inherits list shimming), the bare-string lookup key originates at\n_api.py:993, and projection.set's real signature is until=/until_value=/\nfrequency= rather than the projection_end_* names the docs still show.\n\nTwo steps deliberately direct the implementer to read code before writing:\nlocating the describe() raise from its traceback, and reading the replay\nmachinery before attempting collect-time attribution. Inventing call sites\nthat cannot be verified would be worse than pointing at the evidence.\n\n* fix(deps): bump pyasn1 to 0.6.4; document the pymdown-extensions exception\n\nTracking bindings/python/uv.lock gave the PR scanner a Python lockfile to read\nfor the first time. It reported six advisories across two packages as\n\"introduced\" by that commit — the scan of main returned an empty result set\nbecause there was nothing to scan. The risk was not new, only unmeasured,\nwhich is the argument for tracking the lockfile rather than against it.\n\npyasn1 0.6.3 -> 0.6.4 clears PYSEC-2026-3455/3456/3457, GHSA-8ppf-4f7h-5ppj\nand GHSA-hm4w-wwcw-mr6r outright — remediation by lockfile bump, as this\nfile's own policy prefers.\n\nGHSA-9xwg-3r6f-jcx2 (pymdown-extensions path traversal in the b64 extension)\ncannot be remediated: the fix is 11.0.0 and marimo 0.23.13 pins\npymdown-extensions>=10.21.2,<11. It is recorded as an exception with its\nreachability stated — the package arrives through the optional `recipes`\nextra so it is absent from the published wheel's runtime closure, and\nexploitation needs the b64 extension enabled over attacker-controlled\nmarkdown, which gaspatchio never renders.\n\nVerified: uv lock --check and uv sync --locked exit 0; 2644 passed, 8 skipped,\n5 xfailed, 1 xpassed.\n\n* ci(security): apply osv-scanner.toml to every scanned lockfile\n\nosv-scanner resolves its config relative to each scanned file's own directory,\nso the root osv-scanner.toml governed Cargo.lock but never\nbindings/python/uv.lock. The GHSA-9xwg-3r6f-jcx2 exception added in the\nprevious commit was therefore inert — the scanner reported it under \"unused\nignores\" while still failing on the very advisory it named.\n\nPassing --config makes the one file authoritative for every lockfile, which\nkeeps a single reviewed exception list rather than scattering a second\nosv-scanner.toml into bindings/python.\n\nVerified locally against the real scanner image (ghcr.io/google/osv-scanner\n:v2.3.8, the version the workflow pins): without the flag it reports\nGHSA-9xwg-3r6f-jcx2 and lists the ignore as unused; with it, \"9 vulnerabilities\nfiltered, No issues found\".",
          "timestamp": "2026-07-29T11:42:06+12:00",
          "tree_id": "a9d5a2701820f06e59b432ffbdeb1fd7d5d86555",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0fd6835f1968741dc6e09a2194d9ca85922449a0"
        },
        "date": 1785282769833,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.314,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 25.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.439,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2277.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.42,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4132.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 294.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 472,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.337,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4285,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2711.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3087.3,
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
            "value": 0.15,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 53.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2114.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 39.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.181,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 846.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1050.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 394.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 81.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.559,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1524.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 764.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1113.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 83.959,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1191.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7731.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8586,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.1,
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
          "id": "0863a9ce7464d48d7566ddcd787257d40f98509b",
          "message": "Papercuts: unary negation, stale quickstart, describe on list columns, timing signpost (#45)\n\n* fix(column): support unary negation on list columns (#38)\n\n`-af.some_list_column` raised \"neg operation not supported for dtype\nlist[f64]\" while `0.0 - col` and `col * -1.0` both worked, as did `.abs()`,\n`.floor()`, casts and `** 2`. Both proxies define the full arithmetic dunder\nset but omitted `__neg__`, so Python fell through to Polars' native `neg`,\nwhich has no list kernel.\n\nNegation now multiplies by -1 through the same dispatch method the other\noperators use, so it inherits list-column shimming rather than reimplementing\nit. Added to ColumnProxy and ExpressionProxy alike — the second matters because\n`-(af.col * 2.0)` negates an expression, not a column.\n\n* docs: correct the removed projection API and make the quickstart executable (#35)\n\nAGENTS.md is auto-loaded by every agent session, so its quickstart calling\n`af.date.create_projection_timeline(...)` — removed some releases ago — made\nevery downstream session start from a false premise. The parameter names had\ndrifted too, so Gotcha #2's `projection_end_value=99` was stale in the same\nway.\n\nThe sweep found four more occurrences beyond the two known ones:\n\n- skills/gaspatchio-model-building/references/mortality-tables.md\n- schedule/_schedule.py, whose docstring pointed at\n  `date.create_timeline(projection_end_value=N)`. That method does still\n  exist, but takes (start_col, end_col, freq, ...) and has never had that\n  parameter, so the reference was wrong in a way that reads as correct.\n- errors/constants.py, whose projection-end reference set predates\n  `next_anniversary` being accepted.\n\nCorrecting prose fixes today and drifts again next release, so the documented\nshape is now executed by a test, together with an assertion that the removed\nentry point stays removed.\n\n* fix(cli): describe parquet files containing list columns (#40)\n\n`gspio describe` on a file with a list<f64> column printed \"Unsupported key\ntype for array storage: List(Float64)\" and logged an ERROR, because it fed\nevery file through assumption-table detection. Reading back a run's own output\nis what the CLI's agent workflow instructs, so the documented happy path was\nthe one that misbehaved.\n\nList columns are now partitioned out before table-structure detection and\nsummarised on their own terms — inner dtype and length range. A file carrying\nthem is projection output, so describe says so and stops, rather than\nsuggesting a Table() constructor that cannot run against it. The printed\nexample now shows how to read the file back and explode a period column.\n\nTwo further problems surfaced while fixing it:\n\n- The --json payload reported list columns inside detected_dimensions, so an\n  agent following the documented workflow would have tried to key a lookup on\n  a per-period column. They now have their own `list_columns` field and are\n  excluded from the dimension analysis.\n- A frame of nothing but list columns reached value-column detection with no\n  columns left; that case now short-circuits.\n\n* docs: signpost timing conventions in the top-level guide (#42)\n\nprospective_value's beginning/end-of-period semantics were documented only in\nits docstring, so the read-AGENTS-first path could miss that timing is a choice\nat all.\n\nTwo things made this worth more than a cross-reference. The defaults are\nopposite — prospective_value defaults to end_of_period while\ncumulative_survival's rate_timing defaults to beginning_of_period — and with\nconstant rates both conventions give identical answers, so a wrong choice\nsurvives testing and only diverges once rates vary at age boundaries or on a\nreal curve. Both are now stated in a table, with the discount-factor anchoring\ncontract from #28 alongside: passing discount_factor= rather than\ndiscount_rate= means the factors must share the convention you asked for, and\nunder per-period rates the two are not a single multiplication apart.\n\nDefaults were read from accessors/projection.py rather than from `gspio docs`,\nwhose index is currently stale.\n\n* fix(cli): three defects in the list-column describe path (#40)\n\nAll three found in review, all three confirmed by reproducing them before\nfixing. Each had slipped through because the original tests only ever\nexercised a file with ONE list column, only checked the text path for an\nall-list file, and never passed --value-column at all.\n\n1. The generated example was broken for more than one list column.\n   `pl.col(\"a\", \"b\").list.len().alias(\"n_periods\")` expands to two outputs\n   sharing a name and raises DuplicateError, so the snippet printed for any\n   real projection output did not run. Each column now gets its own alias.\n   This is the defect #35 exists to prevent, shipped in the commit that fixes\n   #35.\n\n2. `--json` on a file of nothing but list columns reported a value column\n   named \"rate\" that appears nowhere in the file, and suggested code\n   referencing it. analyze_table falls back to that default on an empty\n   frame; the short-circuit added earlier covered only the text path. With no\n   scalar columns the file cannot be an assumption table, so the value column\n   is empty and the suggested code reads the parquet back instead.\n\n3. `--value-column` naming a list column was validated against the full frame\n   and accepted, then reported as an assumption-table value. It is now\n   rejected with an error naming the scalar columns that are available.\n\nEach fix ships a test verified to fail against the previous commit.\n\n* fix: address self-review findings across the papercuts batch (#38, #35, #40)\n\nFourteen findings, all in this branch's own changes. Each was reproduced\nbefore being fixed.\n\nThe serious one is #38's. `__neg__` was implemented as `mul(-1.0)`, which\nsilently widened Int64 to Float64 (and List(Int64) to List(Float64)) where\n`0 - col` had always preserved the dtype. A negated duration could no longer\nkey an integer assumption table. `mul(-1)` preserves it; a dtype assertion now\npins that. `__neg__` was also missing from _BaseProxy in proxy.pyi, so `-col`\nremained a pyright error for every user with type checking on — the fix was\ninvisible to exactly the audience that reported it.\n\n#40's list-column handling had been threaded through describe as six\nindependent special cases, and the console and JSON modes had already drifted\napart as a result. Replaced with one classification (_partition_nested_columns)\nand one shared example generator, which removes four symptoms by construction:\n\n- Array and Struct columns still reproduced the original bug verbatim;\n  is_nested() covers what isinstance(dtype, pl.List) missed, and gaspatchio's\n  own rollforward machinery puts Struct columns in frames.\n- --json still fabricated a \"rate\" value column for the realistic shape (a\n  scalar policy id alongside list columns); the previous guard only caught\n  files that were entirely lists, which no real output is.\n- sample_rows dumped whole per-period lists: a 10-column x 1200-period file\n  produced ~900 KB of JSON, destroying the context of the agent that follows\n  the documented workflow. Now 2.9 KB.\n- The printed example was not runnable for more than one list column\n  (duplicate alias) nor when the resolved path made Rich wrap it mid-statement.\n- A zero-column parquet raised IndexError; --value-column naming a scalar on a\n  mixed file silently dropped the Table example the user had asked for; the\n  console printed a value column before disclaiming it applied.\n\n#35's fix stopped one line short. Phase 1 creates `issue_age` and Phase 3 read\n`af.age`, so the documented model still failed immediately after the corrected\ncall — and looking up on a scalar age yields one rate with nothing for\ncumulative_survival() to accumulate. Phase 3 now derives attained age and the\ntest executes the whole three-phase shape rather than the single line that had\nbeen reported. Writing it surfaced a real gotcha, now documented: maximum_age\nsizes one grid from the youngest life, so a 55-year-old reaches attained age\n115 and the lookup raises.\n\nAlso: errors/constants.py carried a \"keep in sync\" comment naming an invariant\nnothing enforced, which is how it drifted; a test now asserts it against the\nLiteral. pyright on cli.py goes 6 errors to 0, ruff on tests/api 4 to 0.\n\nVerified: 2661 passed, 8 skipped, 5 xfailed, 1 xpassed; stubtest clean across\n263 modules; manifests regenerated with no drift.",
          "timestamp": "2026-07-29T17:19:04+12:00",
          "tree_id": "ff70a6817a9091f43e02033b2265ed37dc3b955a",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0863a9ce7464d48d7566ddcd787257d40f98509b"
        },
        "date": 1785302938578,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.201,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 39.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 135.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 10.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.411,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2433.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 64.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.378,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4205.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 310.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 487.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.16,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4317.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2842,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3041.8,
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
            "value": 0.18,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 44.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -663,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1400.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 28.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.032,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 969,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1023.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 376.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 82.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.438,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1553.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 750.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1080.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 80.913,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1235.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7706.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8529.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.4,
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
          "id": "ab1081f7463237dbfbd4eca563452cc313cdc0c5",
          "message": "Lookup: a bare string is the value (VLOOKUP semantics) (#46)\n\n* fix(assumptions): name both remedies for a bare-string lookup key (#37)\n\n`tbl.lookup(product=\"annuity\", age=af.age)` routed the string to `pl.col(...)`,\nso it was read as a column name and failed with \"Column 'annuity' not found.\nDid you mean...\" — pointing away from the actual mistake, and listing the\nframe's columns as candidates, which points further away still.\n\nThe issue offered two options; this takes the second deliberately. Auto-wrapping\na bare string as a literal infers a meaning from a shape, which \"Sharp knives,\nno magic\" forbids, and would silently change behaviour for anyone legitimately\npassing a column name as a string. Strings keep their Polars meaning; the error\nnames both readings and lets the caller say which they meant.\n\nThe error also arrives earlier than planned. Any ColumnProxy among the\ndimension values carries its parent frame, so the bare strings can be checked\nagainst the real schema at the lookup() call site rather than several lazy\nsteps later at collect(). With no proxy among the values there is no schema to\ncheck and the deferred error stands — no behaviour invented where there is no\ninformation to base it on.\n\nThe proxy check is duck-typed rather than an isinstance: ColumnProxy is\nannotation-only in this module and importing it at runtime would be circular.\nThat matches how the same function already recognises proxies a few lines down.\n\nVerified: 2652 passed, 8 skipped, 5 xfailed; ruff clean on both files; pyright\nunchanged from baseline (8 pre-existing errors in _api.py, none added).\n\n* feat(assumptions)!: a bare-string lookup key is the value, not a column (#37)\n\n`lookup(product=\"annuity\", age=af.age)` read the string as a COLUMN name\n(Polars convention), failed with \"Column 'annuity' not found\", and the only\nway to express the value was pl.lit(\"annuity\") — Polars leaking into the most\nordinary actuarial operation there is. VLOOKUP semantics are what an actuary\nmeans by that line, and the framework's own older design docs already wrote\nlookups that way (sex=\"M\", scalar_id=\"mort\").\n\nA bare string now means the value. Columns are referenced the gaspatchio way —\naf.product, af[\"product\"] — or pl.col(\"product\") for those who want Polars.\n\nThis replaces the targeted-error approach from the previous commit, and\ndeletes it: with no bare-string-as-column path there is no eager schema check,\nso its cross-frame false positive and its wrong-diagnosis-before-dimension-\nvalidation orderings (both found in review) cease to exist rather than\nneeding fixes, and string values travel as data rather than being interpolated\ninto suggested code.\n\nBREAKING, but safely so: a caller who relied on string-as-column now gets a\nlookup MISS, and since #24 misses raise by default naming the key that missed.\nThe old behaviour failed loudly too — it just blamed the wrong thing. The two\ninternal tests that used string-as-column only asserted isinstance(expr,\npl.Expr) and still pass.\n\nVerified: 256 assumption tests pass, including the #17/#22/#30 regression\nsuites on this same code path.\n\n* docs: bare-string lookup keys are values — state it in the always-loaded contract (#37)",
          "timestamp": "2026-07-30T23:15:02+12:00",
          "tree_id": "f0bc4329dfc18946ab686758027beb632b24b961",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ab1081f7463237dbfbd4eca563452cc313cdc0c5"
        },
        "date": 1785410666734,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.231,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 34.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.9,
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
            "value": 59.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 196.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 55.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.359,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4239.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 300,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 477.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 93.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.932,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4178.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2851.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3044.5,
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
            "value": 0.115,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 69.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 6.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2072.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 19.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.13,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 885,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1706,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 365.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 80.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.349,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1575.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 763.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1083.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 68.838,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1452.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7712.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8535.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "79e54aed7c9cf11b3eee16b3cbde0f6806c9841e",
          "message": "Projection: materialise the month period index — and only month (#47)\n\n* feat(projection): materialise the month and proj_year period index (#36)\n\nprojection.set() materialised no period index, yet shipped examples used\naf.month as though one existed. Deriving it by hand invited an off-by-one:\nt_years() returns n_periods + 1 values while year_fractions() returns\nn_periods, which is Gotcha #2 wearing a different hat.\n\n`month` is elapsed WHOLE MONTHS from the projection start, computed from the\nboundary dates rather than a periods-to-months multiple. The multiple only\nexists for month-aligned frequencies — the codebase's own _MONTHS_PER_PERIOD\nis annotated \"only meaningful for monthly-aligned frequencies\" — and a column\ncalled `month` that counted weeks would be its own trap. Dates make it exact\nat all six frequencies; the weekly test is what pins that.\n\n`proj_year` is month // 12. `year` was rejected: model points routinely carry\na calendar year, ref/05-dsl-polars-wrapper uses af[\"year\"] for exactly that,\nand Gotcha #7 already names proj_year vs year as a cause of silently-wrong\nstress scenarios. A framework-owned `year` would make a documented trap fire\nmore often, which is not a fix.\n\nBoth columns are length n_periods + 1, aligned with t_years(), so the\ndocumented maturity idiom reaches the final boundary — asserted rather than\nassumed. On per-policy timelines they are jagged with the schedule rather than\npadded to the longest-lived policy.\n\nA collision raises rather than overwriting. The first version of that guard\nwas wrong and the suite caught it: re-calling set() is supported and tested\n(test_recall_replaces_projection), and it tripped over the index the previous\ncall had stamped. The guard protects the user's columns, not ours — once a\nprojection exists the index is ours to replace, because a user-supplied\n`month` could not have survived the first call.\n\nThe AGENTS.md quickstart drops to `af.issue_age + af.proj_year` from\n`(af.issue_age + af.projection.t_years()).floor()`, and attained_age stays\nInt64 instead of routing through floats.\n\nVerified: 2673 passed, 8 skipped, 5 xfailed; 125 skill guards; manifests no\ndrift; pyright back to baseline (10 pre-existing, none added); ruff at the\nfile's pre-existing single error.\n\n* feat(projection)!: month only — no proj_year; stamp it only where honest (#36)\n\nReworks the previous commit after review found its proj_year both contradicted\nshipped guidance and could not be made right.\n\nResearch settled it. The framework already carries BOTH year conventions\nunder different names: every reconciled model computes duration = months // 12\n(0-based, lifelib's convention, table keys 0-14), while the model-building\nskill defines proj_year as BSCR-ordinal \"year 1\" via a ceiling — Excel's\nROUNDUP(t/12, 0). The two disagree at every anniversary boundary, and WHICH\none is correct for a stress shock depends on whether the model's rows are\nbeginning- or end-of-period anchored — the exact convention #42 just\ndocumented as a user choice. A framework-materialised proj_year therefore\nsilently picks the user's timing convention for them; under \"Sharp knives, no\nmagic\" that column must not exist. AGENTS.md now shows both one-line formulas\nand says why the framework stamps neither. Dropping it also halves the memory\ncost of the feature (~577 MB per Int64 column at 100K policies x 60y monthly).\n\n`month` survives, stamped only where the name is honest:\n\n- month-aligned frequencies only (1M/3M/6M/1Y). At 1W/1D the calendar-month\n  difference over-counts by up to a month — a daily grid from Jan 31 read\n  \"month 1\" after one day. The docstrings claiming exactness there were false\n  and are gone; sub-month grids get no fabricated index.\n- not on from_inception schedules, whose axis starts at each policy's own\n  inception: elapsed months there are policy DURATION, not projection time —\n  the Gotcha #7 conflation, and the axis scenarios/_aggregated.py already\n  refuses for calendar aggregation.\n- Int32 on both paths (was Int64 uniform / Int32 jagged — same API, two\n  dtypes, schema mismatch on concat).\n- a null per-policy horizon stamps an empty index, matching the null guard\n  num_proj_months already applies four lines above.\n\nThe collision guard now names both exits. A frame reconstructed from a\nprevious run's output (parquet reload, ActuarialFrame(af.collect())) carries\n`month` without a live projection, and we cannot tell that from a user's\ncalendar column — the old message told such users to rename the framework's\nown column, aliasing the period index into their model. It now offers rename\n(if yours) or drop (if from a previous run), and the round-trip is tested in\nboth directions. The guard deliberately covers only `month`: extending it to\nprojection_start_date/num_proj_months would make every reloaded-output\nre-projection raise, since those columns are always present in run output.\n\nset()'s public docstring — the gspio docs surface — now documents the stamped\ncolumns and the ValueError; the L1 tutorial comment asserting set() does not\nproduce `month` automatically was true when written and is corrected.\n\nVerified: 17 period-index tests including round-trip, weekly/daily skip,\nfrom_inception skip, null horizon, dtype, and the anniversary-disagreement\nmaths; 371 passed across accessors/rollforward/examples; ruff clean and\nformatted; pyright at baseline; manifests no drift.\n\n* docs(ref): record the #37 flip and the no-proj_year decision as spec amendments\n\n* fix(projection): collision guard fires only when month will be stamped\n\nWeekly, daily, and from_inception schedules never materialise the month\nindex, yet the collision check ran unconditionally — a frame carrying\nits own legitimate month column (a calendar month on the model points,\nsay) was told to rename a column nothing was going to touch. The guard\nprotects against silent overwrites; where there is no stamp there is\nnothing to overwrite, so projection.set() now leaves the column exactly\nalone on those axes. Meet you where you are: the user's column shape is\naccepted, refusal is reserved for genuine ambiguity.\n\nRegression tests verified to fail against the previous commit.\n\n* docs(projection): the ordinal year formula must not label month 0 as year 0\n\nThe documented one-liner `(af.month + 11) // 12` yields year 0 at the\nmonth-0 boundary, while the convention it documents (Excel ROUNDUP /\nBSCR-style ordinal) assigns the projection start to year 1 — a model\ncopying the line would have `policy_year == 1` logic skip the first row.\nThe doc now uses when/then so the month-0 choice is visible in the\nformula rather than hidden, and the test that pins the AGENTS.md\nformulas executes the ordinal line verbatim and asserts the boundary.",
          "timestamp": "2026-07-31T13:02:28+12:00",
          "tree_id": "894eb43650325832f033217d3d7a736be283e8b7",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/79e54aed7c9cf11b3eee16b3cbde0f6806c9841e"
        },
        "date": 1785460411335,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.186,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 43,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 135.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 10.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.316,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 3164.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 49.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.791,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 5583.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 298.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 475.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 89.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 17.313,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 5776,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2708.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3084,
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
            "value": 0.129,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 62,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 2.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2107.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 28.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.974,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1026.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1693.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 414,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 74.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 5.322,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1879,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 723.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1090.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 51.121,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1956.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7794.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8623.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "e5a78c1d20883d12557812713c878eb1628343af",
          "message": "fix(curves)!: clamp log_linear extrapolation in rate space; make the extrapolation parameter live (#48)\n\n* fix(curves)!: clamp log_linear extrapolation in rate space and make the extrapolation parameter live\n\nlog_linear interpolates log-discount-factors, and outside the knot range\nthe kernel clamped the log-DF LEVEL. Holding a level constant stops the\ndiscount factor decaying: a flat 5% curve returned ~1.64% at 30y (a\n30-year cashflow carried at ~2.7x its true value), and below the first\nknot the same clamp read 5%@5y as 27.6% at t=1, diverging as t -> 0.\nThe extrapolation kwarg was declared, defaulted, serialised across the\nplugin boundary — and read by nothing.\n\nNow \"flat\" (the default) holds the boundary knot's spot rate in both\ndirections, matching what flat has always meant for linear/pchip whose\nknots ARE rates. \"forward\" extends the last segment's forward rate, the\nmarket-consistent choice for long-tail discounting; it requires\nlog_linear, and rate-space methods reject it rather than ignoring it.\nUnknown modes error at Curve construction, not at collect().\n\nThe eager Python path (log_linear_spot) had the identical defect and is\nfixed with the identical arithmetic; parity between the two paths is\nasserted across tenors and modes. canonical_form() includes\nextrapolation only when non-default, so every existing curve keeps its\nsource_sha() while a \"forward\" curve stamps differently — audit by\ndefault, without invalidating shas that predate the parameter working.\n\nBREAKING: models discounting beyond the last knot (or before the first)\nwith a log_linear curve produced overstated present values; re-run\nreconciliations after upgrading. See CHANGELOG.\n\n* fix(curves): preserve extrapolation through shifts; validate on every construction path\n\nTwo review findings, both real. The shift helpers rebuilt curves with a\nhand-written field list that omitted extrapolation (and parametric), so\na parallel- or key-rate-shifted \"forward\" curve silently became \"flat\"\n— the stressed valuation flattened its long tail while the base run\nstayed correct, which is precisely the silent divergence #31 exists to\nkill. They now rebuild with dataclasses.replace, which carries every\nfield by construction, present and future.\n\nValidation moves from the from_zero_rates call site into __post_init__:\nclassmethods, direct Curve(...) construction, and replace() all funnel\nthrough it, so an invalid interpolation/extrapolation pair can no\nlonger produce a live curve that fails (or silently evaluates flat)\nonly at collect time.\n\nRegression tests verified to fail against the previous commit.",
          "timestamp": "2026-07-31T13:16:11+12:00",
          "tree_id": "7aac2aea156cdcda930b35ac08027ee350b0d402",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e5a78c1d20883d12557812713c878eb1628343af"
        },
        "date": 1785461205975,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.371,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 21.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 35.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.428,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2336.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 57,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.455,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4073.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 290.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 467.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.804,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4201,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2717.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3091.9,
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
            "value": 0.131,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 61.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 6.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2118.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 17.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.086,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 920.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1723.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 394.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 77.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.599,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1515.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 749.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1096.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 67.578,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1479.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7616.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8453.2,
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
          "id": "ac747daec774a4fbaa292cd03c716d9afe826d00",
          "message": "Errors: attribute collect-time failures to the assigned column (#49)\n\n* feat(errors): name the offending column in collect-time failures (#39)\n\nA lazy chain failing at collect() surfaced the raw Polars error — e.g.\n\"ShapeError: list lengths differed at index 0: 6 != 3\" — with no clue\nwhich assigned column produced it: a long hunt in a 50-column model.\nThe bisect-replay machinery to attribute it (ErrorBoundaryFinder) has\nexisted since #18, but the graph it replays was only recorded under\ntraced debug runs, so in every normal run it had nothing to work with.\n\nEvery assignment is now recorded as a bare (name, expr) tuple — no\nstack inspection, unlike the traced path, because the setter is the\nmodel-build hot path. When a ShapeError, InvalidOperationError or\nSchemaError reaches the collect() boundary, the recorded assignments\nreplay against the pristine pre-assignment baseline until one\nreproduces the error class; the message then ends with the column name\nand its defining expression. Audit by default: the lineage the\nprinciples promise now reaches the error path.\n\nThe fallback contract is the safety property: on ANY ambiguity — empty\ngraph, replay that does not reproduce, failure inside the replay — the\noriginal error passes through byte-for-byte. A wrong column name costs\nmore than no column name. Structural operations (filter/join/select/\nrename/drop/sort) are not recorded, so they restart the recording\nwindow rather than risk replaying against a stale baseline.\n\ncalc-graph export ignores the bare tuples (no metadata) and still\ndemands a debug-mode run; two tests that asserted \"non-traced graphs\nstay empty\" now assert the property they actually protected — no\nTracedOperation metadata capture outside tracing.\n\n* fix(errors): harden collect-time attribution against fifteen review findings\n\nA full adversarial review of the #39 commit surfaced fifteen defects, six\nempirically reproduced. The worst was a regression of the most common\nerror path: the always-populated graph routed ordinary missing-column\nerrors into the enhanced compilation path, whose builder crashed on the\nbare tuples and re-raised the RAW Polars error — losing the friendly\ndid-you-mean panel for a simple misspelling. The compilation path now\nrequires TracedOperation records, and tuple-only graphs keep the basic\nformatting they always had.\n\nSoundness — the \"wrong name costs more than no name\" contract:\n- Traced graphs survive structural ops (calc-graph export needs them,\n  even after the decorator restores tracing off) but are marked UNSOUND;\n  both attribution and the enhanced replay refuse a graph whose baseline\n  no longer matches the live plan.\n- Multi-expression with_columns batches restart the window: every\n  expression sees the pre-batch frame live, but replay is sequential,\n  so a sibling-shadowing batch could blame a healthy column.\n- The exact-failure scan starts strictly after the known-good prefix;\n  it used to start one op early and double-apply, blaming a valid\n  self-referential dtype-changing assignment for another column's error.\n- Attribution requires the replayed error's leading message to match the\n  original, not just its class — no more pairing column A's name with\n  column B's error text.\n- Rollforward hidden-column injection is recorded (non-traced) or marks\n  the window unsound (traced) instead of silently desynchronising it.\n- Tuples are recorded AFTER the successful apply — a rejected expression\n  leaves no phantom op.\n\nCost and lifecycle:\n- Replay baselines are row-capped: diagnosis stays fast at scale, and an\n  error past the cap yields no attribution rather than a slow one.\n- A successful collect() closes the window, bounding graph growth on\n  long-lived frames and scoping replay to ops since the last success.\n- Plan logging under show_query_plan fires only for traced records,\n  restoring the pre-#39 optimize-mode behaviour.\n- AF_ERROR_MODE=off/basic disables attribution even on debug frames;\n  already-formatted exceptions are never decorated twice.\n\nCoverage:\n- run_to_parquet / run_aggregated route batch-collect failures through\n  the boundary, so the reported at-scale pain case gets the column name.\n- calc-graph export no longer misclassifies tuple-recorded columns as\n  raw model-point inputs.\n- util/__init__.pyi gains get_error_mode/set_error_mode, clearing two\n  pre-existing stubtest errors.\n\nEight new regression tests, one per reproduced finding class.",
          "timestamp": "2026-07-31T13:49:26+12:00",
          "tree_id": "b02ad59b0b73edad9176edd2a175b1d66e2fcf66",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ac747daec774a4fbaa292cd03c716d9afe826d00"
        },
        "date": 1785463291657,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.335,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 23.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.432,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2314.8,
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
            "value": 197,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.466,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4055.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 289,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 467.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.904,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4183.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2698.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3068.9,
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
            "value": 0.135,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 59.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2093.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 16.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.055,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 947.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1081.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 385,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 81.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.653,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1503.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 733.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1073.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 66.983,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1492.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7600.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8415.2,
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
        "date": 1785465884673,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.231,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 34.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 17.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.425,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2352.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 50.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.414,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4142.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 275.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 453.1,
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
            "value": 23.686,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4221.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2742.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3095.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.118,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 67.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2120.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 19.9,
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
            "value": -1742.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 378.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 82.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.5,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1538.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 771,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1103.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 71.112,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1406.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7736,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8580.1,
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
        "date": 1785540075722,
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
            "value": 37,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.433,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2309.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.958,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3380.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 296.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 474.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.248,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4301.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2725.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3101.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.198,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 40.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -623.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1498.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 17.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.019,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 981.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1092.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 406.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 79.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.342,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1576.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 731.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1091.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 67.5,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1481.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7665.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8498.4,
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
          "id": "7d426cb710d04ec83a2563f546414b6d3ea0ce0a",
          "message": "Precision/correctness audits: prospective_value boundaries, rollforward chunk invariance (+ kernel fix), lookup streaming sweep (#55)",
          "timestamp": "2026-08-02T08:15:04+12:00",
          "tree_id": "eb5c068a6d4eabef04b7ce01dc30b74ffafbd179",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/7d426cb710d04ec83a2563f546414b6d3ea0ce0a"
        },
        "date": 1785615965903,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.276,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 29,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 21.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.448,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2232.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 196.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 59.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.47,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4048.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 304.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 482.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.978,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4170.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2721.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3108.2,
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
            "value": 0.138,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 58,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 8.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2138.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 23.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.051,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 951.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1083.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 407.5,
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
            "value": 6.702,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1492.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 750.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1111.6,
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
            "value": 87.086,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1148.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7712.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8562.7,
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
        "date": 1785617772905,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.317,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 25.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 15.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.428,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2336.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 61.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 197.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 58.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.47,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4048.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 291.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 470.5,
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
            "value": 23.976,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4170.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2722.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3093.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.132,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 60.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 7.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2121.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 20.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.047,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 955.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1717.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 404.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 80.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.639,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1506.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 736.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1095.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 68.214,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1466,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7670.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8506.4,
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
          "id": "6487cea894cc04e942556c716fd678b8a9147b19",
          "message": "release: v0.7.0 — book shapes are declared, and conditionals speak strings (#57)",
          "timestamp": "2026-08-02T09:22:50+12:00",
          "tree_id": "49369f9e567c54ab72901163229492273a754257",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/6487cea894cc04e942556c716fd678b8a9147b19"
        },
        "date": 1785619996371,
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
            "value": 37.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.452,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2212.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 58,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.5,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4000,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 296.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 473.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.693,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4220.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2723.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3096.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.121,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 66.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2121.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 29.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.017,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 983.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1719.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 401.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 81.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.554,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1525.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 746.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1102.8,
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
            "value": 76.793,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1302.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7655.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8498.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.7,
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
          "id": "5fbf6bb863062eeb502644c917716c01bcf12912",
          "message": "fix(errors): attribute plan-lowering panics through the collect boundary (#54) (#59)\n\nA schema mismatch inside a when().then() branch fails during IR plan\nlowering, where polars panics ('no valid schema can be derived') instead\nof raising a typed error. pyo3 surfaces that as PanicException — a\nBaseException subclass — which sailed past both 'except Exception' at the\ncollect()/profile() boundary and the #39 attribution gate, reaching the\nmodel author as a bare Rust panic naming nothing. In the field this cost\na statement-level bisect of a ~500-line Solvency II model to localise one\nbad assignment.\n\nThe boundary now converts that panic into a catchable SchemaError\ncarrying the standard attribution block (failing column + defining\nexpression), chained to the original panic:\n\n- is_plan_lowering_panic() matches the panic narrowly (type name +\n  message) — pyo3_runtime is a synthetic module, so no import.\n- The replay probes catch BaseException, guarded so anything that is\n  neither an Exception nor this panic (interrupts, foreign panics)\n  re-raises immediately.\n- attribute_collect_failure() admits the panic alongside the existing\n  attributable error classes; replay matches it by class + leading\n  message like any other failure.\n- _handle_plan_lowering_panic() converts only when attribution succeeds;\n  an unattributed panic passes through untouched per the fallback\n  contract (never rewrite an error into something that merely looks\n  diagnosed).\n\nLLM-shaped from the inside out: plan-lowering panics were exactly the\nfailures that needed the named-column contract most, and the only ones\nthat bypassed it. Tests use raw pl.Expr branches so the repro stays\nfailing after #53 fixes proxy-built expressions.",
          "timestamp": "2026-08-02T18:14:03+12:00",
          "tree_id": "1d3a5ad0a7eab23bb4e246fe10e6ba4355a715e0",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5fbf6bb863062eeb502644c917716c01bcf12912"
        },
        "date": 1785651827086,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.579,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 13.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 11.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.306,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 3268,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 52.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.766,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 5662.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 319.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 477.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 89.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 17.811,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 5614.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2693,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3072.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.092,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 87,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 3.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2096.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 0,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 0,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.883,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1132.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1727.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 369.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 73.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 4.932,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 2027.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 781.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1104.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 94.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 63.055,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1585.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7746.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8589.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "45f40180e80b0fbfeee33d10075cd2f8fd40c78b",
          "message": "chore(deps): bump event-listener 5.4.1 -> 5.4.2 (RUSTSEC-2026-0221) (#58)\n\nTransitive via polars-stream -> async-channel. Affected versions\nunconditionally implement Send/Sync for the listener! macro's StackSlot,\nletting a !Send tag set via Event::with_tag cross threads — a data race\nin safe code. Practical exposure here is nil (async-channel uses untagged\nevents), but the advisory fails every push-to-main osv scan with\n--fail-on-vuln, so main has scanned red since 2026-08-01. Patch-level\ndrop-in; no other packages move.",
          "timestamp": "2026-08-02T18:51:46+12:00",
          "tree_id": "de7e8d0aa7db775a40f160594393d3142442bd81",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/45f40180e80b0fbfeee33d10075cd2f8fd40c78b"
        },
        "date": 1785654164812,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.237,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 33.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 28.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.439,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2277.9,
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
            "value": 195.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 58.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.437,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4103.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 302,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 479.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 23.846,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4193.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2861.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3038.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.128,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 62.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 7.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2065,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 29.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.082,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 924.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1708.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 356.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 78.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.59,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1517.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 763.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1074.2,
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
            "value": 66.004,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1515.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7609.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8425,
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
          "id": "b63d7c1ab442e1bfac82cf0e912438aabf94e0f6",
          "message": "fix(column): make scalar/list broadcast order-independent for + and - (#53) (#60)\n\npolars broadcasts a scalar into list arithmetic only when the scalar side\nis a leaf (bare column or literal) — a compound scalar expression\n(col * col) against a list operand fails supertype derivation, and only\nfor add/sub (mul/div/floordiv/mod broadcast fine). The failing boundary\nis erratic at the raw level: (a*b) + col_list fails while col_scalar +\ncol_list works, and even col_list + (a*b) fails while (a*col_list) +\n(a*b) works. So the natural actuarial shape\nAnnPrem*ExpsPerPrem + (SA*ExpsPerSA + ExpsPol)*InflFactor lived or died\non operand order — three instances found in the wild during the v0.6.0\nfield test, all 'fixed' by flipping operands.\n\nThe dispatch layer now compensates, shape-driven rather than replicating\npolars' quirk boundary: when one operand of +/- is a compound scalar\n(ExpressionProxy with scalar shape) and the other is list-shaped, the\ncompound side is pre-broadcast with repeat_by to the list side's per-row\nlengths (jagged-safe) and the op executes as native list-list\narithmetic. Bare columns, literals, and the working operators keep their\nexisting native plans; unknown shapes are left alone rather than\nguessed.\n\nMeet you where you are: the formula as written in the spec is the\nformula in the code — requiring an operand-ordering rule to make +\ncommute broke that. Sharp knives: the previous behaviour was not a\nprincipled refusal (the same expression worked when mirrored).\n\n13 new tests pin order-independence for + and -, subtraction\nantisymmetry, untouched * and /, the when()-branch shape, and jagged\nper-row broadcasting. Full suite: 2,812 passed.",
          "timestamp": "2026-08-02T20:01:21+12:00",
          "tree_id": "17ef386f55253b8c0fb5a35900a983c86939e8f3",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b63d7c1ab442e1bfac82cf0e912438aabf94e0f6"
        },
        "date": 1785658190189,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.223,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 35.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 19.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.35,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2857.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 196,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 50.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.967,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 5083.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 297.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 476.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 20.375,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4908,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2709.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3095,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.118,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 67.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 6.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2207.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 30.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.194,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 837.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1836,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 371.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 81.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.757,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1479.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 746.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1075.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 62.742,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1593.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7474,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8316.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "6f57792bbf110519c8aa5f99d26a401196db4358",
          "message": "fix(scenarios): refuse scenario_id-carrying base tables in shocks-dict stacking (#52) (#61)\n\nstack_shocked_table stamps pl.lit(sid) over scenario_id on every\nbase_tables entry — a table already keyed by a scenario axis had its\noriginal scenarios silently collapsed onto one batch key. Before strict\ntable builds (#17) this last-write-won silently: the shipped scenarios\ndocs example printed 1714.28 (every scenario priced at the UP rate)\nwhere the true per-scenario answer is 1748.01. After #17 it became a\n'Duplicate key combination at source row N' error — loud, but far from\nthe cause and naming neither the table's existing scenario axis nor the\nfix.\n\nThe stacking boundary now raises upfront, naming the table, its existing\nscenario_id dimension, and both remedies: keep the table\nscenario-invariant and express per-scenario differences as shocks (the\nshocks-dict contract), or pass the scenario-keyed table through the\nid-list/drivers shapes, where base_tables reach the model untouched.\n\nSharp knives, no magic: refuse to run rather than silently fill in a\nfallback that looks right until the regulator asks. The docs side was\nhandled in opioinc/gaspatchio-docs#8; this is the core guard.\n\nFour new tests: the refusal, the message contract (table + axis + both\nremedies), the scenario-invariant happy path untouched, and the\nScenarioRun entry point surfacing the guard instead of the deep\nduplicate-key error. Full suite: 2,803 passed.",
          "timestamp": "2026-08-02T20:28:51+12:00",
          "tree_id": "ae68e2dd73c32b186f7cb2f4b9490d4964279442",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/6f57792bbf110519c8aa5f99d26a401196db4358"
        },
        "date": 1785659967305,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.27,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 29.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 135.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.449,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2227.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 58.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.567,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3895.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 290.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 469,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 25.156,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3975.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2685.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3067.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.13,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 61.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 3.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2179.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 19.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.15,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 869.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1817.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 361.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 77.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.953,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1438.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 753.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1073.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 71.546,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1397.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7415.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8254.2,
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
        "date": 1785664152873,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.24,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 33.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 12.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.335,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2985.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 59.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 196.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 57.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.97,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 5076.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 311,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 490.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 19.747,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 5064.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2692.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3092.2,
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
            "value": 0.091,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 87.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2199.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 0,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 0,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.878,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1139,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1819.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 380.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 74.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 5.328,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1876.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 763.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1104,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 54.561,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1832.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7534.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8405.6,
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
        "date": 1785737951372,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.222,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 36,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 20.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.452,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2212.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 63.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.548,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3924.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 288.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 467.4,
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
            "value": 32.656,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3062.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2660.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3041.6,
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
            "value": 0.276,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 29,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -1243.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 904.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 44.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.385,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 722,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -533.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 371.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 85.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 9.9,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1010.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 735.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1064.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 75.15,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1330.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7615.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8157.8,
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
          "id": "03df6ed7f6fa780a2a856572fbb8f74bbf52300f",
          "message": "fix(rollforward): broadcast scalar inputs; name the NAR timing convention on deduct_nar (#65)\n\n* fix(rollforward): accept scalar input columns and broadcast across periods\n\nA level death benefit or a flat charge rate is naturally one value per\npolicy, but every rollforward input had to be a List column, so callers\nhad to materialise n_periods identical copies of the same number. That is\nceremony with no meaning, and the error when they didn't (\"must be List\ndtype\") named the symptom rather than the fix.\n\nScalar (numeric, non-List) inputs are now broadcast across the period\naxis. List inputs are untouched, so existing plans produce bit-identical\nresults.\n\nThree sites inferred period counts from owned_slices[0], which with a\nscalar column registered first would read a horizon of 1 and reject every\npolicy: the row count, the uniform-schedule guard, and the per-row length\ncheck. All three now consider only genuine per-period lists, and a\nregression test registers the scalar column first to hold that.\n\nThe dtype is checked before casting rather than relying on the cast to\nfail: polars casts String to Float64 as nulls, so a string input would\notherwise have surfaced as \"null value not supported\" instead of naming\nthe real problem.\n\nServes Meet you where you are — accept the shape the assumption already\nhas, rather than making the user reshape it to suit the kernel.\n\n* feat(rollforward): name the NAR timing convention on deduct_nar\n\ndeduct_nar measured the net amount at risk where the charge was taken and\napplied no discount. That is one mainstream universal life convention. The\nother charges COI at the start of the period for a death benefit paid at\nthe end, so the amount at risk is measured against the accumulated balance\nand the charge is discounted back — and it was not expressible.\n\nThe two agree under constant rates and diverge once rates vary, silently:\nboth produce plausible account values and nothing errors. On a 5-year\nprojection at 3% credited the account values differ by 0.24% in year one\nand 0.74% by year five, widening throughout.\n\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face)   # unchanged default\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face,\n                       nar_timing=\"end_of_period\",\n                       coi_discount_rate=af[\"coi_disc\"],\n                       credited_rate=af[\"credited\"])\n\nUnder end_of_period the COI and the balance are mutually dependent, since\ndeducting the charge lowers the balance and so raises the amount at risk.\nThe kernel solves that in closed form rather than iterating:\n\n    NAR = (death_benefit - s*accum) / (1 - coi_rate*accum*v)\n\nnar_timing reuses beginning_of_period / end_of_period, the vocabulary\nprospective_value and cumulative_survival already use — this is the third\ntiming-sensitive method in the API and should not introduce a third\nvocabulary. The default is unchanged and bit-identical.\n\nThe rates are separate arguments rather than inferred from a neighbouring\ngrow(): the COI discount rate is its own product assumption, distinct from\nthe credited rate. Passing either without end_of_period raises rather than\nbeing silently ignored, and an unknown nar_timing names the valid options.\n\nNaming the convention also avoids an argument whose identity value would\nnot reproduce the default: an inferred discount of 1.0 gives the\nsimultaneous solve, not the beginning-of-period form, so \"pass 1.0\" and\n\"omit it\" would have disagreed.\n\nVerified against an external universal life workbook that uses the\nend-of-period convention: NAR matches its cached 497,761.78 to floating\npoint, COI and closing account value to within its own 2dp rounding.\n\nServes Sharp knives, no magic — the convention is visible at the call site\ninstead of folded into a rate — and Meet you where you are.\n\nRefs GSP-119, #64\n\n* fix(rollforward): refuse an end-of-period NAR without its rates\n\nBoth rate factors default to 1.0 in the kernel. Left to default under\nnar_timing=\"end_of_period\" they do not degrade gracefully — they produce the\nsimultaneous-solve convention, a third real convention this API deliberately\ndoes not expose. A forgotten argument therefore returned a different answer\nrather than an error, and a plausible one: the account value still looks like\nan account value.\n\nverify() already refused the mirror-image mistake (rates supplied with\nbeginning_of_period). This closes the asymmetry and names which rate is\nmissing rather than listing both.\n\nAlso admit a Boolean scalar input. The List path casts its inner values\nunconditionally, so a per-period condition mask already worked, while the\nscalar branch gated on is_numeric() — false for Boolean. A policy-level flag,\nsuch as a ratchet's `when=`, was accepted as a list of repeats and refused as\nthe single value it naturally is.\n\nAdds Python coverage for scalar broadcast, which had none: scalar-equals-\nrepeated-list for float, int and Boolean, the all-scalar case that has no List\ncolumn to read a horizon from, and the String refusal.\n\nBoth found by Greptile on #65.",
          "timestamp": "2026-08-05T16:46:05+12:00",
          "tree_id": "e25f97f9b3c8c726a1195627dfb6afd4c1e44e5c",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/03df6ed7f6fa780a2a856572fbb8f74bbf52300f"
        },
        "date": 1785905702157,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.221,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 36.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 18.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.376,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2659.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 45.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.536,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 6510.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 303,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 480.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 87.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 14.633,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 6833.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2601.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 2991.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.081,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 98.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2101.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 0,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 0,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.585,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1709.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 66.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2168.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 73.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 4.104,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 2436.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": -1007.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1119.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 94.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 42.105,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 2375,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7435.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8320.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.1,
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
          "id": "705843f5ea20d3254ee4b9cde718ea1708b10c1e",
          "message": "feat(rollforward): add a Round op for models that round inside the recursion (#74)\n\n* fix(rollforward): accept scalar input columns and broadcast across periods\n\nA level death benefit or a flat charge rate is naturally one value per\npolicy, but every rollforward input had to be a List column, so callers\nhad to materialise n_periods identical copies of the same number. That is\nceremony with no meaning, and the error when they didn't (\"must be List\ndtype\") named the symptom rather than the fix.\n\nScalar (numeric, non-List) inputs are now broadcast across the period\naxis. List inputs are untouched, so existing plans produce bit-identical\nresults.\n\nThree sites inferred period counts from owned_slices[0], which with a\nscalar column registered first would read a horizon of 1 and reject every\npolicy: the row count, the uniform-schedule guard, and the per-row length\ncheck. All three now consider only genuine per-period lists, and a\nregression test registers the scalar column first to hold that.\n\nThe dtype is checked before casting rather than relying on the cast to\nfail: polars casts String to Float64 as nulls, so a string input would\notherwise have surfaced as \"null value not supported\" instead of naming\nthe real problem.\n\nServes Meet you where you are — accept the shape the assumption already\nhas, rather than making the user reshape it to suit the kernel.\n\n* feat(rollforward): name the NAR timing convention on deduct_nar\n\ndeduct_nar measured the net amount at risk where the charge was taken and\napplied no discount. That is one mainstream universal life convention. The\nother charges COI at the start of the period for a death benefit paid at\nthe end, so the amount at risk is measured against the accumulated balance\nand the charge is discounted back — and it was not expressible.\n\nThe two agree under constant rates and diverge once rates vary, silently:\nboth produce plausible account values and nothing errors. On a 5-year\nprojection at 3% credited the account values differ by 0.24% in year one\nand 0.74% by year five, widening throughout.\n\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face)   # unchanged default\n    b[\"av\"].deduct_nar(coi_rate, death_benefit=face,\n                       nar_timing=\"end_of_period\",\n                       coi_discount_rate=af[\"coi_disc\"],\n                       credited_rate=af[\"credited\"])\n\nUnder end_of_period the COI and the balance are mutually dependent, since\ndeducting the charge lowers the balance and so raises the amount at risk.\nThe kernel solves that in closed form rather than iterating:\n\n    NAR = (death_benefit - s*accum) / (1 - coi_rate*accum*v)\n\nnar_timing reuses beginning_of_period / end_of_period, the vocabulary\nprospective_value and cumulative_survival already use — this is the third\ntiming-sensitive method in the API and should not introduce a third\nvocabulary. The default is unchanged and bit-identical.\n\nThe rates are separate arguments rather than inferred from a neighbouring\ngrow(): the COI discount rate is its own product assumption, distinct from\nthe credited rate. Passing either without end_of_period raises rather than\nbeing silently ignored, and an unknown nar_timing names the valid options.\n\nNaming the convention also avoids an argument whose identity value would\nnot reproduce the default: an inferred discount of 1.0 gives the\nsimultaneous solve, not the beginning-of-period form, so \"pass 1.0\" and\n\"omit it\" would have disagreed.\n\nVerified against an external universal life workbook that uses the\nend-of-period convention: NAR matches its cached 497,761.78 to floating\npoint, COI and closing account value to within its own 2dp rounding.\n\nServes Sharp knives, no magic — the convention is visible at the call site\ninstead of folded into a rate — and Meet you where you are.\n\nRefs GSP-119, #64\n\n* fix(rollforward): refuse an end-of-period NAR without its rates\n\nBoth rate factors default to 1.0 in the kernel. Left to default under\nnar_timing=\"end_of_period\" they do not degrade gracefully — they produce the\nsimultaneous-solve convention, a third real convention this API deliberately\ndoes not expose. A forgotten argument therefore returned a different answer\nrather than an error, and a plausible one: the account value still looks like\nan account value.\n\nverify() already refused the mirror-image mistake (rates supplied with\nbeginning_of_period). This closes the asymmetry and names which rate is\nmissing rather than listing both.\n\nAlso admit a Boolean scalar input. The List path casts its inner values\nunconditionally, so a per-period condition mask already worked, while the\nscalar branch gated on is_numeric() — false for Boolean. A policy-level flag,\nsuch as a ratchet's `when=`, was accepted as a list of repeats and refused as\nthe single value it naturally is.\n\nAdds Python coverage for scalar broadcast, which had none: scalar-equals-\nrepeated-list for float, int and Boolean, the all-scalar case that has no List\ncolumn to read a horizon from, and the String refusal.\n\nBoth found by Greptile on #65.\n\n* feat(rollforward): add a Round op for models that round inside the recursion\n\nSpreadsheet source models round to cents at every step, and that rounded\nbalance opens the next period. Rounding only the final answer is a\ndifferent calculation: the difference is invisible early and material\nlate. Converting a universal life workbook, the account value drifted\n0.0023 in year 1 and 0.215 by year 55 -- monotonically, because each\nperiod's rounding fed the next.\n\n    b[\"av\"].deduct_nar(...)\n    b[\"av\"].round(2)          # the workbook rounds the COI here\n    b[\"av\"].grow(rate)\n    b[\"av\"].round(2)          # ...and the interest credited here\n\nWith the op in place that workbook ties out to 1.7e-15 on the closing\naccount value across all 56 live years, against 2.0e-05 without it.\n\nRounds half away from zero -- Excel's ROUND, which is also what Rust's\nf64::round() does -- not banker's rounding. The op exists to reproduce\nspreadsheets, so the tie-breaking rule is load-bearing rather than a\ndetail: the same workbook's year-6 surrender charge is exactly 7,558.485,\nwhich banker's rounding sends to 7,558.48 and Excel to 7,558.49.\nA test pins the divergence so the choice cannot be quietly reversed.\n\nWhere the running balance is already an exact multiple of the rounding\nunit, rounding the state is equivalent to rounding the charge just\napplied to it -- which is what makes this able to stand in for a\nROUND() wrapped around an individual term.\n\nRefs GSP-119\n\n* fix(rollforward): keep Round from overflowing a huge finite state\n\nRounding scales by 10^decimals before calling round(). Above roughly 1e306\nthat multiply overflows, so a representable balance became infinity and\npoisoned every later period — silently, since the op already skipped\nnon-finite values and this one was finite on the way in.\n\nGuard on the scaled value rather than the input. A state that large has no\ndecimal places left to round to anyway, f64 having run out of precision well\nbefore, so passing it through unchanged is both safe and correct.\n\nFound by Greptile on #74.",
          "timestamp": "2026-08-05T17:56:02+12:00",
          "tree_id": "310a0363a8df7d58a7b4a1a5f412ec2301921643",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/705843f5ea20d3254ee4b9cde718ea1708b10c1e"
        },
        "date": 1785909899697,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.561,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 14.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.344,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2907,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 56.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 192.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 56.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.783,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 5608.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 314.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 471.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 89.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 17.095,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 5849.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2681.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3060.1,
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
            "value": 0.239,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 33.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -1291,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 874.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 40.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.791,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1264.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -516.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 358,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 78.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 5.303,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1885.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 758.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1075.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 59.492,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1680.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7480.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8325.5,
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
          "id": "960b645f7eedf9d05a15c41b63b1d8a88c70f7de",
          "message": "docs(skills): add a spreadsheet-to-gaspatchio translation reference (#76)\n\n* docs(skills): add a spreadsheet-to-gaspatchio translation reference\n\nDiscovery's step 0 runs `gspio describe` on data files, which does not\napply to a workbook, and its own red-flag table says Excel models must be\n\"mapped first\" without offering any means to map them. This fills that\ngap.\n\nThe reference covers what a workbook's structure implies about the model\nyou should write. Its value is the third column of the translation table:\nevery row names the failure that is silent. These are conversions that\nproduce a model which runs and is wrong, not one that fails.\n\n  - SCC members that read as plain schedule lookups but sit inside the\n    recursion because of an IF(prior > 0, ...) lapse gate. Written as\n    closed-form columns they are correct until the policy lapses, and\n    most test policies never do.\n  - Three COI timing conventions, not two, which agree under constant\n    rates -- so the error survives every test built on flat assumptions.\n  - ROUND() inside a recursion versus after it: monotonic drift that\n    reads as a formula error and is not.\n  - Approximate-match VLOOKUP silently reusing the last row past a\n    table's end, where our exact-match lookup raises instead.\n\nIt also makes \"closed-form by default\" mechanical rather than a\njudgement call: every strongly-connected component of size > 1 is a\nrollforward state, everything else is closed-form. That is a query\nagainst the binding graph, not an opinion.\n\nDeliberately does not duplicate the xl-marinade skill, which owns the CLI\nand query surface. This covers only what to do with the results, so the\ntwo compose instead of competing for the same routing.\n\nAdds a red-flag row for reading only the first data row: formula_pattern\nreports the dominant pattern, and spreadsheets routinely special-case\nrow 1 -- which is exactly where a lapse gate hides.\n\nWritten from converting a universal life workbook end to end; every entry\nis a mistake that was available to make.\n\n* docs(skills): recalculate the workbook rather than reimplementing it\n\nThe reference told you to treat a workbook's cached outputs as the gold\nstandard, which is right but incomplete: cached values only cover the one set\nof inputs the file happens to be saved with. Branches that never fire on\nthose inputs — a corridor test, a guarantee, a mass-lapse trigger — have no\nreference at all, and that is exactly where conversion bugs hide.\n\nFormula engines (formulas, pycel) evaluate a workbook's real formula text, so\nan input can be changed and a genuine reference read back. Adds the three\nrules that make the result trustworthy: validate the engine against the\ncached values before believing it, exploit the fact that schedules are\nusually one hardcoded cell with the rest cascading, and build the\ncounterfactual by editing the workbook's formula to match the model's\nbehaviour so both halves of the comparison come from the workbook.\n\nAlso names the trap directly, because it fails silently: openpyxl and\nxlsxwriter write formula strings and never evaluate them, so a workbook\nedited with either comes back holding the formula and no value.\n\nFound doing this for real — see gaspatchio#77, where the corridor failure is\ndemonstrated by the workbook computing it with one formula changed.",
          "timestamp": "2026-08-05T18:10:15+12:00",
          "tree_id": "bfd6c3e82a0d8d8bec516cea9dbc9e94d6c3ed0f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/960b645f7eedf9d05a15c41b63b1d8a88c70f7de"
        },
        "date": 1785910878149,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.237,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 33.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 21,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.456,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2193,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 193.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 63.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.589,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3862.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 287.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 465.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 92,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 26.304,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3801.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2668.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3042.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.129,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 62,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2150.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 28.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.142,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 875.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1786.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 364,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 76.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 7.014,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1425.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 737.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1058.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 72.44,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1380.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7515.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8343.2,
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
        "date": 1785913185079,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.294,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 27.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 10.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.448,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2232.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 196.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 61.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.567,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3895.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 291.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 470.3,
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
            "value": 25.165,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3973.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2741.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3123.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.137,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 58.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 4.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2232.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 16.7,
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
            "value": -1853.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 379.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 76.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.899,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1449.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 720.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1057.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 70.627,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1415.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7440.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8264.8,
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
        "date": 1786137583144,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.268,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 29.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 21.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.462,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2164.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 68.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.608,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3834.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 301.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 480.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 24.971,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4004.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2711.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3101.6,
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
            "value": 0.183,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 43.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 5.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2215.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 28.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.083,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 923.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 118,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 354.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 83.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 7.836,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1276.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 766.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1079.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 96.248,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1039,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7461.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8306.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "239c92c7f5beec9d340de6aefee4d46a0028ebe3",
          "message": "docs: make CONTRIBUTING canonical, add code of conduct and PR template (#87)\n\n* chore(gitignore): ignore .claude/worktrees/\n\nAgent worktrees under .claude/worktrees/ carry a full bindings/python/.venv.\nOne stale worktree left 6.7 GB untracked at the repo root — 21,727 vendored\nfiles that break `reuse lint` locally and sit one `git add .` away from being\ncommitted. CI never catches this because it checks out clean.\n\nxl-marinade already ignores this path; gaspatchio ignored three other .claude\npaths but not this one.\n\n* docs: make CONTRIBUTING canonical, add code of conduct and PR template\n\nContribution rules lived only in AGENTS.md, which coding agents read and human\ncontributors never see. GitHub surfaces CONTRIBUTING.md as a banner when someone\nopens an issue or a PR, and counts it in community standards — that is where the\nrules belong.\n\nCONTRIBUTING.md is now canonical for humans and agents alike: branch-vs-fork\nguidance (including which workflows fork PRs cannot run, since evals.yml and\ntrigger-rag-rebuild.yml need real secrets), the bindings/python working-directory\nrule, signing setup for the signed-commits ruleset now active on main, the\nissue-title convention, PR scope, and the merge policy. AGENTS.md keeps only what\ndiffers when there is no human in the loop and points at it.\n\nAdds the Contributor Covenant 2.1 and a PR template that asks which principle a\nchange serves and which it strains, and — for anything moving a projected number —\nbefore/after on a reproducible model point with the timing convention stated,\nsince constant rates hide that class of error entirely.\n\nCloses the CONTRIBUTING, CODE_OF_CONDUCT and pull_request_template gaps in\nGitHub's community standards checklist.\n\n* docs: regenerate copilot-instructions after the AGENTS.md change\n\n.github/copilot-instructions.md is generated from AGENTS.md by\nscripts/gen_skill_manifests.py, and tests/skills/test_skill_manifests.py asserts\nthe two stay in sync. The previous commit edited the source without regenerating.\n\n* docs: correct the signing guidance — squash does not sidestep the rule\n\nThe claim that unsigned commits need no rewrite because a squash merge produces a\nsingle signed commit is wrong, and was proven wrong on gaspatchio/xl-marinade#3:\n`gh pr merge --squash` was refused with \"the base branch policy prohibits the\nmerge\". GitHub evaluates required_signatures against every commit in the PR and\nrefuses before it creates the squash commit.\n\nUnsigned commits must be re-signed, which means a rebase. Says so now, and points\ncontributors at a maintainer rebase rather than leaving them to untangle it.\n\n* docs(pr-template): guard the changelog against concurrent-merge clobber\n\nThe template asked for a CHANGELOG entry only when the public API changed, and\nsaid nothing about the case that actually bites: two PRs editing the same\nchangelog block, the later merge silently winning with no test to catch it.\nThat happened on gaspatchio/xl-marinade#8, whose speedup vanished from its\nrelease notes.\n\nMakes the entry conditional on user-visible change rather than API surface, and\nadds an explicit re-check when main has moved under an open PR.",
          "timestamp": "2026-08-08T11:06:54+12:00",
          "tree_id": "a73d21674a045774bfbdf59221773d69e6e38b77",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/239c92c7f5beec9d340de6aefee4d46a0028ebe3"
        },
        "date": 1786144674638,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.267,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 30,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.433,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2309.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 58.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 195.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 62.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.55,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3921.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 291,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 470.1,
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
            "value": 24.683,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4051.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2702.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3082.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.232,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 34.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -691.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 1496.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 40.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.183,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 845.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -522.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 356.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 83.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 7.214,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1386.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 761.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1074.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 87.111,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1148,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7442.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8283.2,
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
        "date": 1786147021506,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.284,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 28.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 36.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 39.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.76,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 1315.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 68.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.839,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3522.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 302.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 480.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 90.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 25.728,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3886.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2604.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 2995.9,
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
            "value": 0.125,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 64,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 6.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2108.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 21.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.155,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 865.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1722.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 386.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 75.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.892,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1451,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 740.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1084.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 96.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 71.653,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1395.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7647.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8497.3,
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
          "id": "5310176fbf7e13c402841d53f487a3c39799d9ee",
          "message": "fix(assumptions): lookup() cooperates with proxies in either operand order (#84)\n\n* fix(assumptions): lookup() cooperates with proxies in either operand order\n\npl.Expr's binary operators raise on a ColumnProxy/ExpressionProxy operand\ninstead of returning NotImplemented, so Python never offers the proxy its\nreflected method — lookup(...) * af.v raised while af.v * lookup(...)\nworked. Which of two mathematically identical spellings crashes is exactly\nthe kind of trap the formula-is-the-code promise forbids.\n\nlookup() now returns ProxyAwareExpr, a pl.Expr subclass whose operators\nunwrap a proxy operand to its underlying expression and re-wrap their\nresults, so the property survives operator chains\n(lookup * af.a * af.b). isinstance(x, pl.Expr) stays true — no new type\nfor callers to know about, and every existing annotation still holds.\n\nCloses #67.\n\n* fix(column): delegate proxy-operand operators to the proxy layer; extend the contract to rollforward and Schedule exprs\n\nReview hardening of the gh#67 fix. The red-team probe matrix caught a\nreal divergence in the first design: unwrapping the proxy operand and\ndelegating to raw polars bypassed the proxy layer's operator shims, so\nlookup(...) ** af.list_col raised (polars has no list pow) while the\nreverse order worked — the same asymmetry class gh#67 describes, one\nshape up.\n\nProxyAwareExpr now hands a proxy operand the whole operation via the\nreflected operator: the proxy layer stays the single owner of operator\nsemantics, current and future shims included, and the result is the\nframe-native ExpressionProxy with the full accessor surface. Non-proxy\noperands delegate to polars unchanged and re-wrap.\n\nThe same either-order contract now covers the other bare-Expr surfaces a\nmodel combines with af columns — CompiledRollforward.expr_for /\nincrement_for, the collector's self-contained exprs, and the\nSchedule.*_expr family.\n\nA 40-cell operator x shape x operand-order matrix checks every cell\nagainst a pure-Python reference so the two dispatch routes can never\ndiverge silently. One cell is xfail: scalar base ** list-valued\nexpression exponent, a pre-existing proxy-layer gap (gh#89). The\noperator-only boundary of the guarantee is documented in the module and\nlookup docstrings; the raise-not-NotImplemented root cause is filed\nupstream as pola-rs/polars#28748.",
          "timestamp": "2026-08-08T12:29:02+12:00",
          "tree_id": "a4538836236d2a4fc25d12a0c4be3489e06ab523",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5310176fbf7e13c402841d53f487a3c39799d9ee"
        },
        "date": 1786149473669,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.164,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 48.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 137.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 15.4,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.269,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 3717.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 56.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 57.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 1.502,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 6657.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 275.7,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 454.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 89.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 14.698,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 6803.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2693.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3059.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 98.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.215,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 37.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -1310.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 854,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 20.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.722,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1385,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -510.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 343.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 76.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 4.154,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 2407.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 757.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1060.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 94.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 42.192,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 2370.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7451.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8278.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/100K-cpu-avg",
            "value": 99.3,
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
          "id": "51a86c110bfb73b98191269ee2e564aee6bb754b",
          "message": "release: v0.8.0 — rounding is requested by name, and lookups commute (#90)\n\nThe v0.6.0 field-test issue batch (#66–#68, #70–#73) plus the preceding\nrollforward hardening. New: .excel.round with Excel's half-away-from-zero\non per-period columns (the never-implemented panicking wrappers are\nremoved), a rollforward Round op on the same rule by design, and a\ncorridor test on deduct_nar with a negative NAR refusing to run. Fixed:\nlookup() and the other bare-Expr surfaces cooperate with proxies in\neither operand order, only declared columns become dimension keys, scalar\nrollforward inputs broadcast across periods, and the length-mismatch\nerror points at what fails. Plus the cryptography 50.0.0 bump and the\nreviewed pymdown advisory filter.\n\nVersion stamps in core/Cargo.toml, bindings/python/Cargo.toml,\nbindings/python/pyproject.toml; Cargo.lock and uv.lock regenerated\n(uv lock --check passes).",
          "timestamp": "2026-08-08T13:38:48+12:00",
          "tree_id": "2063e3a8d0ce1f82739353fa8ebc58601be1dad2",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/51a86c110bfb73b98191269ee2e564aee6bb754b"
        },
        "date": 1786153773637,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.294,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 27.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 37.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 136.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 16.7,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.454,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2202.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 57.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 194.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 59.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.559,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 3907.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 295.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 473.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 91,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 25.801,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 3875.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 2717.6,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3102,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.13,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 61.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 5.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2215.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 29.2,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 1.11,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 900.9,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -1822.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 393,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 81.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.939,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1441.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 739.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 1091.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 97.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 71.706,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1394.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 7461.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 8319.8,
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