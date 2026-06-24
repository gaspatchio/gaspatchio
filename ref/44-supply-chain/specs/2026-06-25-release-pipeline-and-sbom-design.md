# Release Pipeline & SBOM — Design

**Date:** 2026-06-25
**Status:** Draft (awaiting review)
**Topic:** `ref/44-supply-chain`
**Target repo:** `github.com/gaspatchio/gaspatchio` (new public repo; currently private as `opioinc/gaspatchio-core`)
**PyPI package:** `gaspatchio`

---

## Context

`gaspatchio-core` (Rust core + PyO3/maturin Python bindings → PyPI) is going public. The
maintainer wants to demonstrate software-supply-chain seriousness at launch, with an **SBOM**
specifically.

Current state (`.github/workflows/CI.yml` `release` job): builds wheels across
manylinux/windows/macos + sdist, downloads them, and creates a GitHub Release (draft → publish,
to satisfy immutable-release rules). It **publishes to PyPI manually** (no CI step), **declares
`attestations: write` + `id-token: write` that it never uses**, and **generates no SBOM**.

**Reference model — pydantic** (same Rust + maturin + PyPI stack), confirmed from their live
workflows:

| | pydantic-core (Rust/maturin) | pydantic (pure Python) |
|---|---|---|
| Publish | `uv publish --trusted-publishing always` | `pypa/gh-action-pypi-publish` (SHA-pinned) |
| Trusted Publishing (OIDC) | yes (`id-token: write`) | yes (`id-token: write`) |
| Integrity check | — | `twine check --strict` |
| SBOM | none | none |
| Explicit build-provenance attestation | none | none |
| Actions SHA-pinned | yes | yes |

pydantic establishes the baseline; **neither package generates an SBOM**, so an SBOM is one
deliberate step beyond the model.

---

## Goal

A single modern `release` job on the new repo that:

1. Publishes to PyPI via **Trusted Publishing** (OIDC, no API token) — matches pydantic.
2. Yields **PEP 740 attestations** on PyPI for free (via `gh-action-pypi-publish` ≥ 1.11 under
   Trusted Publishing) — this is why we use the gh action rather than `uv publish`, which did not
   emit PEP 740 attestations as of early 2026.
3. Generates and attaches a **CycloneDX SBOM** covering Rust **and** Python dependencies — the
   one deliberate differentiator vs. pydantic.
4. SHA-pins the actions it touches and runs `twine check --strict` — pydantic's hygiene.

## Non-goals (fast-follow, separate specs)

- Explicit `actions/attest-build-provenance` (SLSA-L2 on the GitHub-release wheels). pydantic
  skips it; PEP 740 already covers the PyPI artefacts. Easy to add later.
- OpenSSF Scorecard badge, `cargo-deny` / `deny.toml`, OSS-Fuzz.
- GitHub **repo settings** done in the UI, not commits: enabling Private Vulnerability Reporting,
  branch protection. (Referenced where relevant but not implemented by this spec.)

---

## Design

### 1. `release` job (on tag), extended

**Permissions:** `id-token: write` (PyPI OIDC auth + PEP 740 Sigstore signing) and
`contents: write` (create/publish the GitHub Release). **Drop** the currently-declared-but-unused
`attestations: write` (we are not using `actions/attest-*`).

Steps, in order:

1. **`actions/checkout`** (SHA-pinned) — *new*. The release job currently does not check out
   source; `syft` needs the dependency manifests (`Cargo.lock`, `pyproject.toml`) at the tagged
   commit.
2. **`actions/download-artifact`** (SHA-pinned) — the per-platform wheels + sdist from the build
   jobs into `dist/` (existing behaviour; consolidate artefacts into a single `dist/` dir).
3. **SBOM** — install `syft` (pinned version) and run
   `syft scan dir:. -o cyclonedx-json=sbom.cdx.json`, producing one CycloneDX SBOM. Rust
   components come from `Cargo.lock`; Python components from `bindings/python/pyproject.toml`
   and/or the built wheel `METADATA` (see Open Questions on the Python lockfile).
4. **Integrity** — `uvx twine check --strict dist/*` (matches pydantic).
5. **Publish** — `pypa/gh-action-pypi-publish` (SHA-pinned) uploading `dist/*` via Trusted
   Publishing. PyPI mints PEP 740 attestations automatically.
6. **GitHub Release** — existing draft → publish immutable flow; attach the wheels **and**
   `sbom.cdx.json` as release assets.

### 2. PyPI / repo settings (one-time, on the new repo — not commits)

- On PyPI, for project `gaspatchio` → *Publishing* → add a **Trusted Publisher**: owner
  `gaspatchio`, repo `gaspatchio`, the release workflow filename, environment (none today; see
  below). PEP 740 attestations require no extra config once Trusted Publishing is active.
- (Fast-follow, UI: enable GitHub **Private Vulnerability Reporting** so `SECURITY.md` resolves to
  a working "Report a vulnerability" button.)

### 3. Portable files (author now, targeting `gaspatchio/gaspatchio`)

- **`SECURITY.md`** at repo root — concise disclosure policy: report via GitHub Private
  Vulnerability Reporting (primary) with `security@opioinc.com` fallback, supported-versions note,
  response expectations. Wording sourced from the existing `security_plan.md`
  (`docs/security-plan` branch), condensed.
- **SHA-pin** every third-party action in the workflow(s) we touch (`actions/checkout`,
  `actions/download-artifact`, `actions/setup-uv` / `astral-sh/setup-uv`, `PyO3/maturin-action`,
  `pypa/gh-action-pypi-publish`), each with a trailing `# vX.Y` comment so Dependabot can still
  bump them.

### 4. Portable vs. repo-bound (re: the repo move)

- **Portable** (moves with the code): the workflow YAML, the SBOM step, `SECURITY.md`, the
  SHA-pins. Author with `gaspatchio/gaspatchio` URLs from the start.
- **Repo-bound** (only doable on the new repo): PyPI Trusted Publisher registration, PEP 740
  (automatic), GitHub vuln-reporting / branch-protection settings.

---

## Verification

- Validate `sbom.cdx.json` against the CycloneDX JSON schema (`syft`'s output or a CycloneDX
  validator) and confirm it lists **both** Rust and Python components with versions.
- Dry-run the release job via `workflow_dispatch` (or a pre-release tag) targeting **TestPyPI**
  before the first real release.
- Confirm: the PyPI project page shows verified/attestation details; `twine check --strict`
  passes; `sbom.cdx.json` is attached to the GitHub Release.

---

## Sequencing

Author all files targeting `gaspatchio/gaspatchio`. Land them as the new repo's initial
release-pipeline setup — either folded into `main` before the public push, or as the first public
commits. The pipeline is dormant until the new repo **and** the PyPI Trusted Publisher exist; the
first tagged release on the new repo exercises it end-to-end.

---

## Open questions

1. **Python dependency source for syft.** `uv.lock` lives at the workspace root (outside this
   repo); only `Cargo.lock` is in-repo. Decide whether the SBOM's Python components come from
   `pyproject.toml`, the built wheel `METADATA`, or by also scanning the wheel
   (`syft scan` over `dist/*.whl`). Validate during implementation that the SBOM captures the full
   runtime Python closure, not just direct declares.
2. **GitHub Environment.** The release job uses no Environment today. Optionally add a
   `release`/`pypi` Environment (with required reviewers) for the Trusted Publisher — modest extra
   protection; decide at implementation.
3. **SPDX as well?** One extra `-o spdx-json=sbom.spdx.json` flag would emit SPDX alongside
   CycloneDX. Defer unless a consumer needs it.
