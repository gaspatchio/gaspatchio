window.BENCHMARK_DATA = {
  "lastUpdate": 1788172627321,
  "repoUrl": "https://github.com/gaspatchio/gaspatchio",
  "entries": {
    "Scenario Batch Search": [
      {
        "commit": {
          "author": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "committer": {
            "name": "Matt Wright",
            "username": "mrmattwright",
            "email": "matt@opioinc.com"
          },
          "id": "ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4",
          "message": "release: v0.5.3",
          "timestamp": "2026-07-08T00:06:26Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/ed0903dced967f4e847e6d58e3e6c5cdaa3a58f4"
        },
        "date": 1783469296709,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 29.864,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 950,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 454.288,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 175.8,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 217.702,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 633.8,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 210.755,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 5739.2,
            "unit": "MB"
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
        "date": 1783927809038,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 30.745,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 765.1,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 470.116,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 472.9,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 223.347,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 870.6,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 216.718,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4913.1,
            "unit": "MB"
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
        "date": 1784532728454,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 30.847,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 783.3,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 468.196,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 498.6,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 224.584,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 804.4,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 217.68,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4825,
            "unit": "MB"
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
        "date": 1785138496733,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 30.437,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 790.8,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 459.551,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 490.5,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 213.597,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 973.4,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 206.024,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4644,
            "unit": "MB"
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
        "date": 1785743246849,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 32.581,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 789.8,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 485.684,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 475.4,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 235.505,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 785.4,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 228.465,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4757.9,
            "unit": "MB"
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
          "id": "0c0884e2385c1f4924f10f9d668997c56239d7d6",
          "message": "docs(skills): formula_pattern cannot signal a mixed binding — teach the distribution query (#107)\n\n* docs(skills): formula_pattern is one row's formula — teach the distribution query, not trust in the column\n\nThe conversion reference claimed formula_pattern 'reports the dominant\npattern, not the exception'; on merged mixed bindings it reports one\nrow's formula — in the observed cases the first row's, which is\nprecisely the exception (upstream: gaspatchio/xl-marinade#12, the\nschema stores a single formula id per binding). Replace the claim with\nthe defensive truth and the Counter-over-formula_r1c1 idiom the\nround-three clean-room run used to catch it.\n\nRefs #103\n\n* docs(skills): make the distribution query runnable from the binding row\n\nThe worked example bound sheet/col/first_row/last_row without saying where\nthey come from, and agent_cells_light stores col as a 1-based number — a\nreader deriving the letter from the binding address gets zero rows with no\nerror. Parse the binding's own A1 range instead; snippet executed against a\nreal IR (capital-regimes erm-153 extract) before committing.\n\nAddresses Greptile review on #107.",
          "timestamp": "2026-08-09T08:20:55Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/0c0884e2385c1f4924f10f9d668997c56239d7d6"
        },
        "date": 1786340550543,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 25.055,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 791.6,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 369.924,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 467.1,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 176.625,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 755.4,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 175.112,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4757.2,
            "unit": "MB"
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
          "id": "d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c",
          "message": "release: v0.8.2 — the recursion tells the whole truth\n\nReal per-op increment emission closes the #69 arc; round_charge places ROUND on the flow as source spreadsheets do (#92); between() scope sticks to its handle (#101); truthful stubs un-blind the rollforward API (#104); shape-gated conversions (#86, #89); skill honesty (#102, #103).",
          "timestamp": "2026-08-16T08:26:56Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/d7616b20f72dc0d41c87ad4c6bdc0f97c77a525c"
        },
        "date": 1786943932319,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 32.225,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 785.5,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 491.746,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 471.7,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 233.347,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 802.2,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 224.848,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4802.1,
            "unit": "MB"
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
          "id": "03406f74d9d047f6791799e54b4d6794ef2a13b4",
          "message": "chore(release): 0.9.0 — one name, and the surfaces meet you halfway (#156)\n\nThe import is the package name (gaspatchio_core stays as a deprecated\nalias until 1.0), accumulate() broadcasts scalar multiply/add,\ncumulative_survival() accepts survival-shaped input, and the\ntruth-telling season lands: docs, tutorials, the v2 spec, and the\ndocstring harness all describe the framework that ships. Version bumped\nin both crates, the Python project, and both lockfiles; the changelog\npromotes and curates the 26 commits since v0.8.2.",
          "timestamp": "2026-08-23T07:57:46Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/03406f74d9d047f6791799e54b4d6794ef2a13b4"
        },
        "date": 1787548863212,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 32.293,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 791.1,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 478.941,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 477,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 225.713,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 782.3,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 218.2,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4781,
            "unit": "MB"
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
          "id": "03406f74d9d047f6791799e54b4d6794ef2a13b4",
          "message": "chore(release): 0.9.0 — one name, and the surfaces meet you halfway (#156)\n\nThe import is the package name (gaspatchio_core stays as a deprecated\nalias until 1.0), accumulate() broadcasts scalar multiply/add,\ncumulative_survival() accepts survival-shaped input, and the\ntruth-telling season lands: docs, tutorials, the v2 spec, and the\ndocstring harness all describe the framework that ships. Version bumped\nin both crates, the Python project, and both lockfiles; the changelog\npromotes and curates the 26 commits since v0.8.2.",
          "timestamp": "2026-08-23T07:57:46Z",
          "url": "https://github.com/gaspatchio/gaspatchio/commit/03406f74d9d047f6791799e54b4d6794ef2a13b4"
        },
        "date": 1788172625999,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "Batch Search/1K-100sc-auto-wall",
            "value": 31.865,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-100sc-auto-peak",
            "value": 794,
            "unit": "MB"
          },
          {
            "name": "Batch Search/1K-100sc-checksum",
            "value": 1,
            "unit": "bool"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-wall",
            "value": 470.996,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/1K-1000sc-auto-peak",
            "value": 487.5,
            "unit": "MB"
          },
          {
            "name": "Batch Search/10K-100sc-auto-wall",
            "value": 222.568,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/10K-100sc-auto-peak",
            "value": 802,
            "unit": "MB"
          },
          {
            "name": "Batch Search/100K-10sc-auto-wall",
            "value": 215.246,
            "unit": "seconds"
          },
          {
            "name": "Batch Search/100K-10sc-auto-peak",
            "value": 4563.6,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}