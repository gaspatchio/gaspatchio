# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The three distributions this repository publishes, held to each other.

One tag publishes ``gaspatchio``, ``gaspatchio-jax`` and ``gaspatchio-viewer``
together, and each names another by an exact version: the core's ``jax`` and
``viewer`` extras pin the engine and the viewer, and the engine pins the core it
is qualified against. A pin that disagrees with the version it names is an
install that cannot resolve, and it is found by the first person to install
after the tag, when it can no longer be fixed without a new release.

**The lockfiles cannot see it.** Each resolves the other projects from this
checkout through a ``[tool.uv.sources]`` path, and uv ignores a version
specifier when a path source supplies the package: an engine pinning
``gaspatchio==0.8.0`` against a 0.9.0 core locks cleanly and ``uv lock
--check`` passes. So the pins are compared here, where a version bump that moved
one side and not the other fails before anything is built.

Held beside them, because a half-done bump breaks them the same way: each
package's ``__version__`` against its own metadata, and each crate the core's
extension is built from against the core's own version. And the licence texts
each wheel carries, against the repository's ``LICENSES/``, and each licence
expression against the notices of what the wheel carries.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE = REPO_ROOT / "bindings" / "python"
ENGINE = REPO_ROOT / "engines" / "jax"
VIEWER = REPO_ROOT / "viewer" / "python"

# The core's source distribution ships this directory and neither of the other
# two projects, so a run from an unpacked sdist has nothing to compare. Inside a
# checkout the same absence is the fault, so the guard is keyed on the checkout
# rather than on the files -- the reasoning test_ratchet_documents_agree.py
# gives for its own guard.
pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="not a repository checkout; the core's sdist ships no engines/ or viewer/",
)


def _project(root: Path) -> dict[str, Any]:
    """Return the ``[project]`` table of the pyproject.toml under ``root``."""
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    table: dict[str, Any] = document["project"]
    return table


def _exact_pins(requirements: list[str], name: str) -> list[str]:
    """Return the versions ``requirements`` pins ``name`` to with ``==``.

    Anything else that names the package -- a range, a marker, an extra -- is
    returned as its whole requirement string, so that the assertion prints it
    rather than passing over it.
    """
    pins = []
    for text in requirements:
        requirement = Requirement(text)
        if requirement.name != name:
            continue
        specifiers = list(requirement.specifier)
        is_exact = (
            len(specifiers) == 1
            and specifiers[0].operator == "=="
            and not requirement.extras
            and requirement.marker is None
        )
        pins.append(specifiers[0].version if is_exact else text)
    return pins


def _declared_dunder_version(module: Path) -> str:
    """Return the string a module assigns to ``__version__``, read without import."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in statement.targets
            )
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            return statement.value.value
    message = f"{module} assigns no string to __version__"
    raise AssertionError(message)


def test_the_engine_requires_exactly_the_core_version() -> None:
    """``gaspatchio-jax`` pins ``gaspatchio`` to the version the core declares."""
    core_version = _project(CORE)["version"]
    pins = _exact_pins(_project(ENGINE)["dependencies"], "gaspatchio")
    assert pins == [core_version], (
        f"engines/jax/pyproject.toml requires gaspatchio as {pins!r}; the core "
        f"is {core_version!r}. The engine is qualified against one core release "
        "and requires it exactly -- move the pin with the core's version, in the "
        "same commit, and relock both projects."
    )


@pytest.mark.parametrize(
    ("extra", "distribution", "root"),
    [
        ("jax", "gaspatchio-jax", ENGINE),
        ("viewer", "gaspatchio-viewer", VIEWER),
    ],
)
def test_each_extra_pins_exactly_its_distribution(
    extra: str, distribution: str, root: Path
) -> None:
    """``gaspatchio[<extra>]`` is one exact pin, on the version the project holds."""
    declared = _project(CORE)["optional-dependencies"][extra]
    version = _project(root)["version"]
    assert _exact_pins(declared, distribution) == [version], (
        f"gaspatchio[{extra}] is {declared!r}; {root.relative_to(REPO_ROOT)} is "
        f"{distribution} {version!r}. The extra pins the release it was "
        "qualified with, exactly."
    )
    assert len(declared) == 1, (
        f"gaspatchio[{extra}] should install {distribution} and nothing else "
        f"beside it; it declares {declared!r}."
    )


@pytest.mark.parametrize(
    ("root", "module"),
    [
        (ENGINE, ENGINE / "src" / "gaspatchio_jax" / "__init__.py"),
        (VIEWER, VIEWER / "gaspatchio_viewer" / "__init__.py"),
    ],
)
def test_each_package_states_the_version_its_metadata_does(
    root: Path, module: Path
) -> None:
    """A package's ``__version__`` is the version its distribution is built as."""
    version = _project(root)["version"]
    stated = _declared_dunder_version(module)
    assert stated == version, (
        f"{module.relative_to(REPO_ROOT)} says __version__ = {stated!r} and "
        f"{(root / 'pyproject.toml').relative_to(REPO_ROOT)} builds {version!r}."
    )


def _cargo(manifest: Path) -> dict[str, Any]:
    """Return a Cargo manifest, parsed."""
    document: dict[str, Any] = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return document


def _workspace_crates() -> list[Path]:
    """Return the manifest of every crate the repository's Cargo workspace builds."""
    members = _cargo(REPO_ROOT / "Cargo.toml")["workspace"]["members"]
    return [REPO_ROOT / member / "Cargo.toml" for member in members]


def _crate_version(manifest: Path) -> str:
    """Return a crate's own version, or the workspace's where the crate inherits it."""
    version = _cargo(manifest)["package"]["version"]
    if isinstance(version, dict) and version.get("workspace") is True:
        inherited = _cargo(REPO_ROOT / "Cargo.toml")["workspace"]["package"]
        return str(inherited["version"])
    return str(version)


def test_every_crate_is_versioned_as_the_core_it_is_built_into() -> None:
    """Each first-party crate states the version the core's distribution is built as.

    The bindings crate's version is compiled into the extension: it is what
    ``gaspatchio._internal.__version__`` returns, and the ``core_version`` a
    results manifest and ``last_run.versions`` state. The wheel is built as
    the version the core's pyproject.toml states. A release that bumps one
    and not the other publishes a core whose results name a version it was
    never published as, and nothing at build time says so.

    The two are compared as versions, not as text: a pre-release is spelled
    one way by each standard -- ``1.0.0rc1`` in PEP 440, ``1.0.0-rc.1`` in
    SemVer, which Cargo requires -- and PEP 440 reads both as one version.
    """
    project = CORE / "pyproject.toml"
    stated = _project(CORE)["version"]
    crates = _workspace_crates()
    assert CORE / "Cargo.toml" in crates, (
        "the Cargo workspace no longer builds bindings/python, whose version "
        "the extension is compiled with"
    )
    apart = [
        f"{manifest.relative_to(REPO_ROOT)} says version = {version!r} and "
        f"{project.relative_to(REPO_ROOT)} says version = {stated!r}"
        for manifest in crates
        if Version(version := _crate_version(manifest)) != Version(stated)
    ]
    assert apart == [], (
        "; ".join(apart) + ". The crates are compiled into the core's extension, "
        "whose version is the core_version every result states, so bump each "
        "crate's version and the pyproject's together."
    )


@pytest.mark.parametrize("root", [CORE, ENGINE, VIEWER])
def test_each_wheel_carries_the_repository_licence_texts(root: Path) -> None:
    """The texts a wheel ships are the repository's, byte for byte.

    PEP 639 takes ``license-files`` from inside the project directory, so each
    project holds copies of the texts it ships -- from ``LICENSES/``, and the
    core's NOTICE. A copy that drifted from the repository's would put a
    licence in the wheel that the repository never granted. An entry with no
    counterpart at the repository root -- the viewer's generated third-party
    notices -- only has to exist.
    """
    listed = _project(root)["license-files"]
    assert listed, f"{root.relative_to(REPO_ROOT)} ships no licence text"
    for relative in listed:
        copy = root / relative
        assert copy.is_file(), f"{copy.relative_to(REPO_ROOT)} is listed but absent"
        original = REPO_ROOT / relative
        if Path(relative).parent != Path("LICENSES") and not original.is_file():
            continue
        assert original.is_file(), (
            f"{copy.relative_to(REPO_ROOT)} has no counterpart in LICENSES/"
        )
        assert copy.read_bytes() == original.read_bytes(), (
            f"{copy.relative_to(REPO_ROOT)} differs from "
            f"{original.relative_to(REPO_ROOT)}; copy the repository's text back "
            "over it."
        )


def test_the_viewer_states_every_licence_its_assets_carry() -> None:
    """The viewer's ``License-Expression`` covers each built asset's SPDX header.

    viewer/build.mjs writes each asset's header from the packages esbuild
    bundled into it, so a dependency under a new licence changes a header; the
    wheel's own expression has to follow, and it needs that licence's text.
    """
    expression = _project(VIEWER)["license"]
    declared = set(expression.split(" AND "))
    listed = {Path(entry).stem for entry in _project(VIEWER)["license-files"]}
    tag = "SPDX-License" + "-Identifier: "
    assets = VIEWER / "gaspatchio_viewer" / "assets"
    for asset in (assets / name for name in ("viewer.js", "viewer.css", "fonts.css")):
        header = asset.read_text(encoding="utf-8")[:1024]
        found = [line.split(tag, 1)[1] for line in header.splitlines() if tag in line]
        assert found, f"{asset.relative_to(REPO_ROOT)} carries no SPDX header"
        carried = set(found[0].strip().split(" AND "))
        assert carried <= declared, (
            f"{asset.relative_to(REPO_ROOT)} carries {sorted(carried - declared)}, "
            f"which viewer/python/pyproject.toml's license = {expression!r} omits."
        )
        assert carried <= listed, (
            f"{asset.relative_to(REPO_ROOT)} carries {sorted(carried - listed)} "
            "with no text in viewer/python/pyproject.toml's license-files."
        )


def _rust_notices() -> ModuleType:
    """Return scripts/rust_notices.py, which writes and reads the core's notices."""
    path = REPO_ROOT / "scripts" / "rust_notices.py"
    spec = importlib.util.spec_from_file_location("rust_notices", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: its dataclasses look their module up by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_core_states_every_licence_its_notices_carry() -> None:
    """The core's ``License-Expression`` is exactly what its wheel carries.

    Its own Apache-2.0, MIT for the Level 4 tutorial's lifelib data, and every
    licence third-party-notices.txt takes a linked Rust crate under -- read
    from the file itself, which scripts/rust_notices.py writes from Cargo.lock
    and CI holds to what the extension links. A crate that brings a new
    licence changes the notices, and this fails until the expression, the
    licence's text in ``license-files`` and REUSE.toml's annotation of the
    notices follow. Exact rather than a superset, so a licence that stopped
    being carried leaves the expression too.
    """
    project = _project(CORE)
    expression = project["license"]
    declared = set(expression.split(" AND "))
    notices = (CORE / "third-party-notices.txt").read_text(encoding="utf-8")
    named = _rust_notices().licences_named(notices)

    assert declared == named | {"Apache-2.0", "MIT"}, (
        f"bindings/python/pyproject.toml's license = {expression!r}; the notices "
        f"take crates under {sorted(named)}, beside the core's own Apache-2.0 and "
        "the tutorial data's MIT."
    )
    texts = {
        Path(entry).stem
        for entry in project["license-files"]
        if Path(entry).parent == Path("LICENSES")
    }
    assert texts == declared, (
        f"license-files carries texts for {sorted(texts)}; the expression names "
        f"{sorted(declared)}. Copy each missing text from LICENSES/ and list it."
    )
    assert "third-party-notices.txt" in project["license-files"]

    reuse = tomllib.loads((REPO_ROOT / "REUSE.toml").read_text(encoding="utf-8"))
    annotated = [
        annotation["SPDX-License-Identifier"]
        for annotation in reuse["annotations"]
        if "bindings/python/third-party-notices.txt" in annotation["path"]
    ]
    assert annotated == [expression], (
        "REUSE.toml annotates bindings/python/third-party-notices.txt with "
        f"{annotated}; it holds material under the core's expression, {expression!r}."
    )
