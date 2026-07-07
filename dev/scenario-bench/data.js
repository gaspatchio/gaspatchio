window.BENCHMARK_DATA = {
  "lastUpdate": 1783464818606,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Scenario Benchmarks": [
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
        "date": 1783464817676,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.197,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 184.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3127.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 29.624,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 957.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3375.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 451.41,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 1146.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2215.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.314,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1336.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4691.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 209.045,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6545.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4783.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
          }
        ]
      }
    ]
  }
}