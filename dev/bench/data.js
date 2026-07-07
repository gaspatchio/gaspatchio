window.BENCHMARK_DATA = {
  "lastUpdate": 1783460246379,
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
      }
    ]
  }
}