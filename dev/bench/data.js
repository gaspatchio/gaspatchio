window.BENCHMARK_DATA = {
  "lastUpdate": 1786264584162,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Rust Benchmarks": [
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
        "date": 1783393075148,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 168369180,
            "range": "± 1624977",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 168234165,
            "range": "± 1219232",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 166466788,
            "range": "± 264054",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4329230,
            "range": "± 18924",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 166205999,
            "range": "± 272979",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4332282,
            "range": "± 20653",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 166504311,
            "range": "± 2464166",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4304926,
            "range": "± 32595",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 591557,
            "range": "± 656",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54336662,
            "range": "± 61837",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10073212,
            "range": "± 26488",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 544407933,
            "range": "± 3668675",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 404458,
            "range": "± 470",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31406689,
            "range": "± 40091",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4095521,
            "range": "± 6964",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 314267007,
            "range": "± 2295178",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 404976,
            "range": "± 1980",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31376317,
            "range": "± 55679",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4096024,
            "range": "± 7349",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 314586004,
            "range": "± 3744483",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 525378,
            "range": "± 610",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40196757,
            "range": "± 39694",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5379406,
            "range": "± 79606",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 401221643,
            "range": "± 241210",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1938394,
            "range": "± 68929",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 156543694,
            "range": "± 205184",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26757599,
            "range": "± 441886",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1574411279,
            "range": "± 7498705",
            "unit": "ns/iter"
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
        "date": 1783393863888,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 130418770,
            "range": "± 898392",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 130038189,
            "range": "± 471957",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 141455305,
            "range": "± 889652",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3359427,
            "range": "± 26679",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 141445610,
            "range": "± 646172",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3338117,
            "range": "± 30521",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 141545644,
            "range": "± 329241",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3345992,
            "range": "± 103962",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 457476,
            "range": "± 534",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 41998491,
            "range": "± 24161",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 8654511,
            "range": "± 94358",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 420976561,
            "range": "± 262433",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 313930,
            "range": "± 373",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 23993040,
            "range": "± 46258",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3177937,
            "range": "± 14253",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 240015190,
            "range": "± 1913358",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 313948,
            "range": "± 800",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 24074200,
            "range": "± 40153",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3203721,
            "range": "± 17211",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 240147216,
            "range": "± 1289415",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 406849,
            "range": "± 1160",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 31132681,
            "range": "± 23564",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4201373,
            "range": "± 8701",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 311725257,
            "range": "± 108961",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1495016,
            "range": "± 3224",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 122519375,
            "range": "± 80711",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 21527355,
            "range": "± 76360",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1235736808,
            "range": "± 1604052",
            "unit": "ns/iter"
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
        "date": 1783395475569,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159476298,
            "range": "± 1044402",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159493974,
            "range": "± 3008811",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 155265418,
            "range": "± 453641",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4194369,
            "range": "± 41249",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 155374773,
            "range": "± 309856",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4210088,
            "range": "± 84843",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 158000642,
            "range": "± 232533",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4230714,
            "range": "± 45990",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 556123,
            "range": "± 1040",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 53533976,
            "range": "± 46952",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9682375,
            "range": "± 98903",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 535340618,
            "range": "± 3155846",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 413320,
            "range": "± 954",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29685272,
            "range": "± 57184",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4416416,
            "range": "± 32812",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 297281505,
            "range": "± 2262545",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 417946,
            "range": "± 2156",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29932760,
            "range": "± 135389",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4475622,
            "range": "± 41608",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 299756199,
            "range": "± 1593319",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 496616,
            "range": "± 762",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39368223,
            "range": "± 144404",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5296606,
            "range": "± 42548",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 393751923,
            "range": "± 366029",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1996205,
            "range": "± 8982",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 150272730,
            "range": "± 261702",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27465901,
            "range": "± 119590",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1512917398,
            "range": "± 3407095",
            "unit": "ns/iter"
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
        "date": 1783419307757,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 158272800,
            "range": "± 2053076",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 158245675,
            "range": "± 540012",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 155193454,
            "range": "± 480329",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4259695,
            "range": "± 28601",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 156550555,
            "range": "± 368750",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4273396,
            "range": "± 43589",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 157635303,
            "range": "± 401026",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4270996,
            "range": "± 38606",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 557082,
            "range": "± 646",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52390847,
            "range": "± 77507",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 8980151,
            "range": "± 63004",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 524614071,
            "range": "± 2355400",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 432302,
            "range": "± 2512",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29518372,
            "range": "± 49388",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4476502,
            "range": "± 27045",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 300703667,
            "range": "± 231678",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 435645,
            "range": "± 2032",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29776036,
            "range": "± 38641",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4496588,
            "range": "± 46946",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 304474091,
            "range": "± 673902",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 500799,
            "range": "± 3486",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38991425,
            "range": "± 19807",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5348400,
            "range": "± 26419",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 389054467,
            "range": "± 668718",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1917293,
            "range": "± 4555",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 149622917,
            "range": "± 126984",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27627404,
            "range": "± 92593",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1511184307,
            "range": "± 2813952",
            "unit": "ns/iter"
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
        "date": 1783460245845,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 166502991,
            "range": "± 438214",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 166580631,
            "range": "± 1966832",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 165070522,
            "range": "± 165420",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4293656,
            "range": "± 9201",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 169396607,
            "range": "± 1521760",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4294152,
            "range": "± 14477",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 165116271,
            "range": "± 1599148",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4303858,
            "range": "± 31609",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 593303,
            "range": "± 3671",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54046201,
            "range": "± 87865",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9002629,
            "range": "± 83914",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 542812256,
            "range": "± 2651658",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 405285,
            "range": "± 1554",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30914445,
            "range": "± 48479",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4053946,
            "range": "± 20317",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 310815352,
            "range": "± 4186615",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 404993,
            "range": "± 657",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31209325,
            "range": "± 28409",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4125612,
            "range": "± 43971",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 310715997,
            "range": "± 3651434",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 526792,
            "range": "± 2318",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40082236,
            "range": "± 24956",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5304001,
            "range": "± 12899",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 401136273,
            "range": "± 721397",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1937775,
            "range": "± 18125",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 157584109,
            "range": "± 1998670",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26807267,
            "range": "± 66370",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1589979024,
            "range": "± 5685847",
            "unit": "ns/iter"
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
        "date": 1783464626260,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159835263,
            "range": "± 559576",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159974932,
            "range": "± 1918459",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 155705905,
            "range": "± 345964",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4314447,
            "range": "± 50288",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 155638166,
            "range": "± 857179",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4258154,
            "range": "± 42901",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 155389948,
            "range": "± 1137752",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4384361,
            "range": "± 49408",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 557787,
            "range": "± 3333",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52382949,
            "range": "± 344699",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 11343679,
            "range": "± 196197",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 525482716,
            "range": "± 2794293",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 417518,
            "range": "± 7065",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29865106,
            "range": "± 56924",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4874995,
            "range": "± 82167",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 299400428,
            "range": "± 589787",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 416249,
            "range": "± 2813",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29937251,
            "range": "± 50688",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4819770,
            "range": "± 61311",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 312926582,
            "range": "± 2372393",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 501300,
            "range": "± 1379",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39099721,
            "range": "± 69670",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 6173700,
            "range": "± 131815",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 390497590,
            "range": "± 1076471",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1917242,
            "range": "± 31649",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 151675892,
            "range": "± 484854",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 31146268,
            "range": "± 993921",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1523186656,
            "range": "± 6116811",
            "unit": "ns/iter"
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
        "date": 1783465916992,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 156066388,
            "range": "± 1444849",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 156044884,
            "range": "± 1802947",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 156023844,
            "range": "± 1348335",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4167020,
            "range": "± 31166",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 156067935,
            "range": "± 372686",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4226671,
            "range": "± 49414",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 156336283,
            "range": "± 328720",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4160402,
            "range": "± 31855",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 553481,
            "range": "± 1999",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52070313,
            "range": "± 49899",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9524679,
            "range": "± 62834",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 522360543,
            "range": "± 4543731",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 416716,
            "range": "± 1847",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29543375,
            "range": "± 42888",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4536319,
            "range": "± 95619",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 299109107,
            "range": "± 4643906",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 409459,
            "range": "± 946",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29750546,
            "range": "± 27448",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4369563,
            "range": "± 41678",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 301266140,
            "range": "± 2563945",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 496442,
            "range": "± 1312",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38809493,
            "range": "± 27255",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5246371,
            "range": "± 24525",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 388111857,
            "range": "± 236668",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1876258,
            "range": "± 7539",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 150276626,
            "range": "± 180316",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27918593,
            "range": "± 175040",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1513551406,
            "range": "± 3735434",
            "unit": "ns/iter"
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
        "date": 1783469946418,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 130559623,
            "range": "± 1174969",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 130296248,
            "range": "± 482030",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 127727994,
            "range": "± 2358694",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3326971,
            "range": "± 12674",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 127452023,
            "range": "± 155705",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3324799,
            "range": "± 7265",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 127020068,
            "range": "± 395558",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3335096,
            "range": "± 9328",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 457391,
            "range": "± 5006",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 45579699,
            "range": "± 125960",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 7844585,
            "range": "± 86662",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 456767388,
            "range": "± 3224180",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 312390,
            "range": "± 225",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 25522728,
            "range": "± 22267",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3176371,
            "range": "± 16964",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 254774305,
            "range": "± 539241",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 312684,
            "range": "± 1635",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 25431478,
            "range": "± 62494",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3213395,
            "range": "± 18313",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 255009985,
            "range": "± 2538284",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 405570,
            "range": "± 573",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 32859627,
            "range": "± 86541",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4167975,
            "range": "± 23902",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 329090601,
            "range": "± 715539",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1489167,
            "range": "± 1395",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 120756813,
            "range": "± 872010",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 21204444,
            "range": "± 186989",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1218936578,
            "range": "± 5184256",
            "unit": "ns/iter"
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
        "date": 1783475174152,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 157977615,
            "range": "± 640224",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 157474323,
            "range": "± 3789254",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 158087769,
            "range": "± 769824",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4335103,
            "range": "± 29865",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 155199250,
            "range": "± 1322627",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4370349,
            "range": "± 31984",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 158103382,
            "range": "± 675545",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4361174,
            "range": "± 38471",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 551827,
            "range": "± 1325",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51790897,
            "range": "± 196057",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9588265,
            "range": "± 84503",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518110807,
            "range": "± 3146168",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 424085,
            "range": "± 1161",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29079096,
            "range": "± 51279",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4459873,
            "range": "± 295206",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 291469890,
            "range": "± 196723",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 421232,
            "range": "± 1887",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29406668,
            "range": "± 56955",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4506553,
            "range": "± 66499",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 295500559,
            "range": "± 2112097",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 495278,
            "range": "± 7996",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38578935,
            "range": "± 63795",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5244132,
            "range": "± 72642",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 386397890,
            "range": "± 9180594",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1891565,
            "range": "± 13622",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 148356677,
            "range": "± 112469",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27779073,
            "range": "± 872071",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1498247620,
            "range": "± 14888030",
            "unit": "ns/iter"
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
        "date": 1783486776142,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 155706974,
            "range": "± 813213",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 155654986,
            "range": "± 2564589",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 157590486,
            "range": "± 1643896",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4425174,
            "range": "± 35117",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 157751312,
            "range": "± 1373261",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4467935,
            "range": "± 48178",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 160151896,
            "range": "± 147124",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4371187,
            "range": "± 116312",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 554563,
            "range": "± 1539",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51913555,
            "range": "± 197681",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10718659,
            "range": "± 169722",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 519366979,
            "range": "± 2808953",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 450205,
            "range": "± 2636",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29588269,
            "range": "± 54981",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4591758,
            "range": "± 74040",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 295629360,
            "range": "± 3500240",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 425467,
            "range": "± 2303",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29730612,
            "range": "± 150924",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4429972,
            "range": "± 46356",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 297190223,
            "range": "± 3201613",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 495296,
            "range": "± 1163",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38810526,
            "range": "± 44106",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5259607,
            "range": "± 45273",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 387853130,
            "range": "± 752492",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1916059,
            "range": "± 17443",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 149377374,
            "range": "± 94819",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26410008,
            "range": "± 190627",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1509157296,
            "range": "± 3450997",
            "unit": "ns/iter"
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
        "date": 1783501896911,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 162444056,
            "range": "± 1583863",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 162645595,
            "range": "± 2104360",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 155830124,
            "range": "± 275915",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4293551,
            "range": "± 159945",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 155743127,
            "range": "± 1595190",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4297716,
            "range": "± 57834",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 155838151,
            "range": "± 423892",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4264676,
            "range": "± 40229",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 553730,
            "range": "± 41954",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52114487,
            "range": "± 67288",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9835406,
            "range": "± 295653",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 521143077,
            "range": "± 2829908",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 433136,
            "range": "± 8402",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29573228,
            "range": "± 332697",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4520826,
            "range": "± 35567",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 296329526,
            "range": "± 3705202",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 420622,
            "range": "± 1506",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30095652,
            "range": "± 308325",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4489051,
            "range": "± 44644",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 298277411,
            "range": "± 5924667",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 494984,
            "range": "± 10346",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38836540,
            "range": "± 41563",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5277907,
            "range": "± 103856",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 388470216,
            "range": "± 679065",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1930509,
            "range": "± 32479",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 149436772,
            "range": "± 423098",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26816292,
            "range": "± 260833",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1503700427,
            "range": "± 7376004",
            "unit": "ns/iter"
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
        "date": 1783923168014,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 156109273,
            "range": "± 384853",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 155333719,
            "range": "± 1818060",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 165570205,
            "range": "± 309185",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3983779,
            "range": "± 22478",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 162678012,
            "range": "± 594577",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3981354,
            "range": "± 43058",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 163243261,
            "range": "± 202216",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3986294,
            "range": "± 54307",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 551401,
            "range": "± 2631",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52518104,
            "range": "± 34572",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10143606,
            "range": "± 52715",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 526918375,
            "range": "± 2656086",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 413591,
            "range": "± 1075",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29103251,
            "range": "± 42305",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4283834,
            "range": "± 42236",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 292951695,
            "range": "± 330268",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 416113,
            "range": "± 1637",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29337798,
            "range": "± 43581",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4291963,
            "range": "± 25991",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 295666182,
            "range": "± 2314458",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 492610,
            "range": "± 3387",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38946635,
            "range": "± 107365",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5217412,
            "range": "± 37281",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 389607489,
            "range": "± 2393961",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1867879,
            "range": "± 3008",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 148757951,
            "range": "± 258388",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27843491,
            "range": "± 72305",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1499339116,
            "range": "± 1297598",
            "unit": "ns/iter"
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
        "date": 1784528023873,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 157255008,
            "range": "± 2486610",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 157120583,
            "range": "± 2437224",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 155086054,
            "range": "± 513519",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4314644,
            "range": "± 28408",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 156050046,
            "range": "± 921053",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4327889,
            "range": "± 43601",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 155576198,
            "range": "± 322452",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4294530,
            "range": "± 38990",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 581304,
            "range": "± 3121",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52138370,
            "range": "± 124494",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10690989,
            "range": "± 37320",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 522051512,
            "range": "± 613134",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 454738,
            "range": "± 1012",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30667345,
            "range": "± 241865",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4998737,
            "range": "± 47967",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 296955339,
            "range": "± 404187",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 459126,
            "range": "± 1268",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29914382,
            "range": "± 32358",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4986212,
            "range": "± 24629",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 299122860,
            "range": "± 2336230",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 523740,
            "range": "± 3502",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38967209,
            "range": "± 164904",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5618488,
            "range": "± 30124",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 388220003,
            "range": "± 1137479",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 2026407,
            "range": "± 17564",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 150638660,
            "range": "± 88371",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28762336,
            "range": "± 88675",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1518983398,
            "range": "± 2523770",
            "unit": "ns/iter"
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
        "date": 1785036433541,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 172359224,
            "range": "± 2534409",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 173011851,
            "range": "± 1557197",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 173381756,
            "range": "± 2041640",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4499541,
            "range": "± 38557",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 173256098,
            "range": "± 203912",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4451541,
            "range": "± 36790",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 174902546,
            "range": "± 2048735",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4457329,
            "range": "± 17526",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 592681,
            "range": "± 3203",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54873366,
            "range": "± 1469848",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 11456136,
            "range": "± 57543",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 549327038,
            "range": "± 7869685",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 403704,
            "range": "± 7883",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 32155192,
            "range": "± 515354",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4182323,
            "range": "± 15066",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 321757556,
            "range": "± 2872419",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 404147,
            "range": "± 5517",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32193714,
            "range": "± 42397",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4178152,
            "range": "± 105253",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 324180245,
            "range": "± 316362",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 522282,
            "range": "± 818",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40577888,
            "range": "± 140754",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5423072,
            "range": "± 126877",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 404575161,
            "range": "± 333473",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1928212,
            "range": "± 3399",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 160412442,
            "range": "± 256443",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26342473,
            "range": "± 495961",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1611328110,
            "range": "± 2865115",
            "unit": "ns/iter"
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
        "date": 1785105332346,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 152139676,
            "range": "± 2477404",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 152955180,
            "range": "± 297352",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 152496939,
            "range": "± 307631",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4376187,
            "range": "± 45786",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 153333805,
            "range": "± 396688",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4368215,
            "range": "± 62179",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 152549638,
            "range": "± 141059",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4379888,
            "range": "± 67860",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 574993,
            "range": "± 1680",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51455387,
            "range": "± 92774",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10730729,
            "range": "± 141175",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 516098036,
            "range": "± 2403260",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 405742,
            "range": "± 1734",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 28984231,
            "range": "± 44538",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4617395,
            "range": "± 91427",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 290039213,
            "range": "± 2453402",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 405301,
            "range": "± 4041",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29183354,
            "range": "± 38283",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4712068,
            "range": "± 73256",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 290434548,
            "range": "± 1975889",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 525793,
            "range": "± 16925",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 36694573,
            "range": "± 113058",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 6354179,
            "range": "± 135350",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 367180092,
            "range": "± 287819",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1961886,
            "range": "± 47194",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 146508794,
            "range": "± 146368",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 31269560,
            "range": "± 309096",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1476467141,
            "range": "± 2351659",
            "unit": "ns/iter"
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
        "date": 1785133910454,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 164179103,
            "range": "± 770268",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 164121170,
            "range": "± 193349",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 162232461,
            "range": "± 308845",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4516423,
            "range": "± 26882",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 162308933,
            "range": "± 176898",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4538431,
            "range": "± 27665",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 162255098,
            "range": "± 196444",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4590575,
            "range": "± 45632",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 598917,
            "range": "± 11778",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54958102,
            "range": "± 75831",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 11248735,
            "range": "± 191451",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 551875328,
            "range": "± 2180856",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 393650,
            "range": "± 2954",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31227442,
            "range": "± 35860",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4408316,
            "range": "± 153695",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 314943526,
            "range": "± 1169180",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 398232,
            "range": "± 1397",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31253875,
            "range": "± 81996",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4589799,
            "range": "± 129748",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 316203757,
            "range": "± 559763",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 539251,
            "range": "± 25054",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40195837,
            "range": "± 131336",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 6161355,
            "range": "± 168651",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 405030248,
            "range": "± 230184",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1996353,
            "range": "± 64917",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 156094334,
            "range": "± 154938",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 32392261,
            "range": "± 563726",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1574683879,
            "range": "± 6695082",
            "unit": "ns/iter"
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
        "date": 1785283068693,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 173478554,
            "range": "± 619844",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 171262017,
            "range": "± 905130",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 174127045,
            "range": "± 154519",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4310593,
            "range": "± 32294",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 175779883,
            "range": "± 1420841",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4323607,
            "range": "± 37144",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 174364648,
            "range": "± 194872",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4304009,
            "range": "± 52624",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 591896,
            "range": "± 1055",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54205544,
            "range": "± 656147",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9982328,
            "range": "± 134791",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 541074593,
            "range": "± 4572217",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 403180,
            "range": "± 364",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 32328354,
            "range": "± 184211",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4082039,
            "range": "± 21054",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 321114736,
            "range": "± 2479112",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 403451,
            "range": "± 19832",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32083395,
            "range": "± 12684",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4052061,
            "range": "± 9386",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 321556908,
            "range": "± 179951",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 523811,
            "range": "± 381",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40150315,
            "range": "± 24209",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5332612,
            "range": "± 63782",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 401241440,
            "range": "± 352063",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1935804,
            "range": "± 2861",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 159005279,
            "range": "± 135600",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 25182891,
            "range": "± 158906",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1611269009,
            "range": "± 4278387",
            "unit": "ns/iter"
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
        "date": 1785303264776,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 161684578,
            "range": "± 3484974",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 160093341,
            "range": "± 335179",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 159450068,
            "range": "± 783451",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3994453,
            "range": "± 25711",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 159476203,
            "range": "± 200383",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3999421,
            "range": "± 45316",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 159353342,
            "range": "± 747073",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4003136,
            "range": "± 20634",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 553969,
            "range": "± 1573",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 53139977,
            "range": "± 38329",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10447450,
            "range": "± 97256",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 532437024,
            "range": "± 388885",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 412889,
            "range": "± 1379",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30925889,
            "range": "± 37653",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4254218,
            "range": "± 39192",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 304841835,
            "range": "± 2635574",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 407991,
            "range": "± 4930",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30745228,
            "range": "± 32773",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4239465,
            "range": "± 56089",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 306657969,
            "range": "± 1945838",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 494509,
            "range": "± 967",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39510113,
            "range": "± 66789",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5171619,
            "range": "± 54513",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 395349451,
            "range": "± 491999",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1889353,
            "range": "± 10354",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 151026244,
            "range": "± 140010",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27095803,
            "range": "± 219082",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1515313942,
            "range": "± 2430528",
            "unit": "ns/iter"
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
        "date": 1785411025443,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159539083,
            "range": "± 2475656",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159587297,
            "range": "± 2657104",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 164659711,
            "range": "± 2494867",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4450853,
            "range": "± 20803",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 164797802,
            "range": "± 2182120",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4440804,
            "range": "± 43115",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 164620970,
            "range": "± 412926",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4416631,
            "range": "± 21361",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 575899,
            "range": "± 2865",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51705175,
            "range": "± 46755",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9485137,
            "range": "± 22166",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518466168,
            "range": "± 2094789",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 484472,
            "range": "± 2770",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29826162,
            "range": "± 298180",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4789610,
            "range": "± 95775",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 298250877,
            "range": "± 378324",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 472504,
            "range": "± 2515",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30046035,
            "range": "± 43877",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4753701,
            "range": "± 38623",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 300355072,
            "range": "± 2828423",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 520636,
            "range": "± 766",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38437301,
            "range": "± 38317",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5344390,
            "range": "± 9725",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 385239685,
            "range": "± 351736",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 2003384,
            "range": "± 32891",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 153166294,
            "range": "± 178920",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 29224599,
            "range": "± 629083",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1538627883,
            "range": "± 2665997",
            "unit": "ns/iter"
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
        "date": 1785461509317,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 158949181,
            "range": "± 701662",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159090805,
            "range": "± 2483051",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 159396588,
            "range": "± 339923",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4321280,
            "range": "± 37480",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 160594929,
            "range": "± 1424919",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4291194,
            "range": "± 53789",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 159190318,
            "range": "± 199542",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4294484,
            "range": "± 92764",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 550475,
            "range": "± 2590",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51983143,
            "range": "± 66434",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10288427,
            "range": "± 63159",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 520401609,
            "range": "± 4008376",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 453109,
            "range": "± 1278",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29852648,
            "range": "± 29634",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4603768,
            "range": "± 25613",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 298634254,
            "range": "± 228149",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 431673,
            "range": "± 1952",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30041620,
            "range": "± 20301",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4761529,
            "range": "± 37520",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 301168508,
            "range": "± 2880186",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 493533,
            "range": "± 1315",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38235717,
            "range": "± 105347",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5297856,
            "range": "± 15972",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 382734346,
            "range": "± 3389698",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1914045,
            "range": "± 3983",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 150272543,
            "range": "± 530306",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27701953,
            "range": "± 115275",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1515455914,
            "range": "± 939805",
            "unit": "ns/iter"
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
        "date": 1785463551049,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159485960,
            "range": "± 902142",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159565836,
            "range": "± 1524494",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 161102829,
            "range": "± 825088",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4686968,
            "range": "± 91630",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 159882690,
            "range": "± 236122",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4474505,
            "range": "± 48748",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 159738495,
            "range": "± 375393",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4511152,
            "range": "± 79673",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 550811,
            "range": "± 1817",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 53383607,
            "range": "± 86007",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10487640,
            "range": "± 119280",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 532920655,
            "range": "± 837289",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 428289,
            "range": "± 2329",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30447379,
            "range": "± 982378",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 5124001,
            "range": "± 55207",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 307571155,
            "range": "± 2981588",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 427572,
            "range": "± 2861",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30959083,
            "range": "± 93079",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 5086625,
            "range": "± 128517",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 308909270,
            "range": "± 3109800",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 493555,
            "range": "± 959",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39819405,
            "range": "± 86074",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 6070621,
            "range": "± 99557",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 397024452,
            "range": "± 1487095",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1946031,
            "range": "± 26308",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 153051051,
            "range": "± 205483",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 32633988,
            "range": "± 427383",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1550355673,
            "range": "± 4285300",
            "unit": "ns/iter"
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
        "date": 1785466208039,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 171150208,
            "range": "± 550262",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 171278265,
            "range": "± 1755229",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 172467945,
            "range": "± 305515",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4287167,
            "range": "± 7711",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 172505479,
            "range": "± 1010060",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4290681,
            "range": "± 13627",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 172310428,
            "range": "± 207781",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4289456,
            "range": "± 9946",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 593146,
            "range": "± 2792",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54658821,
            "range": "± 81511",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9773129,
            "range": "± 30878",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 546879395,
            "range": "± 3964649",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 403277,
            "range": "± 642",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 32145691,
            "range": "± 23899",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4035750,
            "range": "± 14193",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 322036173,
            "range": "± 218996",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 403555,
            "range": "± 735",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32094643,
            "range": "± 30774",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4035015,
            "range": "± 3576",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 321304150,
            "range": "± 185931",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 523995,
            "range": "± 732",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40405475,
            "range": "± 35126",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5286035,
            "range": "± 9412",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 404072990,
            "range": "± 338892",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1927816,
            "range": "± 985",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 160261042,
            "range": "± 85830",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26744051,
            "range": "± 53864",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1619251250,
            "range": "± 1120447",
            "unit": "ns/iter"
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
        "date": 1785540333632,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 143406515,
            "range": "± 4442110",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 143388527,
            "range": "± 6722080",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 141974316,
            "range": "± 5921038",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3934131,
            "range": "± 127029",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 142363245,
            "range": "± 5694173",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4014908,
            "range": "± 179033",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 142395481,
            "range": "± 5101802",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4028900,
            "range": "± 185305",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 527389,
            "range": "± 31998",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 49783391,
            "range": "± 1667570",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 7242144,
            "range": "± 211211",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 474443914,
            "range": "± 11127200",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 351672,
            "range": "± 7420",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 26911169,
            "range": "± 1247081",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3474608,
            "range": "± 96548",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 283669539,
            "range": "± 12059399",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 340500,
            "range": "± 5054",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 26981253,
            "range": "± 519070",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3535909,
            "range": "± 117819",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 281105091,
            "range": "± 7263513",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 489065,
            "range": "± 15367",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 34246308,
            "range": "± 1075169",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4716791,
            "range": "± 135863",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 351921012,
            "range": "± 8623854",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1736797,
            "range": "± 78329",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 139224877,
            "range": "± 5101116",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26116971,
            "range": "± 2210236",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1393613485,
            "range": "± 28039644",
            "unit": "ns/iter"
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
        "date": 1785616077069,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 132293360,
            "range": "± 670770",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 132838969,
            "range": "± 796883",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 131829611,
            "range": "± 150679",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3329031,
            "range": "± 4023",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 131842152,
            "range": "± 187581",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3333075,
            "range": "± 5497",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 131941264,
            "range": "± 237523",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3329010,
            "range": "± 34329",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 458714,
            "range": "± 702",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 41927076,
            "range": "± 128184",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 7612690,
            "range": "± 19548",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 419959646,
            "range": "± 1103227",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 312139,
            "range": "± 349",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 24889692,
            "range": "± 24321",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3140147,
            "range": "± 8262",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 249194939,
            "range": "± 3348888",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 316588,
            "range": "± 2511",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 24864995,
            "range": "± 33450",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3148454,
            "range": "± 8275",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 249323735,
            "range": "± 187260",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 405798,
            "range": "± 579",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 31120431,
            "range": "± 18421",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4129334,
            "range": "± 9019",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 311807582,
            "range": "± 243633",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1488908,
            "range": "± 3015",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 126085670,
            "range": "± 113936",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 21209984,
            "range": "± 52009",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1273922419,
            "range": "± 2552222",
            "unit": "ns/iter"
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
        "date": 1785618109781,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 163289421,
            "range": "± 2301880",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 163228358,
            "range": "± 758734",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 159846209,
            "range": "± 1117000",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4402885,
            "range": "± 46547",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 159815949,
            "range": "± 225466",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4363947,
            "range": "± 46125",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 160262479,
            "range": "± 1047737",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4362834,
            "range": "± 46260",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 552072,
            "range": "± 8558",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54659647,
            "range": "± 108183",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 11121254,
            "range": "± 140901",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 531834646,
            "range": "± 3535749",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 431846,
            "range": "± 4709",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30581704,
            "range": "± 100827",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4976109,
            "range": "± 32317",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 304761607,
            "range": "± 4377557",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 410511,
            "range": "± 4826",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31316009,
            "range": "± 270096",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 5041415,
            "range": "± 69877",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 308378038,
            "range": "± 4231890",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 499183,
            "range": "± 5030",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39703628,
            "range": "± 73399",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5789265,
            "range": "± 76517",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 394843746,
            "range": "± 3933581",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 2038981,
            "range": "± 26306",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 152269127,
            "range": "± 359344",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28078225,
            "range": "± 380661",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1547492141,
            "range": "± 4820275",
            "unit": "ns/iter"
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
        "date": 1785620317062,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 163679851,
            "range": "± 1146062",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 160277300,
            "range": "± 1468797",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 162812436,
            "range": "± 439603",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4266295,
            "range": "± 139919",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 162519544,
            "range": "± 563554",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4278541,
            "range": "± 44708",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 163027371,
            "range": "± 1554654",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4269835,
            "range": "± 53505",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 555035,
            "range": "± 1328",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52090550,
            "range": "± 531518",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10648804,
            "range": "± 143925",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 521942291,
            "range": "± 2830832",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 463786,
            "range": "± 2425",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29962599,
            "range": "± 43882",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4824393,
            "range": "± 29627",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 299228252,
            "range": "± 5001102",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 453569,
            "range": "± 2003",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30082065,
            "range": "± 468804",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4866990,
            "range": "± 45284",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 301965051,
            "range": "± 926626",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 496828,
            "range": "± 1330",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38626956,
            "range": "± 51696",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5289717,
            "range": "± 52437",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 385972277,
            "range": "± 588591",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1973239,
            "range": "± 12505",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 154115233,
            "range": "± 1588952",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28520718,
            "range": "± 145299",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1557546174,
            "range": "± 5845152",
            "unit": "ns/iter"
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
        "date": 1785652181934,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 178835321,
            "range": "± 3183174",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 178745331,
            "range": "± 249354",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 171714782,
            "range": "± 377219",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4185491,
            "range": "± 28840",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 172033986,
            "range": "± 248202",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4257356,
            "range": "± 44509",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 171698276,
            "range": "± 358522",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4202328,
            "range": "± 43763",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 553358,
            "range": "± 3066",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 52155176,
            "range": "± 64458",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10419205,
            "range": "± 39911",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 523186116,
            "range": "± 3730755",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 439125,
            "range": "± 1289",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30129553,
            "range": "± 31391",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4578835,
            "range": "± 44786",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 300465853,
            "range": "± 1720564",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 435878,
            "range": "± 1653",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30309340,
            "range": "± 36568",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4791028,
            "range": "± 30401",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 303095247,
            "range": "± 2757804",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 500302,
            "range": "± 1479",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38620733,
            "range": "± 44535",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5074612,
            "range": "± 12336",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 386117136,
            "range": "± 333690",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1880143,
            "range": "± 3902",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 153670033,
            "range": "± 302977",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28680437,
            "range": "± 178768",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1560758978,
            "range": "± 1234567",
            "unit": "ns/iter"
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
        "date": 1785654431676,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 160018688,
            "range": "± 476049",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 161366704,
            "range": "± 1215605",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 164712365,
            "range": "± 1409336",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4256448,
            "range": "± 29196",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 162653414,
            "range": "± 338351",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4239955,
            "range": "± 70211",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 161998848,
            "range": "± 1056106",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4166993,
            "range": "± 28998",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 552009,
            "range": "± 1552",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54079385,
            "range": "± 103111",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9198368,
            "range": "± 48670",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 541889063,
            "range": "± 480235",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 423939,
            "range": "± 1493",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31324120,
            "range": "± 157366",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4760508,
            "range": "± 57707",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 313283991,
            "range": "± 478772",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 437333,
            "range": "± 1817",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31562601,
            "range": "± 71903",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4703776,
            "range": "± 38846",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 320682126,
            "range": "± 1947598",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 494241,
            "range": "± 1115",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 41232554,
            "range": "± 48218",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5195396,
            "range": "± 31985",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 411639492,
            "range": "± 266019",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1961630,
            "range": "± 9758",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 151000850,
            "range": "± 147198",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28255983,
            "range": "± 191554",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1519910724,
            "range": "± 2114372",
            "unit": "ns/iter"
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
        "date": 1785658448554,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 130802446,
            "range": "± 818767",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 130592249,
            "range": "± 1617907",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 132033978,
            "range": "± 1225814",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3339575,
            "range": "± 15749",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 132098299,
            "range": "± 1587792",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3348124,
            "range": "± 13983",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 132375858,
            "range": "± 310095",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3352130,
            "range": "± 7443",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 458998,
            "range": "± 1278",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 44036467,
            "range": "± 29509",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 7985688,
            "range": "± 36306",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 441040306,
            "range": "± 2777005",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 313008,
            "range": "± 2372",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 25686484,
            "range": "± 26657",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3156111,
            "range": "± 7555",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 257539714,
            "range": "± 299883",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 311927,
            "range": "± 1027",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 25694791,
            "range": "± 55050",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3190735,
            "range": "± 18636",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 257288044,
            "range": "± 2162263",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 403953,
            "range": "± 1194",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 32117387,
            "range": "± 56294",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4122603,
            "range": "± 20086",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 321135790,
            "range": "± 183257",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1491181,
            "range": "± 1821",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 123766600,
            "range": "± 807835",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 21388000,
            "range": "± 94971",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1248520950,
            "range": "± 2929797",
            "unit": "ns/iter"
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
        "date": 1785660288927,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 171030892,
            "range": "± 687366",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 170959675,
            "range": "± 1677927",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 172035722,
            "range": "± 200631",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4322339,
            "range": "± 28235",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 171938624,
            "range": "± 367626",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4332941,
            "range": "± 15865",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 172164804,
            "range": "± 260613",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4340893,
            "range": "± 46315",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 593355,
            "range": "± 589",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54429724,
            "range": "± 46790",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10049920,
            "range": "± 117545",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 544523583,
            "range": "± 7871727",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 404680,
            "range": "± 1842",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 32046528,
            "range": "± 165296",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4070438,
            "range": "± 36638",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 320422177,
            "range": "± 3432325",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 403995,
            "range": "± 1836",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32125974,
            "range": "± 93183",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4148226,
            "range": "± 50293",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 320520537,
            "range": "± 2489604",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 525767,
            "range": "± 1628",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40350852,
            "range": "± 40607",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5367458,
            "range": "± 39265",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 403359084,
            "range": "± 759339",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1928377,
            "range": "± 3443",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 160392407,
            "range": "± 117528",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27014900,
            "range": "± 89661",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1613541550,
            "range": "± 2466092",
            "unit": "ns/iter"
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
        "date": 1785664514231,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159524527,
            "range": "± 3513573",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159294607,
            "range": "± 289370",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 158987364,
            "range": "± 225556",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4076570,
            "range": "± 24958",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 162383130,
            "range": "± 218698",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4111114,
            "range": "± 21781",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 158925550,
            "range": "± 426479",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4079081,
            "range": "± 35742",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 548647,
            "range": "± 5447",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51787145,
            "range": "± 64971",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10169533,
            "range": "± 594501",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518539878,
            "range": "± 2318116",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 439087,
            "range": "± 1804",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29732267,
            "range": "± 46579",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4582936,
            "range": "± 42888",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 297959862,
            "range": "± 2599214",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 442048,
            "range": "± 1385",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29973542,
            "range": "± 44013",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4638515,
            "range": "± 70234",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 299976027,
            "range": "± 2687866",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 498589,
            "range": "± 1466",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38544627,
            "range": "± 73391",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5178289,
            "range": "± 52849",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 384428178,
            "range": "± 905177",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1960029,
            "range": "± 18769",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 153389306,
            "range": "± 131110",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28621180,
            "range": "± 749637",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1549698003,
            "range": "± 4745309",
            "unit": "ns/iter"
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
        "date": 1785738116365,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 126471622,
            "range": "± 4670002",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 123996956,
            "range": "± 5936031",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 120584628,
            "range": "± 127595",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 3354321,
            "range": "± 28266",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 120665988,
            "range": "± 6654565",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 3374849,
            "range": "± 33104",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 120606873,
            "range": "± 115821",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 3363401,
            "range": "± 27360",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 391504,
            "range": "± 6290",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 39372322,
            "range": "± 31533",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 5842933,
            "range": "± 9760",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 394782479,
            "range": "± 1752363",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 292450,
            "range": "± 1684",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 22331226,
            "range": "± 12755",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 2877025,
            "range": "± 2908",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 227019496,
            "range": "± 11493684",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 288975,
            "range": "± 2020",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 22311225,
            "range": "± 863895",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 2921018,
            "range": "± 38623",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 225448321,
            "range": "± 12727710",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 362104,
            "range": "± 1052",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 28504147,
            "range": "± 1666923",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 3643212,
            "range": "± 4195",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 286560172,
            "range": "± 511124",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1359001,
            "range": "± 2476",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 114620096,
            "range": "± 85524",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 19446369,
            "range": "± 768563",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1196793027,
            "range": "± 41607668",
            "unit": "ns/iter"
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
        "date": 1785906095481,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 159188627,
            "range": "± 3534550",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159352037,
            "range": "± 483299",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 160231480,
            "range": "± 684051",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4198942,
            "range": "± 31603",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 160218146,
            "range": "± 277705",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4171162,
            "range": "± 31852",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 160487081,
            "range": "± 480157",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4164404,
            "range": "± 28202",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 548801,
            "range": "± 1107",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51684566,
            "range": "± 35351",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9282196,
            "range": "± 46588",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518029932,
            "range": "± 3431913",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 402891,
            "range": "± 3817",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30064524,
            "range": "± 827238",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4267837,
            "range": "± 37611",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 297406291,
            "range": "± 2109123",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 406803,
            "range": "± 5441",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29901216,
            "range": "± 129206",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4266012,
            "range": "± 26760",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 299367251,
            "range": "± 1432620",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 492121,
            "range": "± 1467",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38276052,
            "range": "± 52962",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5160160,
            "range": "± 21999",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 383883178,
            "range": "± 285583",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1876611,
            "range": "± 5032",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 152762554,
            "range": "± 134853",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 25362692,
            "range": "± 189807",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1539997676,
            "range": "± 1643843",
            "unit": "ns/iter"
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
        "date": 1785911247387,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 167900149,
            "range": "± 1458542",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 168213359,
            "range": "± 2013377",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 167521426,
            "range": "± 1383637",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4579327,
            "range": "± 55810",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 167949030,
            "range": "± 1313418",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4555522,
            "range": "± 51827",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 170864856,
            "range": "± 1073573",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4552764,
            "range": "± 49767",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 633958,
            "range": "± 10083",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 55287035,
            "range": "± 489345",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 13403874,
            "range": "± 189774",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 561498508,
            "range": "± 3854500",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 492656,
            "range": "± 7313",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31524965,
            "range": "± 469418",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 5608987,
            "range": "± 218753",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 320521560,
            "range": "± 3523618",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 497642,
            "range": "± 4242",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 31767237,
            "range": "± 208805",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 5551170,
            "range": "± 127426",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 321512034,
            "range": "± 2842534",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 561491,
            "range": "± 6523",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40306244,
            "range": "± 288027",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 6755680,
            "range": "± 141482",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 406647277,
            "range": "± 2118421",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 2166983,
            "range": "± 18624",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 157809081,
            "range": "± 731524",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 35164047,
            "range": "± 644118",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1605354592,
            "range": "± 5055878",
            "unit": "ns/iter"
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
        "date": 1785913466485,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 160170878,
            "range": "± 3261216",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 160036602,
            "range": "± 971158",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 160575906,
            "range": "± 454816",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4265290,
            "range": "± 33954",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 160364408,
            "range": "± 417785",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4282954,
            "range": "± 29970",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 160045722,
            "range": "± 894447",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4269841,
            "range": "± 26631",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 550161,
            "range": "± 777",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51970109,
            "range": "± 116233",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 8727284,
            "range": "± 142129",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 521224650,
            "range": "± 2389449",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 422705,
            "range": "± 1854",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29938534,
            "range": "± 100659",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4465974,
            "range": "± 33781",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 299365798,
            "range": "± 403872",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 430827,
            "range": "± 1675",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30248131,
            "range": "± 41769",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4406821,
            "range": "± 29482",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 301931619,
            "range": "± 2372885",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 495414,
            "range": "± 960",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38360789,
            "range": "± 62990",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5333992,
            "range": "± 35167",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 382646458,
            "range": "± 160564",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1898794,
            "range": "± 4782",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 152245249,
            "range": "± 96258",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27357319,
            "range": "± 134654",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1533037666,
            "range": "± 1539514",
            "unit": "ns/iter"
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
        "date": 1786137859551,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 172299107,
            "range": "± 843267",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 172267725,
            "range": "± 2366593",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 172150487,
            "range": "± 377821",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4299162,
            "range": "± 225646",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 174909627,
            "range": "± 1438774",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4295928,
            "range": "± 8452",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 171678264,
            "range": "± 743937",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4292124,
            "range": "± 8399",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 593187,
            "range": "± 563",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54385411,
            "range": "± 92737",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 8955881,
            "range": "± 85073",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 544761366,
            "range": "± 311224",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 404341,
            "range": "± 578",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31993624,
            "range": "± 33408",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4070363,
            "range": "± 218669",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 320387186,
            "range": "± 3357938",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 405162,
            "range": "± 359",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32060653,
            "range": "± 62990",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4076507,
            "range": "± 128623",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 320889056,
            "range": "± 241115",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 525882,
            "range": "± 456",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40357737,
            "range": "± 115092",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5313354,
            "range": "± 189387",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 403441981,
            "range": "± 1140114",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1925310,
            "range": "± 2777",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 168037763,
            "range": "± 257864",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 28318742,
            "range": "± 67848",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1696510743,
            "range": "± 2538771",
            "unit": "ns/iter"
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
        "date": 1786144941998,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 164790810,
            "range": "± 3120764",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 164697616,
            "range": "± 1278050",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 162001263,
            "range": "± 703889",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4014589,
            "range": "± 33326",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 163640255,
            "range": "± 455027",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4008716,
            "range": "± 131326",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 161370018,
            "range": "± 340858",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4010631,
            "range": "± 14958",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 545632,
            "range": "± 2035",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51794207,
            "range": "± 94075",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10076907,
            "range": "± 112865",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518580900,
            "range": "± 445808",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 386003,
            "range": "± 701",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29703745,
            "range": "± 96009",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3990256,
            "range": "± 44058",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 297838585,
            "range": "± 2189195",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 385430,
            "range": "± 3875",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29909182,
            "range": "± 33685",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3977039,
            "range": "± 20248",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 299625352,
            "range": "± 177392",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 488012,
            "range": "± 546",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38127142,
            "range": "± 45464",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5108919,
            "range": "± 30297",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 383271337,
            "range": "± 2505502",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1811794,
            "range": "± 14821",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 150103642,
            "range": "± 151294",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26019320,
            "range": "± 182664",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1514230110,
            "range": "± 2061145",
            "unit": "ns/iter"
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
        "date": 1786147237287,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 143694998,
            "range": "± 822126",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 143722434,
            "range": "± 637765",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 142158004,
            "range": "± 437592",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4090904,
            "range": "± 28724",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 142108712,
            "range": "± 501588",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4085202,
            "range": "± 25016",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 141803467,
            "range": "± 472142",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4076009,
            "range": "± 28405",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 542735,
            "range": "± 6777",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 47045065,
            "range": "± 113042",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 7896308,
            "range": "± 40723",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 473879264,
            "range": "± 2719870",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 387408,
            "range": "± 6696",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 26629177,
            "range": "± 75499",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3711080,
            "range": "± 15721",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 267307764,
            "range": "± 612686",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 390074,
            "range": "± 4744",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 26589916,
            "range": "± 133226",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3677968,
            "range": "± 15295",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 267656563,
            "range": "± 1541438",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 502481,
            "range": "± 11332",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 34115275,
            "range": "± 101547",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 4951751,
            "range": "± 29750",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 341611247,
            "range": "± 629134",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1784036,
            "range": "± 12044",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 135896178,
            "range": "± 260117",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 21634256,
            "range": "± 234893",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1371347724,
            "range": "± 3008385",
            "unit": "ns/iter"
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
        "date": 1786149909453,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 160452116,
            "range": "± 1182493",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 160627097,
            "range": "± 3828343",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 160521957,
            "range": "± 799929",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4075279,
            "range": "± 16196",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 160352672,
            "range": "± 1198581",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4077156,
            "range": "± 21850",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 160416724,
            "range": "± 295881",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4064529,
            "range": "± 30702",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 550280,
            "range": "± 2628",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51995669,
            "range": "± 1044173",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9840961,
            "range": "± 33747",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 520728905,
            "range": "± 2778736",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 389179,
            "range": "± 708",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30357260,
            "range": "± 47356",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4181439,
            "range": "± 31985",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 299240152,
            "range": "± 619193",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 387737,
            "range": "± 640",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30070658,
            "range": "± 62833",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4161417,
            "range": "± 16726",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 301087160,
            "range": "± 2925362",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 502694,
            "range": "± 1177",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38682872,
            "range": "± 38408",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5324458,
            "range": "± 17977",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 386044629,
            "range": "± 508436",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1838364,
            "range": "± 18923",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 149559930,
            "range": "± 194753",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27324423,
            "range": "± 203099",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1509121981,
            "range": "± 2286768",
            "unit": "ns/iter"
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
        "date": 1786154048494,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 161892569,
            "range": "± 538778",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 160725439,
            "range": "± 1689373",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 165966029,
            "range": "± 3315585",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4007565,
            "range": "± 16705",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 163322661,
            "range": "± 458488",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4010968,
            "range": "± 71592",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 163474406,
            "range": "± 474369",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4006906,
            "range": "± 20168",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 577456,
            "range": "± 3117",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 51813710,
            "range": "± 58856",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10264189,
            "range": "± 27565",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 518751062,
            "range": "± 2309336",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 386171,
            "range": "± 1422",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 29773927,
            "range": "± 71947",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3925758,
            "range": "± 18550",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 298334195,
            "range": "± 2338888",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 386244,
            "range": "± 1621",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 29881675,
            "range": "± 51866",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 3908876,
            "range": "± 24386",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 308176570,
            "range": "± 1732789",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 523344,
            "range": "± 11334",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 38801231,
            "range": "± 573548",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5422082,
            "range": "± 50069",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 382876883,
            "range": "± 426500",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1874666,
            "range": "± 3531",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 149608710,
            "range": "± 175734",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26844287,
            "range": "± 102586",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1507445806,
            "range": "± 1081697",
            "unit": "ns/iter"
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
          "id": "5007e1c420fa6733b79df1fa9f0a8f1ea4137e73",
          "message": "docs(agents): skill routing table names the real skill names (#99)\n\nThe routing table listed quickstart, model-building, etc. — names that\nexist nowhere: the canonical names are gaspatchio-quickstart and\nfriends, and Claude Code invokes them plugin-prefixed as\ngaspatchio:gaspatchio-model-building. An agent following the table as\nwritten asks for skills that don't resolve. Also adds the missing\ngaspatchio-extending row and fixes the reversed extending-gaspatchio\nreference in the Extending section. Flagged in round one of the UL\nconversion (P2 loose end); made urgent by the clean-room rerun, where\nskill routing is the variable under test. copilot-instructions\nregenerated.",
          "timestamp": "2026-08-08T20:50:59+12:00",
          "tree_id": "e2d61fbc1c7559db7519e1f3c3312a2c4d15d2e6",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/5007e1c420fa6733b79df1fa9f0a8f1ea4137e73"
        },
        "date": 1786180014233,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 172134699,
            "range": "± 1133942",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 169897960,
            "range": "± 1893847",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 171139676,
            "range": "± 949815",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4331233,
            "range": "± 22941",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 171152679,
            "range": "± 1045309",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4355564,
            "range": "± 39665",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 171163360,
            "range": "± 355800",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4363572,
            "range": "± 47395",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 588274,
            "range": "± 1162",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 53903977,
            "range": "± 40170",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 11234618,
            "range": "± 93073",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 550981145,
            "range": "± 3492169",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 404687,
            "range": "± 4643",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 32266074,
            "range": "± 64129",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4331330,
            "range": "± 64462",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 323300313,
            "range": "± 969170",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 403469,
            "range": "± 1115",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32366352,
            "range": "± 28256",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4321468,
            "range": "± 36199",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 323720663,
            "range": "± 2102380",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 521436,
            "range": "± 3783",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40165193,
            "range": "± 45090",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5460572,
            "range": "± 35593",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 401095071,
            "range": "± 485283",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1921640,
            "range": "± 4463",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 158589044,
            "range": "± 1447426",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 26333156,
            "range": "± 118638",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1601466454,
            "range": "± 3702486",
            "unit": "ns/iter"
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
          "id": "01d554dcf6cf1fae68c59f80267392a737d8a1ea",
          "message": "release: v0.8.1 — the surface tells the truth (#100)\n\nVersion stamps 0.8.0 → 0.8.1 in core/Cargo.toml,\nbindings/python/Cargo.toml, and bindings/python/pyproject.toml, with\nCargo.lock and uv.lock regenerated to match, plus the CHANGELOG entry.\n\nPatch-only: #96 (gspio tutorial reaches the shipped rollforward\npatterns, gh#94), #97 (capture-slot errors name the real rule, gh#93),\n#98 (track_increments=True refuses loudly at build time, refs gh#69).\nNo numeric behaviour changes.",
          "timestamp": "2026-08-08T21:07:26+12:00",
          "tree_id": "867a41d4565773529b115ca7765815ed3656b70f",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/01d554dcf6cf1fae68c59f80267392a737d8a1ea"
        },
        "date": 1786180995426,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 162092930,
            "range": "± 683186",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 159401418,
            "range": "± 1395000",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 166556675,
            "range": "± 463059",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4048903,
            "range": "± 29972",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 163096996,
            "range": "± 795730",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4043525,
            "range": "± 20679",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 162841957,
            "range": "± 144481",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4058787,
            "range": "± 38355",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 579964,
            "range": "± 8588",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 53507192,
            "range": "± 43930",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9924222,
            "range": "± 102713",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 536123803,
            "range": "± 3029572",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 388233,
            "range": "± 628",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30567711,
            "range": "± 28959",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4165776,
            "range": "± 19199",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 306055383,
            "range": "± 632335",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 387615,
            "range": "± 676",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30906312,
            "range": "± 58948",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4112893,
            "range": "± 19202",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 308434691,
            "range": "± 2928532",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 525216,
            "range": "± 1879",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39584501,
            "range": "± 28936",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5660312,
            "range": "± 37682",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 395472935,
            "range": "± 432980",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1893811,
            "range": "± 3712",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 151426537,
            "range": "± 77410",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27326794,
            "range": "± 128782",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1522638979,
            "range": "± 13570190",
            "unit": "ns/iter"
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
          "id": "4692029197f4eb802ca161b509f78b0d34a01bfb",
          "message": "fix(accessors): gate list path on shape, not proxy type, so composed expressions convert element-wise (#105)\n\nto_monthly(), compound(), and cumulative_survival() gated their list\npath on isinstance(proxy, ColumnProxy), so a composed list-valued\nExpressionProxy fell through to the scalar path and refused to run at\ncollect (pow on list[f64], cum_prod on list). Gate on the resolved\nshape alone — the pattern PR #85 established for excel.round; both\nproxy types resolve .shape identically.\n\nServes 'Meet you where you are': a composed per-period expression is\nthe same shape the user already had, and the accessor now accepts it.\n\nFixes #86",
          "timestamp": "2026-08-09T11:18:37+12:00",
          "tree_id": "302976df27e98e9aba604bc033c6af1e96555af8",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/4692029197f4eb802ca161b509f78b0d34a01bfb"
        },
        "date": 1786231826814,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 104110779,
            "range": "± 2871669",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 104078464,
            "range": "± 1737475",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 102873729,
            "range": "± 1212942",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 2172277,
            "range": "± 21689",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 103243631,
            "range": "± 847525",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 2119046,
            "range": "± 139485",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 102933410,
            "range": "± 3292132",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 2139126,
            "range": "± 107991",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 307529,
            "range": "± 28922",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 35052910,
            "range": "± 493308",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 6127573,
            "range": "± 64228",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 349429769,
            "range": "± 11289788",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 203447,
            "range": "± 4363",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 19425242,
            "range": "± 183554",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 2043360,
            "range": "± 30697",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 196244579,
            "range": "± 7459110",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 201540,
            "range": "± 4289",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 19512790,
            "range": "± 869926",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 1995719,
            "range": "± 42523",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 199022637,
            "range": "± 3878673",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 259021,
            "range": "± 5995",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 24787570,
            "range": "± 88746",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 2930929,
            "range": "± 60188",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 248922476,
            "range": "± 1610544",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 955291,
            "range": "± 20043",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 100033641,
            "range": "± 445439",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 15926124,
            "range": "± 618683",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1038276046,
            "range": "± 16941221",
            "unit": "ns/iter"
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
          "id": "0000b0b3908078ec95e5058a98bd63a2e363ad2f",
          "message": "fix(column): resolve bare-expression shapes in the pow dispatch, so scalar ** lookup(list key) works (#106)\n\nThe pow shim's operand detection only recognised proxy operands, so a\nbare pl.Expr exponent (e.g. Table.lookup over a list key) was treated\nas scalar and handed to raw polars pow, which has no list support.\nResolve a bare expression's shape from the schema the same way\nExpressionProxy does (_shape_from_expr_dtype), extracted into a\n_pow_arg_is_list helper.\n\nFlips the operator x shape matrix xfail cell\n(list_x_scalar/pow/proxy_first) to a passing assertion, as gh#89\nspecified.\n\nFixes #89",
          "timestamp": "2026-08-09T19:49:59+12:00",
          "tree_id": "c760f7133b415088c889a366834ffc6b0da25704",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0000b0b3908078ec95e5058a98bd63a2e363ad2f"
        },
        "date": 1786262735909,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 164847041,
            "range": "± 1427326",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 164452006,
            "range": "± 1386285",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 164580301,
            "range": "± 765084",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4513363,
            "range": "± 40959",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 165351664,
            "range": "± 847270",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4475102,
            "range": "± 34021",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 164699558,
            "range": "± 1006899",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4503160,
            "range": "± 43405",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 587464,
            "range": "± 11758",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54593971,
            "range": "± 172868",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9178873,
            "range": "± 220184",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 549861585,
            "range": "± 3123820",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 424054,
            "range": "± 10895",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 30644756,
            "range": "± 144567",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 3988861,
            "range": "± 38784",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 310633951,
            "range": "± 1802017",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 427678,
            "range": "± 3164",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 30721683,
            "range": "± 221519",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4044355,
            "range": "± 47054",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 311680605,
            "range": "± 866826",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 572683,
            "range": "± 3529",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 39481329,
            "range": "± 134970",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5453789,
            "range": "± 61491",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 397484313,
            "range": "± 1495264",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1903270,
            "range": "± 47691",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 153691640,
            "range": "± 1559379",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 29078842,
            "range": "± 423077",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1554788330,
            "range": "± 4532449",
            "unit": "ns/iter"
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
          "id": "0c0884e2385c1f4924f10f9d668997c56239d7d6",
          "message": "docs(skills): formula_pattern cannot signal a mixed binding — teach the distribution query (#107)\n\n* docs(skills): formula_pattern is one row's formula — teach the distribution query, not trust in the column\n\nThe conversion reference claimed formula_pattern 'reports the dominant\npattern, not the exception'; on merged mixed bindings it reports one\nrow's formula — in the observed cases the first row's, which is\nprecisely the exception (upstream: gaspatchio/xl-marinade#12, the\nschema stores a single formula id per binding). Replace the claim with\nthe defensive truth and the Counter-over-formula_r1c1 idiom the\nround-three clean-room run used to catch it.\n\nRefs #103\n\n* docs(skills): make the distribution query runnable from the binding row\n\nThe worked example bound sheet/col/first_row/last_row without saying where\nthey come from, and agent_cells_light stores col as a 1-based number — a\nreader deriving the letter from the binding address gets zero rows with no\nerror. Parse the binding's own A1 range instead; snippet executed against a\nreal IR (capital-regimes erm-153 extract) before committing.\n\nAddresses Greptile review on #107.",
          "timestamp": "2026-08-09T20:20:55+12:00",
          "tree_id": "a5beb9e7f0c8f36d9952b5b146aa1a589e51d62b",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0c0884e2385c1f4924f10f9d668997c56239d7d6"
        },
        "date": 1786264583155,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 172092223,
            "range": "± 577709",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 171676008,
            "range": "± 169221",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 173069154,
            "range": "± 1054179",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 4359913,
            "range": "± 41058",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 172001372,
            "range": "± 239931",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 4350639,
            "range": "± 158349",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 172543419,
            "range": "± 178274",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 4349278,
            "range": "± 41192",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 594134,
            "range": "± 11042",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 54578709,
            "range": "± 937272",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 10134871,
            "range": "± 58888",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 546078495,
            "range": "± 4059753",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 404288,
            "range": "± 3238",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 31902532,
            "range": "± 299483",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 4228605,
            "range": "± 35245",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 318201444,
            "range": "± 4014824",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 406293,
            "range": "± 2150",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 32165183,
            "range": "± 21967",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 4173563,
            "range": "± 26087",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 318786607,
            "range": "± 2861596",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 521306,
            "range": "± 1198",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 40216649,
            "range": "± 48102",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 5364472,
            "range": "± 14916",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 402206391,
            "range": "± 573068",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 1997136,
            "range": "± 5764",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 160079998,
            "range": "± 126988",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 27088372,
            "range": "± 691059",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 1613531848,
            "range": "± 4471910",
            "unit": "ns/iter"
          }
        ]
      }
    ]
  }
}