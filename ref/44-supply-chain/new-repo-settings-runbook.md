# New-repo settings runbook (gaspatchio/gaspatchio)

One-time, non-commit setup required for the release pipeline (ref/44-supply-chain) to
function. Do these once the public repo exists.

## PyPI — register the Trusted Publisher
1. Log in to https://pypi.org as an owner of the `gaspatchio` project.
2. Project → **Settings** → **Publishing** → **Add a new pending/trusted publisher**
   (GitHub Actions):
   - Owner: `gaspatchio`
   - Repository: `gaspatchio`
   - Workflow filename: `CI.yml`
   - Environment: *(leave blank — the release job uses no environment)*
3. Save. No API token is needed afterward; OIDC handles auth and PEP 740 attestations
   are generated automatically by `gh-action-pypi-publish`.

## GitHub — enable private vulnerability reporting
1. Repo → **Settings** → **Code security and analysis**.
2. Enable **Private vulnerability reporting** (makes the "Report a vulnerability"
   button in SECURITY.md resolve).
3. Update maintainer notification settings — GitHub does **not** notify on new private
   reports by default.

## First-release verification (do once on the new repo)
1. Trigger a release on a pre-release tag (or `workflow_dispatch` against **TestPyPI**
   first by temporarily pointing `gh-action-pypi-publish` at TestPyPI).
2. Confirm: the wheel + `sbom.cdx.json` are attached to the GitHub Release; the PyPI
   project page shows verified/attestation details; `twine check --strict` passed.
