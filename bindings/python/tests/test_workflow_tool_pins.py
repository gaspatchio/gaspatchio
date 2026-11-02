# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every workflow installs each tool it runs at a version this repository names.

The workflows under ``.github/workflows/`` gate changes, qualify the engine,
and build and check what a release publishes. A tool installed at whatever
version is newest that day can change a verdict on a tree that did not change,
or the bytes of a release built from one, and runs code nobody here reviewed.

Each workflow declares what it installs, in comment lines that start at the
first column, which these tests read::

    # pins: <tool> <count>
    # floats: <requirement> [<requirement> ...] -- <reason>
    # runner: <label> x86-64 <Linux|Windows>

``pins`` names a tool the workflow fetches and the number of install commands
that fetch it. A tool's name is read off the command: the distribution a
requirement or an archive names, the stem of a ``-r`` or build-constraints
file, or the crate that ``cargo install --path /tmp/<crate>-src`` builds.
``floats`` names an install that takes the newest release on purpose, by the
requirements it writes, exactly as written, and says why. ``runner`` gives the
platform of a runner label the tests do not know. A workflow that installs
nothing declares nothing. The tests find the workflows with a glob, so a tree
that lacks one of them, or has a new one, is held to the same rules.

The tests read each workflow as text, with no YAML parser: its jobs, each
job's ``runs-on``, and each step's ``uses``, ``if``, ``with``, ``env`` and
``run``. What they guarantee is this, and no more:

* The tools a workflow fetches are the tools it declares, each in as many
  install commands as it declares, and a declaration it does not keep fails as
  an undeclared install does. CI.yml and licence-check.yml, which build and
  check what ships, must also fetch the tools ``REQUIRED_TOOLS`` names. So
  deleting one of their installs fails even if its declaration goes with it.
* Every command in a ``run`` block in a form ``_form`` knows names an exact
  version, a local path or a repository file whose every requirement names an
  exact version. That covers cargo install and binstall; uv tool install and
  run, uvx, uv run --with, uv build and uv sync; uv pip, pip, pip3 and python
  -m pip install; pipx; npx, npm exec and npm install. It holds after ``then``,
  ``do``, ``sudo``, ``env`` and the like, and inside ``$(...)``. The only
  exceptions are the floats a workflow declares, each with its reason.
* A tool uv installs from a local archive carries a constraints file, and from
  a source archive a build-constraints file as well, unless ``DEPENDENCY_FREE``
  says it has nothing to constrain. ``uv build`` carries a build-constraints
  file and ``--require-hashes``.
* Every ``astral-sh/setup-uv`` step names an exact uv and a checksum. The
  checksum comes through an env name that says which platform's archive it
  is. It is read in a job on a runner of that platform, a GitHub-hosted label
  the tests know or one the workflow declares, or behind an ``if`` that runs
  only on that platform, and so is every other platform's digest a step reads.
  Every ``PyO3/maturin-action`` step names an exact ``maturin-version``. Every
  workflow that installs uv names the same release, with the same digest for
  each platform.

They do not show that a digest was checked; the step that downloads each
archive does that. Nor do they show that a constraints file lists everything a
tool depends on: uv resolves what it leaves out. They cannot see what a script
a workflow runs installs by itself (``scripts/check-clones.sh`` pins jscpd on
its own), nor OS packages installed with apt-get.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# The source distribution ships tests/ and not .github/, so a run from an
# unpacked sdist stands down; inside a checkout the workflow's absence is the
# fault. The reasoning test_ratchet_documents_agree.py gives for its own guard.
pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a repository checkout; the sdist ships tests/ but no .github/",
)

# Every workflow the tests find.
WORKFLOW_NAMES = sorted(
    path.name for pattern in ("*.yml", "*.yaml") for path in WORKFLOWS.glob(pattern)
)

# The tools the workflows that build and check what ships must fetch, with the
# number of install commands that fetch each.
REQUIRED_TOOLS: dict[str, dict[str, int]] = {
    "CI.yml": {
        "ruff": 1,
        "import-linter": 1,
        "cargo-about": 1,
        "maturin": 1,
        "twine": 2,
        "hatchling": 2,
    },
    "licence-check.yml": {"reuse": 1, "pip-licenses": 1, "cargo-license": 1},
}

# A workflow's declaration of what it installs, one per line.
DECLARATION = re.compile(r"^# (pins|floats|runner):(.*)$", re.MULTILINE)

# Tools that depend on nothing on the interpreters the workflows run them on,
# so installing one from its archive needs no constraints file.
DEPENDENCY_FREE = {
    "maturin": "its wheel needs tomli before Python 3.11 and nothing after",
}

# The env names that hold one platform's digest, and that platform's
# GitHub-hosted runners. A workflow declares any other runner it uses.
PLATFORM_DIGESTS = {
    "SETUP_UV_SHA256": "Linux",
    "MATURIN_SHA256": "Linux",
    "SETUP_UV_SHA256_WINDOWS": "Windows",
}
PLATFORM_RUNNERS = {
    "Linux": {"ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04"},
    "Windows": {"windows-latest", "windows-2025", "windows-2022"},
}

# Variables a step sets at run time, which the test cannot evaluate.
# CORE_WHEEL is the core wheel a JAX engine workflow builds, which the step
# before selects. ruff_version is read out of the exact `ruff==` pin in
# bindings/python/pyproject.toml, and the test reads it the same way.
RUNTIME_VALUES = {
    "CORE_WHEEL": "/runner-temp/jax-core-wheels/gaspatchio.whl",
    "RUNNER_TEMP": "/runner-temp",
    "HOME": "/home/runner",
}

EXACT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]*\])?(==|@)[0-9][0-9A-Za-z.!+-]*$"
)
LOCAL = re.compile(r"^(\.{1,2}/|/|~/|file://|[A-Za-z0-9._-]+(\[[^\]]*\])? @ file://)")
VERSION = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ENV_REFERENCE = re.compile(r"^\$\{\{\s*env\.([A-Za-z_]\w*)\s*\}\}$")
REFERENCE = re.compile(
    r"\$\{\{\s*env\.([A-Za-z_]\w*)\s*\}\}|\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)"
)
ASSIGNMENT = re.compile(
    r'^\s+([A-Z][A-Z0-9_]*):\s*"?([^"\s#]+)"?\s*(?:#.*)?$', re.MULTILINE
)
PIP = re.compile(r"^(.*/)?pip(3(\.[0-9]+)?)?$")
PYTHON = re.compile(r"^(.*/)?python(3(\.[0-9]+)?)?$")
REQUIREMENT_LINE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]*\])?==[0-9][0-9A-Za-z.!+-]*\s*(;[^#]*)?"
    r"(\s+--hash=sha256:[0-9a-f]{64})*\s*$"
)
# Words that come before a command without being it, each with the options of
# its own that take a value.
PREFIXES: dict[str, set[str]] = {
    word: set()
    for word in ("if", "then", "elif", "else", "do", "while", "until", "!", "time")
} | {word: set() for word in ("exec", "nohup", "command", "builtin")}
PREFIXES["sudo"] = {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}
PREFIXES["env"] = {"-u", "-C", "-S"}
PREFIXES["xargs"] = {"-n", "-I", "-L", "-P", "-d", "-E", "-s", "-a"}
# Options whose next word is their value rather than a package to install.
VALUE_OPTIONS = {
    "--python",
    "-p",
    "--constraints",
    "-c",
    "--build-constraints",
    "--build-constraint",
    "-b",
    "--overrides",
    "--with",
    "--with-requirements",
    "--exclude-newer",
    "--from",
    "-r",
    "--requirement",
    "--target",
    "--prefix",
    "--root",
    "--path",
    "--version",
    "--vers",
    "--features",
    "--out",
    "--out-dir",
    "-o",
    "--interpreter",
    "-i",
    "--spec",
    "--package",
    "--group",
    "--index-url",
    "--extra-index-url",
}


@dataclass
class Declarations:
    """What a workflow declares it installs, and what is wrong with the lines."""

    pins: dict[str, int] = field(default_factory=dict)
    floats: list[tuple[frozenset[str], str]] = field(default_factory=list)
    runners: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _declarations(text: str) -> Declarations:
    """Return the workflow's ``pins``, ``floats`` and ``runner`` lines, read."""
    found = Declarations()
    for kind, written in DECLARATION.findall(text):
        line = f"# {kind}:{written}"
        rest = written.strip()
        if kind == "pins":
            pin = re.fullmatch(r"([A-Za-z0-9@][\w./@-]*) ([1-9][0-9]*)", rest)
            if pin is None or pin.group(1) in found.pins:
                found.problems.append(f"`{line}` is not `# pins: <tool> <count>`, once")
            else:
                found.pins[pin.group(1)] = int(pin.group(2))
        elif kind == "floats":
            requirements, separator, reason = rest.partition(" -- ")
            if not separator or not requirements.split() or not reason.strip():
                found.problems.append(
                    f"`{line}` is not `# floats: <requirement> ... -- <reason>`"
                )
            else:
                found.floats.append((frozenset(requirements.split()), reason.strip()))
        else:
            runner = re.fullmatch(r"(\S+) x86-64 (Linux|Windows)", rest)
            if runner is None:
                found.problems.append(
                    f"`{line}` is not `# runner: <label> x86-64 <Linux|Windows>`"
                )
            else:
                found.runners[runner.group(1)] = runner.group(2)
    return found


@dataclass
class Step:
    """One step of a workflow, as the test reads it."""

    job: str
    runs_on: str
    uses: str = ""
    condition: str = ""
    inputs: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    run: str = ""


def _key(text: str) -> tuple[str, str]:
    """Return a ``key: value`` line's key and its value, comment and quotes dropped."""
    key, _, value = text.partition(":")
    value = re.sub(r"\s+#.*$", "", value.strip()).strip()
    if len(value) > 1 and value[0] in "'\"" and value[-1] == value[0]:
        value = value[1:-1]
    return key.strip(), value


def _block(lines: list[str], at: int, indent: int) -> tuple[list[str], int]:
    """Return the lines after ``at`` indented past ``indent``, and where they end."""
    body = []
    end = at + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
        end += 1
    while body and not body[-1].strip():
        body.pop()
    return body, end


def _dedent(lines: list[str]) -> list[str]:
    """Return ``lines`` with the indentation they share removed."""
    margin = min(
        (len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0
    )
    return [line[margin:] for line in lines]


def _step(lines: list[str], job: str, runs_on: str, indent: int) -> Step:
    """Return the step whose lines are ``lines``, its item at ``indent``."""
    step = Step(job=job, runs_on=runs_on)
    keys = [" " * (indent + 2) + lines[0].lstrip()[2:], *lines[1:]]
    at = 0
    while at < len(keys):
        line = keys[at]
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or len(line) - len(line.lstrip()) != indent + 2
        ):
            at += 1
            continue
        key, value = _key(stripped)
        raw, end = _block(keys, at, indent + 2)
        body = _dedent(raw)
        if key == "uses":
            step.uses = value
        elif key == "if":
            step.condition = value
        elif key in {"with", "env"}:
            for item in body:
                if item and not item[0].isspace() and ":" in item:
                    name, found = _key(item)
                    (step.inputs if key == "with" else step.env)[name] = found
        elif key == "run":
            text = "\n".join(body) if value[:1] in {"|", ">"} else value
            step.run = " ".join(text.split("\n")) if value[:1] == ">" else text
        at = end if key in {"with", "run", "env"} else at + 1
    return step


def _runners(lines: list[str]) -> dict[str, str]:
    """Return each job's ``runs-on``, wherever in the job it is written."""
    runners = {}
    job = ""
    for line in lines:
        if re.fullmatch(r"  [A-Za-z0-9_-]+:\s*", line):
            job = line.strip()[:-1]
        elif line.startswith("    runs-on:"):
            runners[job] = _key(line.strip())[1]
    return runners


def _steps(text: str) -> list[Step]:
    """Return every step of the workflow, with its job and that job's runner."""
    lines = text.splitlines()
    runners = _runners(lines)
    steps: list[Step] = []
    job = ""
    item: int | None = None
    at = 0
    while at < len(lines):
        line = lines[at]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if not stripped or stripped.startswith("#"):
            at += 1
            continue
        if indent == 2 and re.fullmatch(r"[A-Za-z0-9_-]+:", stripped):
            job, item = stripped[:-1], None
        elif indent == 4 and stripped == "steps:":
            item = -1
        elif item is not None and stripped.startswith("- ") and indent > 4:
            item = indent if item == -1 else item
            if indent == item:
                body, end = _block(lines, at, indent)
                runs_on = runners.get(job, "")
                steps.append(_step([line, *body], job, runs_on, indent))
                at = end
                continue
        elif indent <= 4:
            item = None
        at += 1
    return steps


def _ruff_pin() -> str:
    """Return ruff's version as the ratchets job reads it: the pyproject's pin."""
    text = (REPO_ROOT / "bindings" / "python" / "pyproject.toml").read_text()
    pin = re.search(r'"ruff==([0-9]+\.[0-9]+\.[0-9]+)"', text)
    assert pin, "bindings/python/pyproject.toml no longer pins ruff exactly"
    return pin.group(1)


def _variables(text: str) -> dict[str, str]:
    """Return the values the workflow gives its names, and those set at run time."""
    given = {
        name: value
        for name, value in ASSIGNMENT.findall(text)
        if not value.startswith("${{")
    }
    return {
        **given,
        **RUNTIME_VALUES,
        "GITHUB_WORKSPACE": str(REPO_ROOT),
        "ruff_version": _ruff_pin(),
    }


def _expand(text: str, variables: dict[str, str]) -> str:
    """Return ``text`` with each reference to a name it is given replaced."""

    def value(match: re.Match[str]) -> str:
        name = next(group for group in match.groups() if group)
        return variables.get(name, match.group(0))

    return REFERENCE.sub(value, text)


def _without_prefixes(words: list[str]) -> list[str]:
    """Return ``words`` from the command itself, past any word that only leads in."""
    at = 0
    while at < len(words):
        word = words[at].lstrip("({")
        if word in PREFIXES:
            at += 1
            while at < len(words) and (
                words[at].startswith("-") or re.match(r"^[A-Za-z_]\w*=", words[at])
            ):
                at += 2 if words[at] in PREFIXES[word] else 1
            continue
        if re.match(r"^[A-Za-z_]\w*=", word):
            at += 1
            continue
        break
    command = [w.rstrip(")};") for w in words[at:]]
    if command:
        command[0] = command[0].lstrip("({")
    return [w for w in command if w]


def _commands(run: str, variables: dict[str, str]) -> list[list[str]]:
    """Return every simple command in a ``run`` block, as its words."""
    commands = []
    for line in re.sub(r"\\\n\s*", " ", run).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        expanded = _expand(line, variables)
        for segment in re.split(r"&&|\|\||;|\||\$\(|`", expanded):
            try:
                words = shlex.split(segment, comments=True)
            except ValueError:
                continue
            split = []
            for word in words:
                if word.startswith("--") and "=" in word:
                    split += word.split("=", 1)
                else:
                    split.append(word)
            command = _without_prefixes(split)
            if command:
                commands.append(command)
    return commands


def _values(arguments: list[str], *options: str) -> list[str]:
    """Return the words that follow any of ``options``."""
    return [arguments[i + 1] for i, w in enumerate(arguments[:-1]) if w in options]


def _positionals(arguments: list[str]) -> list[str]:
    """Return the words that are neither an option nor an option's value."""
    positionals = []
    skip = False
    for word in arguments:
        if skip:
            skip = False
        elif word in VALUE_OPTIONS:
            skip = True
        elif not word.startswith("-"):
            positionals.append(word)
    return positionals


def _pinned(requirement: str) -> bool:
    """Return whether a requirement names an exact version or a local path."""
    return bool(EXACT.match(requirement) or LOCAL.match(requirement))


def _file_problem(path: str, *, hashes: bool) -> str | None:
    """Return what keeps a requirements file from pinning every line, or None."""
    resolved = (REPO_ROOT / path).resolve()
    if not resolved.is_relative_to(REPO_ROOT.resolve()) or not resolved.is_file():
        return f"reads {path}, which is not a file of this repository"
    text = re.sub(r"\\\n\s*", " ", resolved.read_text(encoding="utf-8"))
    for raw in text.splitlines():
        line = re.sub(r"\s+#.*$", "", raw).strip()
        if not line or line.startswith("#"):
            continue
        if not REQUIREMENT_LINE.match(line):
            return f"reads {path}, whose line {line!r} names no exact version"
        if hashes and "--hash=sha256:" not in line:
            return f"reads {path}, whose line {line!r} carries no hash"
    return None


def _files_problem(arguments: list[str], *options: str, hashes: bool) -> str | None:
    """Return the first problem with a file any of ``options`` names, or None."""
    for path in _values(arguments, *options):
        if problem := _file_problem(path, hashes=hashes):
            return problem
    return None


def _cargo_install(arguments: list[str]) -> str | None:
    """Judge a ``cargo install``: --locked, and a checked path or exact version."""
    if "--locked" not in arguments:
        return "builds without --locked, so the tool's dependencies float"
    return _cargo_binstall(arguments)


def _cargo_binstall(arguments: list[str]) -> str | None:
    """Judge a ``cargo binstall`` or the version half of a ``cargo install``."""
    versions = _values(arguments, "--version", "--vers")
    versions += [p.split("@", 1)[1] for p in _positionals(arguments) if "@" in p]
    if "--path" in arguments or any(VERSION.match(v.lstrip("=")) for v in versions):
        return None
    return "names neither an exact version nor a checked --path"


def _tool_name(requirement: str) -> str:
    """Return the distribution a requirement or an archive's file name names."""
    name = requirement.split(" @ ", 1)[0] if " @ " in requirement else requirement
    name = re.split(r"[\[=@<>]", name.rsplit("/", 1)[-1], maxsplit=1)[0]
    return re.sub(r"-[0-9].*$", "", name).replace("_", "-").lower()


def _uv_tool(arguments: list[str]) -> str | None:
    """Judge a ``uv tool install``, ``uv tool run`` or ``uvx``."""
    requirements = _values(arguments, "--from") or _positionals(arguments)[:1]
    requirements += _values(arguments, "--with")
    loose = [r for r in requirements if not _pinned(r)]
    if not requirements or loose:
        return f"installs {loose or 'nothing named'}, not an exact version or a path"
    if problem := _files_problem(
        arguments,
        "--constraints",
        "-c",
        "--build-constraints",
        "-b",
        "--with-requirements",
        "--overrides",
        hashes=False,
    ):
        return problem
    tool = requirements[0]
    if LOCAL.match(tool) and _tool_name(tool) not in DEPENDENCY_FREE:
        if not _values(arguments, "--constraints", "-c"):
            return "installs a local archive with no constraints file for what it needs"
        if ".tar.gz" in tool and not _values(arguments, "--build-constraints", "-b"):
            return "builds a source archive with no build-constraints file"
    return None


def _uv_run(arguments: list[str]) -> str | None:
    """Judge a ``uv run``: only what ``--with`` adds is fetched."""
    loose = [r for r in _values(arguments, "--with") if not _pinned(r)]
    if loose:
        return f"adds {loose}, not an exact version or a path"
    return _files_problem(arguments, "--with-requirements", hashes=False)


def _uv_build(arguments: list[str]) -> str | None:
    """Judge a ``uv build``: its build backend is fetched, checked by hash."""
    files = _values(arguments, "--build-constraints", "--build-constraint", "-b")
    if not files or "--require-hashes" not in arguments:
        return "fetches its build backend with no hashed build-constraints file"
    return _files_problem(
        arguments, "--build-constraints", "--build-constraint", "-b", hashes=True
    )


def _uv_sync(arguments: list[str]) -> str | None:
    """Judge a ``uv sync``: without --locked or --frozen it can re-resolve."""
    if {"--locked", "--frozen"} & set(arguments):
        return None
    return "may re-resolve the lockfile: give it --locked"


def _pip_install(arguments: list[str]) -> str | None:
    """Judge a pip install, by pip, pip3, python -m pip or uv pip."""
    hashes = "--require-hashes" in arguments
    if problem := _files_problem(
        arguments, "-r", "--requirement", "-c", "--constraints", hashes=hashes
    ):
        return problem
    loose = [p for p in _positionals(arguments) if not _pinned(p)]
    if loose:
        return f"installs {loose}, not an exact version or a path"
    return None


def _pipx(arguments: list[str]) -> str | None:
    """Judge a ``pipx install`` or ``pipx run``."""
    requirements = _values(arguments, "--spec") or _positionals(arguments)[:1]
    loose = [r for r in requirements if not _pinned(r)]
    if not requirements or loose:
        return f"installs {loose or 'nothing named'}, not an exact version or a path"
    return None


def _npx(arguments: list[str]) -> str | None:
    """Judge an ``npx`` or ``npm exec``: --no runs only what is installed."""
    if {"--no", "--no-install"} & set(arguments):
        return None
    packages = _values(arguments, "--package", "-p") or _positionals(arguments)[:1]
    loose = [p for p in packages if not re.match(r"^@?[^@\s]+@[0-9][\w.+-]*$", p)]
    if not packages or loose:
        return f"fetches {loose or 'nothing named'} at no exact version; use --no"
    return None


def _npm_install(arguments: list[str]) -> str | None:
    """Judge an ``npm install``: npm ci is the locked form."""
    packages = _positionals(arguments)
    loose = [p for p in packages if not re.match(r"^@?[^@\s]+@[0-9][\w.+-]*$", p)]
    if not packages or loose:
        return f"installs {loose or 'from package.json'} at no exact version"
    return None


FORMS: list[tuple[list[str], Callable[[list[str]], str | None]]] = [
    (["cargo", "install"], _cargo_install),
    (["cargo", "binstall"], _cargo_binstall),
    (["uv", "tool", "install"], _uv_tool),
    (["uv", "tool", "run"], _uv_tool),
    (["uvx"], _uv_tool),
    (["uv", "run"], _uv_run),
    (["uv", "build"], _uv_build),
    (["uv", "sync"], _uv_sync),
    (["uv", "pip", "install"], _pip_install),
    (["pipx", "install"], _pipx),
    (["pipx", "run"], _pipx),
    (["npx"], _npx),
    (["npm", "exec"], _npx),
    (["npm", "install"], _npm_install),
    (["npm", "i"], _npm_install),
    (["npm", "add"], _npm_install),
]


def _form(words: list[str]) -> tuple[int, Callable[[list[str]], str | None]] | None:
    """Return how many words name an install form, and the form's rule, or None."""
    for prefix, rule in FORMS:
        if words[: len(prefix)] == prefix:
            return len(prefix), rule
    if PIP.match(words[0]) and words[1:2] == ["install"]:
        return 2, _pip_install
    if PYTHON.match(words[0]) and words[1:4] == ["-m", "pip", "install"]:
        return 4, _pip_install
    return None


def _requirement_words(
    rule: Callable[[list[str]], str | None], arguments: list[str]
) -> list[str]:
    """Return the requirements an install command writes, local builds left out."""
    first = _positionals(arguments)[:1]
    words: dict[Callable[[list[str]], str | None], list[str]] = {
        _uv_tool: (_values(arguments, "--from") or first)
        + _values(arguments, "--with"),
        _uv_run: _values(arguments, "--with"),
        _pip_install: [p for p in _positionals(arguments) if not LOCAL.match(p)],
        _pipx: _values(arguments, "--spec") or first,
        _npx: _values(arguments, "--package", "-p") or first,
        _npm_install: _positionals(arguments),
        _cargo_install: _positionals(arguments),
        _cargo_binstall: _positionals(arguments),
    }
    return words.get(rule, [])


def _npm_name(spec: str) -> str:
    """Return the package an npm spec names, scope kept and version dropped."""
    scope = "@" if spec.startswith("@") else ""
    return scope + spec[len(scope) :].split("@", 1)[0]


def _tools(words: list[str]) -> set[str]:
    """Return the names of the tools an install command fetches."""
    form = _form(words)
    if form is None or not _fetches(words):
        return set()
    length, rule = form
    arguments = words[length:]
    name = _npm_name if rule in {_npx, _npm_install} else _tool_name
    tools = {name(word) for word in _requirement_words(rule, arguments)}
    files = {
        _uv_tool: ("--with-requirements",),
        _uv_run: ("--with-requirements",),
        _uv_build: ("--build-constraints", "--build-constraint", "-b"),
        _pip_install: ("-r", "--requirement"),
    }.get(rule, ())
    tools |= {Path(path).name.split(".", 1)[0] for path in _values(arguments, *files)}
    if rule is _cargo_install:
        tools |= {
            Path(path).name.removesuffix("-src")
            for path in _values(arguments, "--path")
        }
    return tools


def _judged(run: str, variables: dict[str, str]) -> list[tuple[list[str], str | None]]:
    """Return each install command in ``run``, with why it floats or None."""
    found = []
    for words in _commands(run, variables):
        if form := _form(words):
            length, rule = form
            found.append((words, rule(words[length:])))
    return found


def _installs(text: str) -> list[tuple[list[str], str | None]]:
    """Return every install command in the workflow, with why it floats or None."""
    variables = _variables(text)
    return [found for step in _steps(text) for found in _judged(step.run, variables)]


def _run_problems(text: str) -> list[str]:
    """Return each install in the workflow that floats without a declared reason."""
    declared = {requirements for requirements, _ in _declarations(text).floats}
    used: set[frozenset[str]] = set()
    problems = []
    for words, why in _installs(text):
        form = _form(words)
        if why is None or form is None:
            continue
        length, rule = form
        requirements = frozenset(_requirement_words(rule, words[length:]))
        if requirements in declared:
            used.add(requirements)
            continue
        problems.append(f"`{' '.join(words)}` {why}")
    problems += [
        f"`# floats: {' '.join(sorted(requirements))}` matches no install"
        for requirements in sorted(declared - used, key=sorted)
    ]
    return problems


def _fetches(words: list[str]) -> bool:
    """Return whether an install command fetches anything at all.

    ``uv sync`` and a ``uv run`` with nothing added install only what the
    lockfile already pins.
    """
    if words[:2] == ["uv", "sync"]:
        return False
    return words[:2] != ["uv", "run"] or bool(
        {"--with", "--with-requirements"} & set(words)
    )


def _inventory_problems(name: str, text: str) -> list[str]:
    """Return each tool the workflow fetches unlike it declares, or REQUIRED_TOOLS.

    A floating install answers to its ``floats`` declaration, so only the
    pinned ones are counted here.
    """
    declared = _declarations(text)
    problems = list(declared.problems)
    fetched: dict[str, int] = {}
    for words, why in _installs(text):
        if why is None:
            for tool in _tools(words):
                fetched[tool] = fetched.get(tool, 0) + 1
    for tool in sorted(set(fetched) | set(declared.pins)):
        found, count = fetched.get(tool, 0), declared.pins.get(tool, 0)
        if found != count:
            problems.append(f"{tool} is fetched by {found} installs, declared {count}")
    for tool, count in REQUIRED_TOOLS.get(name, {}).items():
        if fetched.get(tool, 0) != count:
            problems.append(
                f"{tool} is fetched by {fetched.get(tool, 0)} installs; "
                f"REQUIRED_TOOLS wants {count}"
            )
    return problems


def _tie_problem(step: Step, digest: str, runners: dict[str, set[str]]) -> str | None:
    """Return why ``step`` may run where ``digest`` is not its platform's, or None."""
    platform = PLATFORM_DIGESTS[digest]
    if step.runs_on in runners[platform]:
        return None
    guarded = re.search(
        rf"runner\.os\s*==\s*'{platform}'", step.condition
    ) and re.search(r"runner\.arch\s*==\s*'X64'", step.condition)
    if guarded:
        return None
    return (
        f"job {step.job} reads {digest}, the x86-64 {platform} digest, on runner "
        f"{step.runs_on!r} with no `if: runner.os == '{platform}' && runner.arch "
        "== 'X64'`"
    )


def _setup_uv_problems(step: Step, variables: dict[str, str]) -> list[str]:
    """Return what a setup-uv step leaves unnamed."""
    problems = []
    version = _expand(step.inputs.get("version", ""), variables)
    checksum = step.inputs.get("checksum", "")
    named = ENV_REFERENCE.match(checksum)
    if not VERSION.match(version):
        problems.append(f"job {step.job}'s setup-uv names uv {version!r}")
    if not (
        named
        and named.group(1) in PLATFORM_DIGESTS
        and SHA256.match(_expand(checksum, variables))
    ):
        problems.append(
            f"job {step.job}'s setup-uv checksum is {checksum!r}, not a "
            "platform's digest named in the env block"
        )
    return problems


def _action_problems(text: str) -> list[str]:
    """Return each tool an action downloads at no exact version, or off its platform."""
    variables = _variables(text)
    runners = {platform: set(labels) for platform, labels in PLATFORM_RUNNERS.items()}
    for label, platform in _declarations(text).runners.items():
        runners[platform].add(label)
    problems = []
    for step in _steps(text):
        read = set(re.findall(r"\b(\w+_SHA256\w*)\b", step.run))
        read |= {
            m.group(1) for v in step.inputs.values() if (m := ENV_REFERENCE.match(v))
        }
        problems += [
            problem
            for digest in sorted(read & set(PLATFORM_DIGESTS))
            if (problem := _tie_problem(step, digest, runners))
        ]
        if step.uses.startswith("astral-sh/setup-uv@"):
            problems += _setup_uv_problems(step, variables)
        if step.uses.startswith("PyO3/maturin-action@"):
            version = _expand(step.inputs.get("maturin-version", ""), variables)
            if not VERSION.match(version):
                problems.append(f"job {step.job}'s maturin-action names {version!r}")
    return problems


def _uv_versions(text: str) -> set[str]:
    """Return the uv versions the workflow's setup-uv steps name."""
    variables = _variables(text)
    return {
        _expand(step.inputs.get("version", ""), variables)
        for step in _steps(text)
        if step.uses.startswith("astral-sh/setup-uv@")
    }


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_the_workflows_that_build_what_ships_are_found() -> None:
    """REQUIRED_TOOLS holds workflows the glob finds, so its check cannot lapse."""
    assert set(REQUIRED_TOOLS) <= set(WORKFLOW_NAMES), (
        f"REQUIRED_TOOLS names {sorted(REQUIRED_TOOLS)}; .github/workflows/ holds "
        f"{WORKFLOW_NAMES}."
    )


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_each_workflow_fetches_the_tools_it_declares(name: str) -> None:
    """A workflow fetches what its `# pins:` lines say: no more, no fewer, no other."""
    problems = _inventory_problems(name, _read(name))
    assert problems == [], (
        f".github/workflows/{name}: "
        + "; ".join(problems)
        + ". Pin the install back, or change the workflow's `# pins:` lines with "
        "the install."
    )


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_no_install_in_a_workflow_floats(name: str) -> None:
    """No install takes whatever release is newest, unless the workflow says why."""
    problems = _run_problems(_read(name))
    assert problems == [], (
        f".github/workflows/{name}: "
        + "; ".join(problems)
        + ". Pin it to the version its last passing run used, with the digest of "
        "what it downloads where the installer can check one, as the Rust Crate "
        "Notices job in CI.yml pins cargo-about."
    )


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_every_downloaded_tool_is_named_for_its_platform(name: str) -> None:
    """Each setup-uv names a uv and its platform's digest; maturin-action, a maturin."""
    problems = _action_problems(_read(name))
    assert problems == [], (
        f".github/workflows/{name}: "
        + "; ".join(problems)
        + ". Name each version exactly, and each digest through an env name "
        "PLATFORM_DIGESTS gives, on a runner of its platform, which the workflow "
        "declares with `# runner:` if the tests do not know it, or behind an `if`."
    )


def test_the_workflows_name_one_uv() -> None:
    """Every workflow that installs uv names one release, with one digest a platform."""
    named = {
        name: sorted(versions)
        for name in WORKFLOW_NAMES
        if (versions := _uv_versions(_read(name)))
    }
    assert "CI.yml" in named, "CI.yml's setup-uv steps are no longer read"
    releases = {version for versions in named.values() for version in versions}
    assert len(releases) == 1, (
        f"the workflows name uv {named}. Name one release in every workflow's "
        "env block, and move them together."
    )
    for digest in sorted(PLATFORM_DIGESTS):
        if not digest.startswith("SETUP_UV_"):
            continue
        values = {
            name: value
            for name in named
            if (value := _variables(_read(name)).get(digest))
        }
        assert len(set(values.values())) <= 1, (
            f"the workflows give {digest} {values}: one release has one digest "
            "a platform, so give them all the same."
        )


# A command in each form the rules read, and whether it takes whatever release
# is newest. Every floating form here went unseen, or passed, before the rules
# learned it.
COMMANDS = [
    ("npx jscpd .", True),
    ("npx --yes jscpd@5.1.2 .", False),
    ("npx --no playwright install", False),
    ("npm exec -- eslint .", True),
    ("npm i -g foo", True),
    ("npm install -g foo@1.2.3", False),
    ("npm install", True),
    ("pip3 install foo", True),
    ("python -m pip install foo", True),
    ("python3 -m pip install foo==1.0", False),
    (".venv/bin/python -m pip install -r /tmp/requirements.txt", True),
    ("pipx install foo", True),
    ("pipx install foo==1.0", False),
    ("pipx run foo", True),
    ("pipx run --spec foo==1.0 foo", False),
    ("uv run --with foo pytest", True),
    ("uv run --with=foo==1.0 pytest", False),
    ("uv run --with-requirements /tmp/r.txt pytest", True),
    ("uv run pytest", False),
    ("cargo binstall foo", True),
    ("cargo binstall foo@1.2.3", False),
    ("if true; then uvx foo; fi", True),
    ("for x in a; do uvx foo; done", True),
    ("sudo -E pip install foo", True),
    ("sudo -u root pip install foo", True),
    ("env A=1 uvx foo", True),
    ("x=$(uvx foo --version)", True),
    ("uvx --with=foo --from bar==1.0 bar", True),
    ("uvx --from=bar==1.0 bar", False),
    ("uvx --with-requirements /tmp/r.txt --from bar==1.0 bar", True),
    ("uvx --from /tmp/twine-7.0.0-py3-none-any.whl twine check", True),
    (
        (
            "uvx --from /tmp/twine-7.0.0-py3-none-any.whl "
            "--constraints .github/pins/twine.txt twine check"
        ),
        False,
    ),
    ("uv tool install /tmp/reuse-6.2.0.tar.gz", True),
    (
        "uv tool install /tmp/reuse-6.2.0.tar.gz --constraints .github/pins/reuse.txt",
        True,
    ),
    (
        (
            "uv tool install 'reuse[charset-normalizer] @ "
            "file:///tmp/reuse-6.2.0.tar.gz' --constraints .github/pins/reuse.txt "
            "--build-constraints .github/pins/reuse-build.txt"
        ),
        False,
    ),
    ("uvx --from /tmp/maturin-1.15.0-py3-none-any.whl maturin build", False),
    ("uv build --no-sources --out-dir dist engines/jax", True),
    (
        "uv build --build-constraints .github/pins/hatchling.txt --require-hashes .",
        False,
    ),
    ("uv build --build-constraints .github/pins/twine.txt --require-hashes .", True),
    ("uv sync", True),
    ("uv sync --locked", False),
]


@pytest.mark.parametrize(("command", "floats"), COMMANDS)
def test_each_install_form_is_read(command: str, *, floats: bool) -> None:
    """The rules see every form above, wherever the command sits in a line."""
    judged = _judged(command, _variables(""))
    assert judged, f"{command!r}: no install command found"
    assert any(why is not None for _, why in judged) is floats, (command, judged)


@pytest.mark.parametrize(
    ("tool", "line"),
    [
        ("maturin", 'uvx --from "/tmp/${MATURIN_WHEEL}" maturin build'),
        ("twine", 'uvx --from "/tmp/${TWINE_WHEEL}" --constraints'),
        ("hatchling", "uv build --no-sources --build-constraints"),
    ],
)
def test_deleting_a_pinned_install_fails_the_inventory(tool: str, line: str) -> None:
    """Without one of CI.yml's pinned installs, the inventory says which.

    It fails whether or not the install's `# pins:` line goes with it: CI.yml
    builds and checks what ships, so REQUIRED_TOOLS holds it to its tools too.
    """
    rows = _read("CI.yml").splitlines()
    kept = [row for row in rows if line not in row]
    assert len(kept) < len(rows), f"CI.yml has no line with {line!r}"
    problems = _inventory_problems("CI.yml", "\n".join(kept))
    assert any(problem.startswith(f"{tool} ") for problem in problems), problems
    undeclared = [row for row in kept if not row.startswith(f"# pins: {tool} ")]
    problems = _inventory_problems("CI.yml", "\n".join(undeclared))
    assert any("REQUIRED_TOOLS" in p for p in problems), problems


SETUP_UV = """
env:
  SETUP_UV_VERSION: "0.12.22"
  SETUP_UV_SHA256: {digest}
jobs:
  build:
    runs-on: {runner}
    steps:
      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78   # v7
        {condition}
        with:
          version: ${{{{ env.SETUP_UV_VERSION }}}}
          checksum: ${{{{ env.SETUP_UV_SHA256 }}}}
"""


@pytest.mark.parametrize(
    ("runner", "condition", "tied"),
    [
        ("ubuntu-latest", "", True),
        ("linux-x64-large", "", False),
        ("windows-latest", "", False),
        ("macos-latest", "", False),
        ("${{ matrix.runner }}", "", False),
        (
            "${{ matrix.runner }}",
            "if: runner.os == 'Linux' && runner.arch == 'X64'",
            True,
        ),
        ("${{ matrix.runner }}", "if: runner.os == 'Linux'", False),
    ],
)
def test_the_linux_digest_is_read_only_on_linux(
    runner: str, condition: str, *, tied: bool
) -> None:
    """The x86-64 Linux digest of uv, read on another runner, fails."""
    text = SETUP_UV.format(digest="a" * 64, runner=runner, condition=condition)
    problems = _action_problems(text)
    assert (problems == []) is tied, problems


def test_reuse_detects_encodings_without_libmagic() -> None:
    """The licence check's verdict does not depend on the runner's libmagic.

    reuse detects each file's encoding with python-magic first, which needs
    the system's libmagic, and refuses to lint at all where neither it nor
    another detector loads. With its charset-normalizer extra installed and
    REUSE_ENCODING_MODULE naming it, the lint reads the same everywhere.
    """
    steps = _steps(_read("licence-check.yml"))
    lints = [step for step in steps if step.run.strip() == "reuse lint"]
    installs = [step for step in steps if "uv tool install" in step.run]
    pins = REPO_ROOT / ".github" / "pins" / "reuse.txt"
    assert lints, "licence-check.yml no longer runs `reuse lint`"
    assert all(
        s.env.get("REUSE_ENCODING_MODULE") == "charset_normalizer" for s in lints
    )
    assert installs, "licence-check.yml no longer installs reuse"
    assert all("reuse[charset-normalizer] @ " in step.run for step in installs)
    assert pins.is_file(), ".github/pins/reuse.txt is missing"
    assert re.search(r"^charset-normalizer==", pins.read_text(), re.MULTILINE)


DECLARED = """
{declarations}
env:
  SETUP_UV_VERSION: "0.12.22"
  SETUP_UV_SHA256: {digest}
jobs:
  check:
    runs-on: {runner}
    steps:
      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78   # v7
        with:
          version: ${{{{ env.SETUP_UV_VERSION }}}}
          checksum: ${{{{ env.SETUP_UV_SHA256 }}}}
      - run: {command}
"""


@pytest.mark.parametrize(
    ("declarations", "command", "problems"),
    [
        # Kept: the one install, declared once.
        ("# pins: ruff 1", "uvx ruff@0.16.3 check .", 0),
        # An install the workflow does not declare.
        ("", "uvx ruff@0.16.3 check .", 1),
        # A declaration with no install behind it.
        ("# pins: ruff 1\n# pins: twine 1", "uvx ruff@0.16.3 check .", 1),
        # A count the workflow does not keep.
        ("# pins: ruff 2", "uvx ruff@0.16.3 check .", 1),
        # Lines in no form the tests read.
        ("# pins: ruff\n# pins: ruff 1", "uvx ruff@0.16.3 check .", 1),
        ("# pins: ruff 1\n# pins: ruff 1", "uvx ruff@0.16.3 check .", 1),
        ("# pins: ruff 1\n# runner: big-box", "uvx ruff@0.16.3 check .", 1),
        ("# pins: ruff 1\n# floats: foo", "uvx ruff@0.16.3 check .", 1),
    ],
)
def test_a_declaration_fails_closed(
    declarations: str, command: str, problems: int
) -> None:
    """A tool fetched or declared without the other, or a line in no form, fails."""
    text = DECLARED.format(
        declarations=declarations,
        digest="a" * 64,
        runner="ubuntu-latest",
        command=command,
    )
    assert len(_inventory_problems("a-workflow.yml", text)) == problems, (
        _inventory_problems("a-workflow.yml", text)
    )


@pytest.mark.parametrize(
    ("declarations", "command", "problems"),
    [
        (
            "# floats: jax jaxlib -- the newest JAX on purpose",
            "pip install jax jaxlib",
            0,
        ),
        ("", "pip install jax jaxlib", 1),
        # A float declared for an install the workflow does not make.
        ("# floats: jax -- the newest JAX on purpose", "pip install jax==0.9.0", 1),
        # A float declares the whole install, not part of it.
        ("# floats: jax -- the newest JAX on purpose", "pip install jax jaxlib", 2),
    ],
)
def test_a_float_is_accepted_only_as_declared(
    declarations: str, command: str, problems: int
) -> None:
    """An install that takes the newest release passes only where a float names it."""
    text = DECLARED.format(
        declarations=declarations,
        digest="a" * 64,
        runner="ubuntu-latest",
        command=command,
    )
    assert len(_run_problems(text)) == problems, _run_problems(text)


@pytest.mark.parametrize(
    ("declarations", "tied"),
    [
        ("", False),
        ("# runner: linux-x64-large x86-64 Linux", True),
        ("# runner: linux-x64-large x86-64 Windows", False),
    ],
)
def test_a_declared_runner_carries_its_platform(
    declarations: str, *, tied: bool
) -> None:
    """A runner the tests do not know reads the Linux digest only if declared Linux."""
    text = DECLARED.format(
        declarations=declarations,
        digest="a" * 64,
        runner="linux-x64-large",
        command="uv sync --locked",
    )
    assert (_action_problems(text) == []) is tied, _action_problems(text)
