window.BENCHMARK_DATA = {
  "lastUpdate": 1783393874851,
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
      }
    ]
  }
}