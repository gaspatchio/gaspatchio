window.BENCHMARK_DATA = {
  "lastUpdate": 1783459781979,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Model Benchmarks": [
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
        "date": 1783392597368,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.107,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 74.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 54.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 221.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 20.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.385,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2597.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 40.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 261.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 68.7,
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
            "value": 331.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 577.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 21.798,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4587.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3261.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3745.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.4,
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
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 3045,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 20.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.868,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1152.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -162.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2882.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.214,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1609.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 457.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3338.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 61.985,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1613.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 6595.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9873.3,
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
          "id": "b89205ba8938cedd55067243082eefe26af2cb65",
          "message": "ci(evals): run OSS benchmarks on free standard runners; gate private suites\n\nThe benchmark jobs requested larger runners (ubuntu-latest-m / windows-m) that\nare only defined on the private org, so they queued forever on the public repo.\nSwitch the public-safe suites (Criterion, Model, Aggregation) to free standard\nrunners (ubuntu-latest / windows-latest), which are unlimited for public repos.\n\nGate the jobs that cannot run publicly to the private repo:\n- comparison-benchmarks (Gaspatchio vs Lifelib) clones the private\n  opioinc/gaspatchio-benchmarks reference data via a deploy key;\n- skill-evals + capability-matrix need paid ANTHROPIC/OPENAI API keys.\nThese stay disabled on the public repo until their secrets are provisioned.",
          "timestamp": "2026-07-07T14:42:36+12:00",
          "tree_id": "a424805d092e630ba336b1c3aaee85beae6b2325",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/b89205ba8938cedd55067243082eefe26af2cb65"
        },
        "date": 1783392597368,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.107,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 74.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 54.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 221.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 20.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.385,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2597.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 40.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 261.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 68.7,
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
            "value": 331.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 577.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 21.798,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4587.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3261.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3745.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.4,
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
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 3045,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 1,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 20.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.868,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1152.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -162.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2882.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.214,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1609.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 457.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3338.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 61.985,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1613.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 6595.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9873.3,
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
          "id": "e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7",
          "message": "ci(evals): enable Gaspatchio vs Lifelib comparison on the public repo\n\nBENCHMARKS_DEPLOY_KEY (read-only deploy key for opioinc/gaspatchio-benchmarks)\nis now configured as an Actions secret on gaspatchio/gaspatchio, so the\ncomparison job can clone the lifelib reference data. Restore its normal trigger\n(schedule / dispatch / push-main / benchmark label); it runs on the free\nstandard runners with the other public suites and publishes to dev/comparison.",
          "timestamp": "2026-07-07T14:57:55+12:00",
          "tree_id": "9765b961fc48b4d840b2c4c8a2229bb01a04a978",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/e68f4e0d78ae2b80ac60932bb2f1c6ff58a9bbf7"
        },
        "date": 1783393538436,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.112,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 71.4,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 54.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 221,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 18.2,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.398,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2512.6,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 42.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 262.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 72.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.3,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4347.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 331.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 578.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 96.6,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 21.783,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4590.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3286.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3765.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.096,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 83.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -102,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2917.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 40.9,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.88,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1136.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 27.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2838.3,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.1,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.23,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1605.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 491.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3329.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 61.906,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1615.4,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 6687.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9841.2,
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
        "date": 1783395010373,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.108,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 74.1,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 52.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 221.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 17.9,
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
            "value": 46.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 263.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 69.5,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.319,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4312.2,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 337.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 581.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 95.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 21.828,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4581.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3263.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3746.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.094,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 85.1,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": 1.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 3047.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 55.8,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.877,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1140.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -7.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 3039.4,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.3,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.205,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1611.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 370.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3408.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 61.814,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1617.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 6488.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9866.6,
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
        "date": 1783418833343,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.106,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 75.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 58.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 223.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 18.8,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-points",
            "value": 0.391,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-throughput",
            "value": 2557.5,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-memory",
            "value": 43.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 266.4,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 70.3,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.259,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4426.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 329.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 578.1,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 96,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 21.606,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4628.3,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3251.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3732.9,
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
            "value": -102.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 2974.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 33.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.873,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1145.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": 9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2935.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.7,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 6.108,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1637.2,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 467.1,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3402.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.6,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 61.22,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1633.5,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 6614.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9945.6,
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
          "id": "346d4662b985d7a4a128252ba7c83d468ed010a0",
          "message": "fix(scenarios): probe gate predicts super-linear streaming cross-join peaks (#10)\n\nThe gate from the previous fix extrapolated a rung's peak linearly in\nbatch size from the last measured rung. Field falsification on the CI\n10sc x 100K cell: b=1 measured ~1.3 GB on the 4-core runner, so a linear\nprediction put b=4 within the 7.7 GB budget -- but the actual b=4 demand\nwas ~11.5 GB (8.6x the b=1 rung, 2.2x ABOVE linear; the Polars #20786\ncross-join inflation is super-linear in batch at high policy counts) and\nthe probe killed the runner again. Locally-measured 1K-10K ratios\n(3.0-3.7x, sub-linear) do not extrapolate to 100K: the scaling law\nitself changes with scale.\n\nMultiply the gate's linear prediction by streaming_batch_inflation\n(3.0, a named SizingDefaults constant chosen above the worst observed\n2.2x excess). Checked against every measured cell: 1K/10K cells keep\ntheir current batch choices; the 100K killer rung is now gated; the one\nbehavioral downgrade is 1000sc x 1K picking b=16 over b=64 (~8% slower)\n-- reliability over peak throughput. Over-predicting costs at most a\nsmaller batch; under-predicting costs the process.\n\nNew test pins the factor: a budget that a bare-linear gate would pass\n(100 MB peak, 1 GB budget -> linear 520 MB) must still skip the b=4\nprobe (inflated 1560 MB).",
          "timestamp": "2026-07-08T09:21:41+12:00",
          "tree_id": "7aeae535b10b4a974f6d35471b9d4bb10dcb7a20",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/346d4662b985d7a4a128252ba7c83d468ed010a0"
        },
        "date": 1783459781436,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "VA Model (GMDB/GMAB)/8-points",
            "value": 0.141,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-throughput",
            "value": 56.7,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-memory",
            "value": 51.3,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-data-mb",
            "value": 0.2,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-rss",
            "value": 212.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cores",
            "value": 2,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/8-cpu-avg",
            "value": 12.3,
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
            "value": 43.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-data-mb",
            "value": 38,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-rss",
            "value": 254,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/1K-cpu-avg",
            "value": 71.9,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-points",
            "value": 2.195,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-throughput",
            "value": 4555.8,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-memory",
            "value": 328.5,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-data-mb",
            "value": 252.8,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-rss",
            "value": 566.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/10K-cpu-avg",
            "value": 96.1,
            "unit": "%"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-points",
            "value": 20.769,
            "unit": "seconds"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-throughput",
            "value": 4814.9,
            "unit": "points/sec"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-memory",
            "value": 3244,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-data-mb",
            "value": 2499.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-rss",
            "value": 3715.9,
            "unit": "MB"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA Model (GMDB/GMAB)/100K-cpu-avg",
            "value": 99.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/8-points",
            "value": 0.099,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/8-throughput",
            "value": 80.8,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/8-memory",
            "value": -0.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-data-mb",
            "value": 0.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-rss",
            "value": 3073.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/8-cores",
            "value": 3,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/8-cpu-avg",
            "value": 35,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/1K-points",
            "value": 0.866,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/1K-throughput",
            "value": 1154.7,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/1K-memory",
            "value": -176.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-data-mb",
            "value": 114,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-rss",
            "value": 2744.7,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/1K-cpu-avg",
            "value": 88.4,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/10K-points",
            "value": 5.87,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/10K-throughput",
            "value": 1703.6,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/10K-memory",
            "value": 538.8,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-data-mb",
            "value": 771.2,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-rss",
            "value": 3283.5,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cores",
            "value": 4,
            "unit": "cores"
          },
          {
            "name": "VA + Scenarios (3x)/10K-cpu-avg",
            "value": 98.5,
            "unit": "%"
          },
          {
            "name": "VA + Scenarios (3x)/100K-points",
            "value": 58.537,
            "unit": "seconds"
          },
          {
            "name": "VA + Scenarios (3x)/100K-throughput",
            "value": 1708.3,
            "unit": "points/sec"
          },
          {
            "name": "VA + Scenarios (3x)/100K-memory",
            "value": 5921.9,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-data-mb",
            "value": 7629.6,
            "unit": "MB"
          },
          {
            "name": "VA + Scenarios (3x)/100K-rss",
            "value": 9071.3,
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
      }
    ]
  }
}