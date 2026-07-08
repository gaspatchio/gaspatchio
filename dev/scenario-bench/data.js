window.BENCHMARK_DATA = {
  "lastUpdate": 1783502080439,
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
        "date": 1783466083389,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.158,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 188.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3167,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 29.37,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 943.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3404.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 446.245,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 1159.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2240.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 20.961,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1297.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4770.8,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 205.322,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6656.6,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4870.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783470258766,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.164,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 192.1,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3160.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 29.538,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 949.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3385.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 449.667,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 1152.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2223.9,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.173,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1365.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4723,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 207.137,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6652.4,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4827.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783475324793,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.147,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 186.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3177.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 29.418,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 947.6,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3399.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 451.733,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 1145,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2213.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 20.893,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1319.1,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4786.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 205.563,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 6822.9,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4864.7,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783486958401,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.268,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 175.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3059.6,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.56,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 757.8,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3272.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 467.216,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 865.4,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2140.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.611,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1191,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4627.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 212.837,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5837.3,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4698.4,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-batch",
            "value": 1,
            "unit": "count"
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
        "date": 1783502079341,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "scen-scaling/1Kpts-0010sc-wall",
            "value": 3.261,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-rss",
            "value": 172.5,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-throughput",
            "value": 3066.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-wall",
            "value": 30.55,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-rss",
            "value": 764.7,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-throughput",
            "value": 3273.3,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-0100sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-wall",
            "value": 465.949,
            "unit": "seconds"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-rss",
            "value": 874.3,
            "unit": "MB"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-throughput",
            "value": 2146.2,
            "unit": "scenario-points/sec"
          },
          {
            "name": "scen-scaling/1Kpts-1000sc-batch",
            "value": 16,
            "unit": "count"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-wall",
            "value": 21.732,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-rss",
            "value": 1146.8,
            "unit": "MB"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-throughput",
            "value": 4601.5,
            "unit": "scenario-points/sec"
          },
          {
            "name": "port-scaling/10Kpts-0010sc-batch",
            "value": 4,
            "unit": "count"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-wall",
            "value": 213.623,
            "unit": "seconds"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-rss",
            "value": 5836,
            "unit": "MB"
          },
          {
            "name": "port-scaling/100Kpts-0010sc-throughput",
            "value": 4681.1,
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