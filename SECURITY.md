# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities in gaspatchio **privately** — not via public
issues or pull requests.

- **Preferred:** use GitHub's private vulnerability reporting. Open the
  [Security tab](https://github.com/gaspatchio/gaspatchio/security) of this repository
  and click **"Report a vulnerability"**. This opens an advisory visible only to the
  maintainers.
- **Alternative:** email **security@opioinc.com**.

Please include the affected version, a description of the issue and its impact, and,
where possible, a minimal reproduction.

## Our commitments

- We acknowledge new reports within **2 business days**.
- We aim to give an initial assessment (confirm or dismiss) within **7 business days**.
- We keep you informed as we work on a fix and credit you in the published advisory
  unless you ask us not to.

## Supported versions

gaspatchio is pre-1.0; security fixes are released against the **latest** version
published on PyPI. We recommend always tracking the latest release.

## Software Bill of Materials (SBOM)

Every release ships a CycloneDX SBOM (`sbom.cdx.json`, covering both the Rust and Python
dependency graphs) as a GitHub Release asset. Fetch it with:

```bash
gh release download <tag> --repo gaspatchio/gaspatchio --pattern 'sbom.cdx.json'
```

Wheels published to PyPI carry [PEP 740](https://peps.python.org/pep-0740/) build-provenance
attestations, generated automatically via PyPI Trusted Publishing.

## Disclosure

Confirmed vulnerabilities are published as GitHub Security Advisories on this
repository once a fix is available.
