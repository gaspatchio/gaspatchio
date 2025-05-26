# Current - Main

### 1K

vector_lookups_parquet_keys_1k/mortality_lookup_parquet_keys_1k
                        time:   [100.79 ms 101.62 ms 102.51 ms]
                        change: [-17.517% -16.453% -15.423%] (p = 0.00 < 0.05)
                        Performance has improved.

vector_lookups_parquet_keys_1k/mortality_lookup_parquet_keys_1k
                        time:   [120.50 ms 121.64 ms 122.84 ms]
                        change: [+20.552% +21.930% +23.440%] (p = 0.00 < 0.05)
                        Performance has regressed.
vector_lookups_parquet_keys_1k/mortality_lookup_parquet_keys_1k
                        time:   [99.256 ms 99.767 ms 100.30 ms]
                        change: [-2.7764% -1.8261% -0.8407%] (p = 0.00 < 0.05)
                        Change within noise threshold.

### 100K


vector_lookups_parquet_keys_100k/mortality_lookup_parquet_keys_100k
                        time:   [10.152 s 10.168 s 10.182 s]
Found 8 outliers among 100 measurements (8.00%)
  5 (5.00%) low mild
  3 (3.00%) high mild
vector_lookups_parquet_keys_100k/mortality_lookup_parquet_keys_100k
                        time:   [9.9888 s 10.004 s 10.020 s]
                        change: [-1.8135% -1.6093% -1.3899%] (p = 0.00 < 0.05)
                        Performance has improved.
vector_lookups_parquet_keys_100k/mortality_lookup_parquet_keys_100k
                        time:   [10.058 s 10.075 s 10.092 s]
                        change: [+0.4773% +0.7094% +0.9480%] (p = 0.00 < 0.05)
                        Change within noise threshold.
Found 3 outliers among 100 measurements (3.00%)



# Propsosed - Develop 

### 1K
vector_lookups_parquet_keys_1k/mortality_lookup_parquet_keys_1k
                        time:   [108.53 ms 110.08 ms 111.77 ms]
vector_lookups_parquet_keys_1k/mortality_lookup_parquet_keys_1k
                        time:   [99.546 ms 100.14 ms 100.84 ms]
                        change: [-10.522% -9.0310% -7.6089%] (p = 0.00 < 0.05)
                        Performance has improved.                    

### 100K
vector_lookups_parquet_keys_100k/mortality_lookup_parquet_keys_100k
                        time:   [11.303 s 11.370 s 11.431 s]

vector_lookups_parquet_keys_100k/mortality_lookup_parquet_keys_100k
                        time:   [10.227 s 10.240 s 10.252 s]
                        change: [-10.423% -9.9430% -9.3908%] (p = 0.00 < 0.05)
                        Performance has improved.                        