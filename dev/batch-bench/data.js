window.BENCHMARK_DATA = {
  "lastUpdate": 1785138497489,
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
      }
    ]
  }
}