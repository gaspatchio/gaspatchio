window.BENCHMARK_DATA = {
  "lastUpdate": 1783393864739,
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
      }
    ]
  }
}