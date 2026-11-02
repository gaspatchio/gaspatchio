# Contributing to Gaspatchio

Thanks for helping. This document is the canonical contribution guide — it applies to
humans and to AI coding agents equally. Agents should also read [`AGENTS.md`](AGENTS.md),
which carries the framework knowledge.

Every change should be justifiable against [`PRINCIPLES.md`](PRINCIPLES.md). When a change
serves one principle and strains another, say so in the PR — that argument belongs in the
open, not settled implicitly.

## Reporting a bug

Open an issue using the bug template. **Wrong numbers matter as much as crashes** — a
silently wrong reserve is the failure mode this project cares about most.

If you work at an insurer and cannot post code or assumption values publicly, email the
same report to **security@opioinc.com** instead. That channel accepts ordinary bugs, not
just vulnerabilities, and we open an anonymised public issue with a rewritten
reproduction. See [`SECURITY.md`](SECURITY.md).

### Writing a good issue title

The title names **the surface, the wrong behaviour, and the mechanism**. Long and specific
beats short and vague — the title is what a future reader greps.

    Table: an undeclared source column is silently promoted to a dimension key
    Table.lookup() returns a bare pl.Expr, so `lookup(...) * af.col` raises
      while `af.col * lookup(...)` works
    deduct_nar: a negative net amount at risk silently credits the account
      value and compounds — needs the corridor test

- **Lead with what is *silently* wrong.** A wrong number that looks right is the
  highest-severity class here — it survives testing and surfaces in a valuation. Say
  "silently" in the title when it applies.
- **Carry the contrast case** when one exists ("X raises while Y works"). It is the
  fastest route to the mechanism.
- Include a minimal reproduction. Synthetic data is preferred — neutral column names and
  made-up rates reproduce most bugs.

New issues land `needs-triage`. `confirmed`, `pending-release`, and the roadmap labels
(`exploring`/`building`/`shipped`) record a maintainer's judgement; please don't
self-apply them.

## Setting up

**Every Python command runs from `bindings/python`.** There is no Python project at the
repository root — running `uv` there resolves nothing useful, and in a multi-repo checkout
it can pick up a workspace spanning sibling repositories.

```bash
cd bindings/python && uv sync --locked                    # exact pinned versions, matching CI
cd bindings/python && uvx maturin develop --release --uv  # after any Rust change
cd bindings/python && .venv/bin/python -m pytest -v
cd core && cargo test && cargo fmt && cargo clippy
```

`develop`, not `build`: a `.pth` puts `bindings/python` on `sys.path`, so imports resolve to
the source tree and the extension has to land there — `maturin build` only writes a wheel and
leaves the imported `.so` stale.

**In this repository, run the tests, the type checkers and `gspio` from `.venv/bin/`, not
through `uv run`.** `uv run` re-syncs the project first, and once any Rust file has changed
the re-sync rebuilds the extension at the dev profile, over the release build `maturin
develop --release` put there: test outcomes can change, and every timing figure goes wrong.
Building a model in a project of your own, where gaspatchio comes from PyPI, is different:
there `uv run gspio …` is the right spelling, because there is no extension to rebuild.

`uv.lock` is tracked. If you intend to move a dependency, run `uv lock` and commit the
result with your change.

`Cargo.lock` is tracked too, and the core's wheels and sdist carry the notices of every Rust
crate it builds the extension from, in `bindings/python/third-party-notices.txt`. If you move
a Rust dependency, rewrite them with `python3 scripts/rust_notices.py write`, run
`python3 scripts/rust_notices.py check`, and commit the result with your change. Both need
Python 3.11 or later, for `tomllib`, and cargo. `write` needs the network as well -- crates.io,
and raw.githubusercontent.com for three licence texts it reads from the Polars repository --
and cargo-about 0.9.2 on `PATH`, installed as the Rust Crate Notices job in
`.github/workflows/CI.yml` installs it. `check` runs offline once cargo has the crates
(`CARGO_NET_OFFLINE=true`). That job fails until the file matches `Cargo.lock`, and so
Dependabot's weekly grouped cargo pull request fails it until someone runs `write` on its
branch and pushes the result.

### Instruction files have a byte budget

Codex merges instruction files from the repository root down to your working directory and
**stops adding them once the combined size reaches `project_doc_max_bytes` — 32 KiB by
default, silently.** The tail is dropped with no warning, and the tail is the file nearest
your code. The root [`AGENTS.md`](AGENTS.md) plus either subtree `AGENTS.md` are held under
that budget with headroom by `tests/skills/test_skill_manifests.py`; the longer-form material
lives in this file, `core/docs/` and `bindings/python/docs/`, pointed at by path.

If you add instruction files of your own — a nested `AGENTS.md`, or anything else Codex
merges — raise the cap in **`~/.codex/config.toml`**, not in the repository (a repo-level
`.codex/config.toml` is ignored):

```toml
project_doc_max_bytes = 65536
```

Claude Code, Cursor and Copilot document no such cap, and `CLAUDE.md` imports the moved files
by path, so a Claude session reads all of it either way.

## Branch or fork?

Both work. Which you use depends on whether you have commit access:

- **Commit access** → push a branch to this repository and open the PR from it. Simpler,
  and CI behaves identically to `main`.
- **No commit access** → fork, push to your fork, open the PR from there. This is the
  standard GitHub flow for outside contributors and nothing about it is second-class.

If you find yourself contributing regularly from a fork, ask for commit access — once
trust is established a fork adds friction and buys nothing.

**On CI:** fork-based PRs cannot read repository secrets, so some workflows will not run on
them:

| Workflow | Needs | On a fork PR |
|----------|-------|--------------|
| `CI.yml`, `bench-pr.yml` | `GITHUB_TOKEN` (automatic) | Runs |
| `evals.yml` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BENCHMARKS_DEPLOY_KEY` | **Skipped** |
| `trigger-rag-rebuild.yml` | `MIX_DISPATCH_PAT` | **Skipped** |

A maintainer re-runs the skipped workflows from a branch before merging anything that could
affect them. Leave **"Allow edits by maintainers"** ticked so a maintainer can push a
rebase or a small fix rather than bouncing the PR back to you.

## Commits

- **Sign your commits.** `main` is protected by a ruleset requiring signed commits.
  Register your key on GitHub **as a signing key** — that is a separate entry from an auth
  key, even when the key material is identical:

  ```bash
  ssh-keygen -t ed25519 -C "signing" -f ~/.ssh/id_ed25519_signing
  git config --global gpg.format ssh
  git config --global user.signingkey ~/.ssh/id_ed25519_signing.pub
  git config --global commit.gpgsign true
  ```

  Set this up **before** you start a branch. `required_signatures` is evaluated against
  every commit in the PR, and **a squash merge does not sidestep it** — GitHub refuses the
  merge before it creates the squash commit. Unsigned commits therefore have to be
  re-signed, which means a rebase. If you're already stuck with some, say so on the PR and
  a maintainer will rebase it for you (your authorship is preserved); it isn't something
  you need to untangle alone.

- **Conventional commits** (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`) with a scope
  where one applies. Explain the *why*, not just the *what*. Keep commits focused and
  atomic.
- Reference the GitHub issue (`#N`) when there is one.
- **Never** add an AI-assistant signature or a `Co-Authored-By: <assistant>` trailer.

## Pull requests

- Title in conventional-commit form with a scope, matching the commit style.
- Body closes its issues explicitly: `Fixes #N.`
- **One PR, one concern.** Don't append unrelated commits to an open PR. Performance work
  reviewed as a footnote to a docs sync is how correctness regressions get through — split
  it out, and re-request review when the head moves.
- **Numerical changes need evidence, not assertion.** If a change moves a projected value,
  show the before/after on a reproducible model point and say why the new number is right.
- Docstring examples are tests. Run
  `.venv/bin/python -m pytest --doctest-modules --doctest-glob="*.pyi"`.
- Both type checkers run over the whole package and **neither is clean**, so passing is
  not the rule and never was. Run them from `bindings/python`:
  `.venv/bin/python -m mypy gaspatchio` and `.venv/bin/python -m pyright gaspatchio`
  (not `uv run`, for the reason under *Setting up*; neither tool reads the extension
  anyway). Two things are enforced, and they are different: the files in your
  diff gain no new errors from either tool, and CI holds each whole-package count to a
  ceiling that only moves down. `.github/RATCHETS.md` says what every enforced figure is
  and how to reproduce it.

`main` rejects force-pushes and deletions, and we **squash merge**.

## Reviewing

Reviewers, and anyone commenting on someone else's PR:

- **Verify claims; don't relay them.** "Reconciles to zero" and "all tests pass" are
  hypotheses until you have run them. State what you ran, and on which SHA.
- **Bind test claims to a SHA.** A branch can move between your fetch and your review; a
  stale "all green" misleads the author more than saying nothing would.
- **Anchor findings to lines** with inline comments rather than a wall of prose. Reserve
  "request changes" for genuine ship-blockers.
- **Separate blockers from risks from nits, and say which is which.** A nit presented at
  the same volume as a blocker costs the author time.
- **Check the timing convention** on anything touching projections. The two conventions
  do not give the same numbers, even at flat rates: a survival curve differs by one
  period's decrement, a prospective value by one period's discount. What flat rates hide
  is a wrong conversion between them — at a constant rate one convention is the other
  times one `v`, and discount factors built from each period's own rate equal the running
  product — so a change that converts by one multiplication, or builds its factors that
  way, passes every flat-rate test and is wrong once rates vary. Ask for a test with rates
  that vary by period.

## Documentation and design documents

Docs target actuaries (who know the products and need to see their workflow in the code) and
LLMs (which need complete, realistic examples). Run every section **business problem ->
gaspatchio solution -> code example**; skip internals unless they change the call.

Specs and plans live in `ref/<topic>/` beside the reference material:
`specs/YYYY-MM-DD-<name>-design.md`, `plans/YYYY-MM-DD-<name>.md`; ask which topic if unsure.
An agent's planning skills save there too: the Superpowers plugin's brainstorming and
plan-writing skills, for one, default to a `docs/superpowers/` directory this repository does
not have.

## Code of conduct

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
