window.BENCHMARK_DATA = {
  "lastUpdate": 1783392790427,
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
      }
    ]
  }
}