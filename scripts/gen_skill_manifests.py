#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Generate the Claude plugin + self-hosted marketplace from the canonical registry.

skills/skills.toml is the single source of truth for the skill set, its order,
and the plugin metadata. This generates the Claude Code plugin manifest
(skills/.claude-plugin/plugin.json, which globs its own plugin root) and the
self-hosted marketplace listing (.claude-plugin/marketplace.json) from that SSOT.

The plugin root is `skills/`, not the repository root. A marketplace entry's
`source` is the payload: Claude Code copies that whole directory into
~/.claude/plugins/cache on install. Rooting the plugin at the repository would
ship the Rust crate, the Python bindings, the test suite and ref/ to anyone who
wanted seven markdown skills.

    bindings/python/.venv/bin/python scripts/gen_skill_manifests.py            # write
    bindings/python/.venv/bin/python scripts/gen_skill_manifests.py --check    # verify (exit 1 on drift)

The bindings/python/AGENTS.md install count/list is verified by
tests/skills/test_skill_manifests.py, not rewritten here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "skills" / "skills.toml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def load_order() -> list[str]:
    """Return the ordered skill list from the canonical registry."""
    with REGISTRY.open("rb") as fh:
        return list(tomllib.load(fh)["order"])


def load_plugin() -> dict:
    """Return the [plugin] metadata table from the canonical registry."""
    with REGISTRY.open("rb") as fh:
        return dict(tomllib.load(fh)["plugin"])


def _dumps(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_claude_plugin() -> str:
    """The Claude Code plugin manifest (globs its own root; self-maintaining).

    Lives at skills/.claude-plugin/plugin.json, so the plugin root *is* the
    skills tree and "./" scans it for <name>/SKILL.md. Still a glob, so adding
    a skill directory needs no manifest edit.
    """
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "version": m["version"],
        "description": m["description"],
        "author": {"name": m["author_name"], "url": m["author_url"]},
        "homepage": m["homepage"],
        "repository": m["repository"],
        "license": m["license"],
        "keywords": m["keywords"],
        "skills": "./",
    })


def render_marketplace() -> str:
    """Self-hosted marketplace listing skills/ as the single plugin payload."""
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "owner": {"name": m["author_name"]},   # Gate 1: owner takes name/email, not url
        "description": m["description"],        # required by `claude plugin validate --strict`
        "plugins": [{
            "name": m["name"],
            "source": "./skills",   # the payload: skills only, not the whole repo
            "description": m["description"],
            "version": m["version"],
        }],
    })


def render_cursor_plugin() -> str:
    """Thin Cursor manifest pointing at the one canonical ./skills tree."""
    m = load_plugin()
    return _dumps({
        "name": m["name"],
        "version": m["version"],
        "description": m["description"],
        "author": {"name": m["author_name"], "url": m["author_url"]},
        "license": m["license"],
        "skills": "./skills/",   # Gate 3: dir-pointer, no ../ traversal
    })


def render_copilot_marketplace() -> str:
    """Copilot agent-plugin marketplace (.github/plugin/marketplace.json).

    Gate 3: same self-hosted shape as the Claude marketplace.
    """
    return render_marketplace()


def render_copilot_instructions() -> str:
    """Copilot always-loaded instructions, derived from the root AGENTS.md."""
    body = AGENTS_MD.read_text(encoding="utf-8")
    header = ("<!-- GENERATED from AGENTS.md by scripts/gen_skill_manifests.py. "
              "Do not edit. -->\n\n")
    return header + body


BEGIN_PRINCIPLES = "<!-- BEGIN GENERATED PRINCIPLES -->"
END_PRINCIPLES = "<!-- END GENERATED PRINCIPLES -->"
PRINCIPLES_MD = REPO_ROOT / "PRINCIPLES.md"


RESOLUTION_MARKER = "**The tension you will hit most.**"


def _blocks() -> list[tuple[str, str]]:
    """PRINCIPLES.md as (heading, body) pairs, H1 and file-meta blockquote dropped.

    The first pair has an empty heading and carries the opening paragraph.
    """
    lines = PRINCIPLES_MD.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if not ln.startswith("# ") and not ln.startswith(">")]
    out: list[tuple[str, str]] = []
    heading, body = "", []
    for line in kept:
        if line.startswith("## "):
            out.append((heading, "\n".join(body).strip()))
            heading, body = line[3:].strip(), []
        elif line.strip() != "---":
            body.append(line)
    out.append((heading, "\n".join(body).strip()))
    return out


def _sentences(paragraph: str) -> list[str]:
    """The sentences of one paragraph, whitespace collapsed."""
    flat = " ".join(paragraph.split())
    return [s for s in re.split(r"(?<=[.!?])\s+", flat) if s]


def principles_body() -> str:
    """PRINCIPLES.md condensed for inlining under an `##` heading.

    Codex merges the root AGENTS.md with the one nearest the working directory
    and stops adding files once the pair reaches `project_doc_max_bytes`, so
    every byte the root file spends is a byte a subtree file does not get. The
    full positions inlined ran 6,825 B; this carries each position's heading
    with the sentence that sets the problem and the sentence that states the
    answer, plus the resolution paragraph agents act on, and points at
    PRINCIPLES.md for the rest.

    First sentence alone would be shorter and would misread: four of the seven
    open on the rejected alternative ("Recursive cell-graphs ... were the answer
    when actuarial modelling first landed in Python"), so an agent quoting one
    would quote the position's opposite. The closing sentence is where each
    position lands, so both are kept.
    """
    blocks = _blocks()
    parts = [_sentences(blocks[0][1])[0]]
    for heading, body in blocks[1:]:
        if heading == "Using these principles":
            resolution = next(
                p for p in body.split("\n\n") if p.lstrip().startswith(RESOLUTION_MARKER)
            )
            parts += [f"### {heading}", resolution.strip()]
            continue
        said = _sentences(body)
        keep = said[:1] if len(said) == 1 else [said[0], said[-1]]
        parts += [f"### {heading}", " ".join(keep)]
    return "\n\n".join(parts) + "\n"


def render_agents_md() -> str:
    """Root AGENTS.md with the generated principles block refreshed in place.

    Codex (and every other AGENTS.md reader) does NOT expand `@file` imports the
    way CLAUDE.md does, and `project_doc_fallback_filenames` only fires when
    AGENTS.md is absent. Inlining is the only way the principles are guaranteed
    to be in the model's context, so the condensed positions live between the
    markers and PRINCIPLES.md stays the single source of truth for the wording.
    """
    current = AGENTS_MD.read_text(encoding="utf-8")
    start = current.index(BEGIN_PRINCIPLES)
    end = current.index(END_PRINCIPLES)
    head = current[: start + len(BEGIN_PRINCIPLES)]
    tail = current[end:]
    return f"{head}\n\n{principles_body()}\n{tail}"


ARTIFACTS = {
    REPO_ROOT / "skills" / ".claude-plugin" / "plugin.json": render_claude_plugin,
    REPO_ROOT / ".claude-plugin" / "marketplace.json": render_marketplace,
    REPO_ROOT / ".cursor-plugin" / "plugin.json": render_cursor_plugin,
    REPO_ROOT / ".github" / "plugin" / "marketplace.json": render_copilot_marketplace,
    AGENTS_MD: render_agents_md,
    REPO_ROOT / ".github" / "copilot-instructions.md": render_copilot_instructions,
}


def main() -> int:
    """Write (or, with --check, verify) the generated Claude plugin artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any generated file is out of date",
    )
    args = parser.parse_args()
    drift: list[Path] = []
    for path, renderer in ARTIFACTS.items():
        expected = renderer()
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != expected:
                drift.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    if args.check and drift:
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in drift)
        print(
            f"Out-of-date generated file(s): {names}\n"
            f"Run: bindings/python/.venv/bin/python scripts/gen_skill_manifests.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
