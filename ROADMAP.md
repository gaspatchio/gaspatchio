# Roadmap and issue tracking

This page explains two things: how a bug report moves from "reported" to "released",
and how larger upcoming features are tracked publicly.

## How bugs move

Every bug follows the same visible trail, so you can watch yours the whole way:

| Stage | What you'll see on the issue |
|---|---|
| Reported | Opened with the `bug` and `needs-triage` labels (applied automatically by the issue template) |
| Confirmed | `needs-triage` is replaced by `confirmed` once a maintainer reproduces it. If we can't reproduce it yet, you'll see `needs-repro` or `needs-info` instead |
| In progress | A pull request is linked to the issue |
| Fixed, awaiting release | The issue closes when the fix merges, and gains the `pending-release` label — the fix is on `main` but not yet on PyPI |
| Released | `pending-release` is removed and the issue is attached to the release's milestone, which names the version that ships the fix |

Prefer not to post code or assumption values publicly? Email any bug to
**security@opioinc.com** — see [SECURITY.md](SECURITY.md). We confirm it, open an
anonymised public issue with a rewritten reproduction, and send you the link so you
can track it through the stages above. Your name, employer, and model details never
appear.

## How larger features are tracked

Each larger feature gets **one public tracking issue** labelled `roadmap`, holding a
short statement of the problem it solves and one status label:

| Status | Meaning |
|---|---|
| `exploring` | We think this matters and are working out the shape of it |
| `building` | In active development |
| `shipped` | Released — the issue is closed with a link to the release |

Roadmap issues are deliberately brief. Design work and development happen on private
branches, and the feature lands in a public pull request when it's ready for use.
Comments on roadmap issues are open and welcome — telling us *why* a feature matters
to your work (which regime, which product, which reporting deadline) directly shapes
what gets built first.

**If you're considering contributing a feature:** anything labelled `building` is
already in active development, so comment on the issue before starting work in that
area — otherwise your effort may collide with work that's about to land.

## The usual disclaimer

This roadmap describes current intent, not commitment. Items may change scope, move,
or be dropped as we learn more, and nothing here is a promise to deliver any feature
by any date. Bug fixes always take priority over roadmap work.
