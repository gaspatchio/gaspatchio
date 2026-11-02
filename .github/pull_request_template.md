<!--
Title this PR in conventional-commit form, e.g.
  fix(rollforward): broadcast scalar inputs; name the NAR timing convention
See CONTRIBUTING.md for the full guide.
-->

## What and why

<!-- What changes, and the reason. Link the issue: "Fixes #N." -->

## Principles

<!-- Which principle does this serve, and which (if any) does it strain?
     See PRINCIPLES.md. Most good changes serve one and strain none; the ones
     worth arguing about serve one and strain another — make that argument here. -->

## Scope

- [ ] This PR addresses **one concern**. Unrelated work has been split out.

## Evidence

<!-- Say what you ran, and on which commit. "CI is green" is not evidence for a
     behaviour claim — name the test. -->

- [ ] `cd bindings/python && .venv/bin/python -m pytest -v` passes
- [ ] `.venv/bin/python -m pytest --doctest-modules --doctest-glob="*.pyi"` passes
- [ ] From `bindings/python`, `.venv/bin/python -m mypy <your files>` and
      `.venv/bin/python -m pyright <your files>` add no new errors. Neither tool is
      clean over the whole package and passing is not the rule: CI holds each
      whole-package count to a ceiling recorded in `.github/ratchets.env`, and the
      per-change rule is the one above. The `uv run` spelling re-syncs the project
      and rebuilds the Rust extension, which neither type checker reads.
- [ ] `cd core && cargo test` passes (if Rust changed)

**If this changes a projected number:**

- [ ] Before/after shown on a reproducible model point, with the reason the new
      number is right.
- [ ] Timing convention stated explicitly (beginning vs end of period) — constant
      rates hide this class of error.

**If this changes the public API:**

- [ ] Type stubs updated and `.venv/bin/python -m pytest tests/test_stub_sync.py` passes — it runs
      stubtest with the config and allowlist the repo ships. The bare
      `mypy.stubtest gaspatchio` reads no config and stops before it compares anything.
- [ ] Docstring examples added or updated (they are executed as tests).

## Changelog

- [ ] User-visible change (behaviour, API, a projected number, performance) → an
      entry under `## [Unreleased]`, or under the pending release section if one is
      open. Internal refactors and repo hygiene don't need one.
- [ ] **If anything merged to `main` while this PR was open, re-check that your entry
      is still there.** Concurrent PRs edit the same block, so the later merge
      silently wins and no test catches it.

## Notes for the reviewer

<!-- Anything you want looked at hardest, and anything you're unsure about. -->
