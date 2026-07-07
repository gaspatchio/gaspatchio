window.BENCHMARK_DATA = {
  "lastUpdate": 1783396077764,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Rust Benchmarks (Windows)": [
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
        "date": 1783396075213,
        "tool": "cargo",
        "benches": [
          {
            "name": "assumption_table_lookup_1k/mortality_assumption_table_lookup_1k",
            "value": 258942500,
            "range": "± 3341485",
            "unit": "ns/iter"
          },
          {
            "name": "assumption_table_vector_lookup_1k/mortality_assumption_table_vector_lookup_1k",
            "value": 242946000,
            "range": "± 3192679",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/hash_lookup_1k",
            "value": 243744600,
            "range": "± 1568829",
            "unit": "ns/iter"
          },
          {
            "name": "hash_vs_array_1k/array_lookup_1k",
            "value": 6279393,
            "range": "± 59880",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/hash_vector_lookup_1k",
            "value": 247332500,
            "range": "± 2038905",
            "unit": "ns/iter"
          },
          {
            "name": "vector_hash_vs_array_1k/array_vector_lookup_1k",
            "value": 6263737,
            "range": "± 70754",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/hash/1000",
            "value": 243981400,
            "range": "± 1946786",
            "unit": "ns/iter"
          },
          {
            "name": "lookup_scaling/array/1000",
            "value": 6313218,
            "range": "± 89919",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_1000/1000",
            "value": 985528,
            "range": "± 34466",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_1000/1000",
            "value": 84819683,
            "range": "± 388574",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/array_10000/10000",
            "value": 9602010,
            "range": "± 109455",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/mortality_select/hash_10000/10000",
            "value": 850413500,
            "range": "± 2600341",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_1000/1000",
            "value": 431652,
            "range": "± 1358",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_1000/1000",
            "value": 45378286,
            "range": "± 213392",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/array_10000/10000",
            "value": 7254912,
            "range": "± 70333",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/lapse_rates/hash_10000/10000",
            "value": 458736250,
            "range": "± 1514141",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_1000/1000",
            "value": 432101,
            "range": "± 1416",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_1000/1000",
            "value": 45836814,
            "range": "± 145710",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/array_10000/10000",
            "value": 7255250,
            "range": "± 60110",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/surrender_charges/hash_10000/10000",
            "value": 463797750,
            "range": "± 2185239",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_1000/1000",
            "value": 532060,
            "range": "± 1631",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_1000/1000",
            "value": 56353950,
            "range": "± 445896",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/array_10000/10000",
            "value": 8971929,
            "range": "± 60176",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/risk_free_rates/hash_10000/10000",
            "value": 565221850,
            "range": "± 1911481",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_1000/1000",
            "value": 2426103,
            "range": "± 15654",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_1000/1000",
            "value": 228722150,
            "range": "± 976523",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/array_10000/10000",
            "value": 33627436,
            "range": "± 344523",
            "unit": "ns/iter"
          },
          {
            "name": "realistic_vector/combined_model/hash_10000/10000",
            "value": 2276841200,
            "range": "± 16980165",
            "unit": "ns/iter"
          }
        ]
      }
    ]
  }
}