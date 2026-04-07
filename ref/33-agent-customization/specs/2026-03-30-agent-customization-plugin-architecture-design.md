# Agent-Driven Customization & Plugin Architecture

**Date**: 2026-03-30
**Status**: Draft
**Branch**: `cursor/agent-customization-plugin-arch`

## Problem

Gaspatchio already has the right low-level primitives for customization:

- Dynamic Python accessor registration for `ActuarialFrame`, `ColumnProxy`, and `ExpressionProxy`
- Rust-backed Polars plugins for performance-critical operations
- A codebase structure that separates ergonomic Python APIs from native kernels

But the current customization story is not productized.

Today:

- Python accessor extension works mainly through import-time decorator side effects
- Reference docs describe entry-point discovery that is not implemented
- Rust-backed custom operations are possible only by editing this repo and rebuilding the bundled `_internal` library
- There is no first-class plugin manifest, compatibility contract, or CLI workflow for agents to scaffold, validate, benchmark, and distribute custom extensions

This creates a gap between what the architecture can do internally and what external users, teams, and agents can do reliably.

## Goal

Make Gaspatchio highly customizable by agents and advanced users without sacrificing Rust performance.

Specifically:

1. Support installable Python accessor plugins as a first-class extension model
2. Support external native plugins that preserve Rust/Polars performance without recompiling Gaspatchio itself
3. Give agents a stable workflow for discovering, scaffolding, validating, and benchmarking plugins
4. Preserve the "formula is the code" philosophy by preferring expression composition first and native code only for hot paths

## Non-Goals

- Do not replace the existing built-in accessor registry or bundled `_internal` library
- Do not require every user to install the Rust toolchain
- Do not introduce a fully sandboxed runtime such as WASM in v1
- Do not turn Gaspatchio into a general-purpose application plugin marketplace before the core extension APIs stabilize

## Current State

### What Exists

#### 1. Python accessor registry

`register_accessor(name, kind="column"|"frame")` populates a module-level registry that is consulted by:

- `ActuarialFrame.__getattr__`
- `ColumnProxy.__getattr__`
- `ExpressionProxy.__getattr__`

Built-in accessors are imported for registration side effects.

This is already a good abstraction for user-defined namespaces such as:

- `af.reporting`
- `af.claims.risk`
- `af.reserve.ifrs17`

#### 2. Rust-backed Polars plugin functions

Performance-critical functions are implemented in Rust with `#[polars_expr]` and invoked from Python using `polars.plugins.register_plugin_function(...)`.

The current wrappers always point `plugin_path` at the bundled `gaspatchio_core._internal` shared library.

This means the runtime already uses a plugin boundary, but only for the bundled native library.

#### 3. Good architectural separation

The codebase is already organized in a way that supports extension:

- `core/`: Rust algorithms and registries
- `bindings/python/src/`: PyO3 and Polars plugin glue
- `bindings/python/gaspatchio_core/`: user-facing Python API and accessors

### What Is Missing

#### 1. Entry-point discovery is documented but not implemented

`ref/07-dsl-namespacing/07-plugins.md` describes automatic discovery via the `gaspatchio.accessors` entry-point group, but the current package imports built-in accessors directly rather than loading external entry points.

#### 2. No supported external native plugin model

There is no public API for a third-party package to:

- ship its own compiled native library
- expose `#[polars_expr]` functions
- register those functions with Gaspatchio through a stable Python wrapper

#### 3. No plugin metadata or compatibility story

There is no standard way to declare:

- plugin type
- supported Gaspatchio version range
- supported Polars version
- required Python version
- whether native code is included

#### 4. No agent-focused authoring workflow

Agents currently have to infer:

- where to put plugin code
- how to structure packaging
- how to validate compatibility
- when a Python accessor is sufficient vs when native code is justified

## Design Principles

### 1. Democratize customization

The default extension path should be accessible to teams who are comfortable in Python but do not want to maintain a Gaspatchio fork.

### 2. Keep performance optional but available

Most customization should start as Python-level expression composition. Native code should be available as an optimization path, not a prerequisite.

### 3. Prefer installable plugins over forks

Customization should primarily happen in separately installable packages, not long-lived downstream forks of this repository.

### 4. Optimize for agent success

The extension model should be easy to:

- discover
- scaffold
- validate
- benchmark
- explain

### 5. Make compatibility explicit

Native extensions are powerful but fragile if version drift is hidden. Compatibility must be machine-readable and checked at import time.

## Proposed Extension Model

Gaspatchio should support three customization lanes.

## Lane A: Python Accessor Plugins

This is the primary extension model.

### Capabilities

Python accessor plugins can add:

- frame-level namespaces like `af.reporting`, `af.audit`, `af.solvency`
- column/expression namespaces like `af.claims.risk`, `af.date.my_company`
- reusable domain logic built from existing Gaspatchio and Polars expressions
- CLI helpers and examples packaged alongside the plugin

### Registration Models

Support both:

1. **Decorator registration** for in-repo or application-local accessors
2. **Entry-point discovery** for installable plugin packages

### Entry Point Contract

Use Python entry points:

- **Group**: `gaspatchio.accessors`
- **Name format**: `{kind}.{name}`
  - `kind` is `frame` or `column`
  - `name` is the namespace exposed to the user
- **Value**: `<module>:<class>`

Example:

```toml
[project.entry-points."gaspatchio.accessors"]
column.risk = "my_company_gspio_plugin.accessors:RiskAccessor"
frame.reporting = "my_company_gspio_plugin.reporting:ReportingAccessor"
```

### Runtime Behavior

On import of `gaspatchio_core`, a discovery function should:

1. Scan the `gaspatchio.accessors` entry-point group
2. Parse names into `(kind, accessor_name)`
3. Import the target class
4. Register it into `_ACCESSOR_REGISTRY`
5. Record plugin metadata for inspection through a public API and CLI

### API Sketch

```python
from importlib.metadata import entry_points

def discover_accessors() -> None:
    for ep in entry_points(group="gaspatchio.accessors"):
        kind, name = ep.name.split(".", 1)
        cls = ep.load()
        register_accessor(name, kind=kind)(cls)
```

### Why this matters

This is the fastest path to democratized customization. It lets an agent create a pip-installable package that adds new namespaces without patching this repo.

## Lane B: Native Plugin Packages

This is the optimization path for hot custom logic.

### Capability

A native plugin package ships:

- Python wrapper code
- a compiled shared library containing `#[polars_expr]` exports
- accessor methods or top-level helper functions that call `register_plugin_function(...)` with the plugin's own `plugin_path`

This allows custom Rust-backed operations without rebuilding `gaspatchio_core._internal`.

### Key Design Decision

Gaspatchio should treat the bundled `_internal` library as just one native plugin provider among many, not as the only possible native provider.

### Public Native Plugin API

Add a new Python module:

- `gaspatchio_core.plugins.native`

Responsibilities:

- resolve plugin library paths
- expose a small wrapper around `register_plugin_function(...)`
- validate compatibility metadata
- cache plugin manifests and loaded libraries

### API Sketch

```python
from gaspatchio_core.plugins.native import NativePlugin

plugin = NativePlugin.from_package("my_company_gspio_plugin")

expr = plugin.function(
    "fast_discount_curve",
    args=[pl.col("rate"), pl.col("month")],
    kwargs={"method": "continuous"},
    is_elementwise=True,
)
```

And for accessor implementations:

```python
class FinanceCompanyAccessor:
    def __init__(self, obj):
        self._obj = obj
        self._plugin = NativePlugin.from_package("my_company_gspio_plugin")

    def fast_discount_curve(self):
        return self._plugin.function(
            "fast_discount_curve",
            args=[self._obj._expr],
            is_elementwise=True,
        )
```

### Plugin Package Layout

Recommended layout:

```text
my-company-gspio-plugin/
├── pyproject.toml
├── src/
│   └── my_company_gspio_plugin/
│       ├── __init__.py
│       ├── accessors.py
│       ├── native.py
│       ├── plugin.toml
│       └── _native/
│           └── plugin.<so|dylib|dll>
└── rust/
    ├── Cargo.toml
    └── src/lib.rs
```

The Python package owns the runtime UX; the Rust crate owns the native kernels.

### Native Manifest

Each native plugin package should include machine-readable metadata.

Example `plugin.toml`:

```toml
name = "my-company-gspio-plugin"
version = "0.1.0"
plugin_api_version = "1"
native = true
gaspatchio = ">=0.2.2,<0.3.0"
polars = "==1.38.1"
python = ">=3.12"

[library]
relative_path = "_native/plugin.so"

[functions.fast_discount_curve]
is_elementwise = true
signature = "rate: Expr, month: Expr -> Expr"
```

### Compatibility Checks

At plugin load time, Gaspatchio should validate:

- Gaspatchio version satisfies plugin constraint
- Python version satisfies plugin constraint
- Polars version matches expected ABI contract
- declared native library file exists

If incompatible, fail with a targeted error that tells the user which version changed.

### Distribution Model

Support two installation modes:

#### 1. Prebuilt wheels

Preferred for most users.

The plugin ships:

- Python package
- prebuilt native binary for each supported platform

No local Rust toolchain required.

#### 2. Local compilation

Supported for internal teams and agent workflows.

The plugin ships source plus build instructions; an agent can compile it locally if the toolchain is available.

## Lane C: Macro / Expression Plugins

Not every plugin needs new native code.

Gaspatchio should explicitly support a middle layer of customization:

- expression macros
- compiled composition helpers
- reusable higher-level actuarial transforms

These are implemented as Python accessors that return expression graphs built from existing Gaspatchio and Polars operations.

### Why this matters

This is often fast enough while keeping:

- full vectorization
- Polars lazy planning
- easier portability
- easier agent authoring
- lower maintenance cost than Rust

### Guidance

Default recommendation:

1. Build customization as an expression/macro plugin first
2. Benchmark it
3. Port only the true bottlenecks to Rust native kernels

This preserves the "formula is the code" philosophy and keeps native code focused.

## Plugin Taxonomy

Gaspatchio should recognize four plugin capabilities:

1. **Accessor plugin**: adds namespaces to frame/column/expression APIs
2. **Macro plugin**: adds reusable expression-building helpers
3. **Native plugin**: adds compiled Polars/Rust functions
4. **Workflow plugin**: adds CLI helpers, templates, examples, tutorials, or validation rules

One package may provide more than one capability.

## Authoring Workflow for Agents

Gaspatchio should ship a CLI workflow specifically designed to reduce ambiguity for agents.

## CLI Commands

### `gspio plugins list`

Show installed plugins, origin package, capability types, and compatibility status.

### `gspio plugins describe <plugin>`

Show:

- namespaces added
- native functions exposed
- version compatibility
- example usage

### `gspio plugin init accessor <name>`

Scaffold:

- Python package skeleton
- entry points
- example accessor methods
- test skeleton

### `gspio plugin init native <name>`

Scaffold:

- Python wrapper package
- Rust crate
- plugin manifest
- example `#[polars_expr]`
- build instructions

### `gspio plugin validate <path-or-package>`

Validate:

- manifest correctness
- entry points
- native library presence
- compatibility rules
- importability

### `gspio plugin benchmark <path-or-package>`

Run focused benchmarks against sample data to decide whether native code is worth the complexity.

## Compatibility Contract

Native plugins need a stable contract or they become brittle.

### v1 Contract

Introduce a small explicit plugin API version:

- `plugin_api_version = "1"`

This version should cover:

- expected metadata format
- loader behavior
- minimal assumptions about Polars plugin invocation
- error handling behavior

### Versioning Rules

#### Accessor-only plugins

These are relatively stable and can follow standard Python package version constraints.

#### Native plugins

These should pin more tightly:

- exact or narrow `polars` versions
- compatible Gaspatchio minor range
- minimum Python version

Native plugin compatibility should be pessimistic by default.

## Packaging Recommendations

### Do not require Rust for all users

The default user experience should be:

1. `uv add my-company-gspio-plugin`
2. plugin is discovered automatically
3. accessors become available immediately

Requiring local Rust compilation for all plugin consumers would unnecessarily narrow adoption.

### Allow local compile for advanced users and agents

The environment used by agents and contributors often already contains:

- `rustc`
- `cargo`
- `uv`

That should be treated as an optimization path for development and internal deployment, not as the baseline distribution requirement.

## Security & Governance

Plugins execute arbitrary Python and may load arbitrary native code. Gaspatchio should not pretend otherwise.

### Recommended posture

- First-party plugins are trusted
- Third-party plugins are opt-in
- Native plugins are clearly labeled
- CLI output should distinguish:
  - pure Python
  - native code present
  - compatibility status

### Optional future hardening

- allowlist mode for enterprise installs
- signed plugin manifests
- provenance reporting in `gspio plugins list`

These are useful later, but not required for v1.

## Documentation Fixes Required

This design implies immediate cleanup of the current docs.

### 1. Fix namespace references

Some docs still refer to `gaspatchio_core.dsl.plugins` and `gaspatchio_core.dsl.core`. The actual public package structure should be documented consistently.

### 2. Align `07-plugins.md` with reality

Either:

- implement entry-point discovery now and keep the document

or:

- update the document to state that entry-point discovery is planned, not current behavior

### 3. Document the recommended ladder

Document customization in this order:

1. Accessor plugin
2. Macro/expression plugin
3. Native plugin
4. Core contribution only if the feature belongs upstream

## Recommended Rollout

## Phase 1: Finish the Python Plugin Story

Ship:

1. Entry-point discovery for `gaspatchio.accessors`
2. Public plugin metadata registry in Python
3. `gspio plugins list` and `gspio plugins describe`
4. Updated docs and one example accessor plugin repo

### Outcome

Agents and users can create installable accessor packages without forking Gaspatchio.

## Phase 2: Add Native Plugin Support

Ship:

1. `gaspatchio_core.plugins.native`
2. external library loading by package/path
3. manifest validation and compatibility checks
4. plugin scaffolding CLI
5. one example native plugin

### Outcome

Teams can keep Rust performance for custom kernels without recompiling Gaspatchio itself.

## Phase 3: Optimize the Agent Workflow

Ship:

1. `gspio plugin init accessor`
2. `gspio plugin init native`
3. `gspio plugin validate`
4. `gspio plugin benchmark`
5. plugin authoring docs discoverable through `gspio docs`

### Outcome

Agents can reliably scaffold and ship extensions with far less repo exploration and guesswork.

## Alternatives Considered

### 1. Keep customization internal-only

Pros:

- minimal implementation effort
- lowest support burden

Cons:

- weak external customization story
- forces downstream forks
- undercuts the "design for AI" philosophy

Rejected.

### 2. Require all native plugins to be merged into core

Pros:

- simpler runtime model
- fewer compatibility questions

Cons:

- slow iteration
- raises contribution barrier
- makes private/enterprise customization awkward

Rejected.

### 3. Ship a Rust toolchain requirement to all plugin consumers

Pros:

- simpler source distribution story

Cons:

- worse UX
- cross-platform pain
- unnecessary for the majority of users

Rejected as the default. Supported only for advanced workflows.

### 4. Build a sandboxed WASM runtime first

Pros:

- interesting long-term isolation story

Cons:

- much higher complexity
- unclear performance profile for this workload
- distracts from the simpler plugin/package problem

Deferred.

## Recommended Decision

Adopt the three-lane plugin architecture:

1. **Python accessor plugins** as the default extension model
2. **Macro/expression plugins** as the preferred performance-preserving middle layer
3. **External native plugin packages** as the optimization path for true hot spots

This makes Gaspatchio meaningfully more customizable by agents while preserving the existing Rust/Polars performance strategy.

## Success Criteria

Gaspatchio has succeeded when:

1. An agent can create and install a pure Python plugin package that adds `af.reporting` with no core edits
2. An agent can create and install a native plugin package that adds a Rust-backed accessor without rebuilding `gaspatchio_core._internal`
3. Users can inspect installed plugins and compatibility status with one CLI command
4. Docs clearly distinguish current behavior from planned behavior
5. Plugin authors can follow a stable template rather than reading internal implementation details

