# Third-party reference oracles (test-only)

These sources provide numeric oracles used by the curve tests. All are permissive-licensed;
none are bundled in the shipped wheel. Values are facts (published numeric outputs); the test
code is original to this project.

| Source | Licence | Copyright | URL | Used for |
|--------|---------|-----------|-----|----------|
| lifelib | MIT | (c) 2022 lifelib Developers | https://lifelib.io/libraries/economic_curves/smith_wilson.html | Smith-Wilson worked-example spot values r(3)/r(10)/r(20) (test_smith_wilson.py) |
| Federal Reserve GSW | US Government work (public domain) | — | https://www.federalreserve.gov/data/nominal-yield-curve.htm | Nelson-Siegel-Svensson published params + SVENYxx yields (test_svensson.py) |

The lifelib Smith-Wilson example values are reproduced as numeric test fixtures under fair use of
factual data; lifelib is MIT-licensed. No lifelib source code is copied.
