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

- [ ] `cd bindings/python && uv run pytest -v` passes
- [ ] `uv run pytest --doctest-modules --doctest-glob="*.pyi"` passes
- [ ] `uv run mypy gaspatchio_core` and `uv run pyright gaspatchio_core` pass
- [ ] `cd core && cargo test` passes (if Rust changed)

**If this changes a projected number:**

- [ ] Before/after shown on a reproducible model point, with the reason the new
      number is right.
- [ ] Timing convention stated explicitly (beginning vs end of period) — constant
      rates hide this class of error.

**If this changes the public API:**

- [ ] Type stubs updated and `uv run python -m mypy.stubtest gaspatchio_core` passes.
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
