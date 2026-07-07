window.BENCHMARK_DATA = {
  "lastUpdate": 1783393552740,
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
      }
    ]
  }
}