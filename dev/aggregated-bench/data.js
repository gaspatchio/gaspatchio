window.BENCHMARK_DATA = {
  "lastUpdate": 1783392597135,
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
      }
    ]
  }
}