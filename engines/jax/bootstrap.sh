#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# bootstrap.sh <core-wheel> [python] — run from this directory only.
# The core arrives as a prebuilt wheel; nothing here builds or installs from bindings/python.
set -euo pipefail
WHEEL="${1:?usage: bootstrap.sh <core-wheel> [python]}"
ENGINE_PYTHON="${2:-3.13}"
[ -f "$WHEEL" ] || { echo "no such wheel: $WHEEL" >&2; exit 2; }
uv venv --python "$ENGINE_PYTHON" .venv
# Everything the lock holds except the core, which the lock resolves from
# ../../bindings/python and which is never built from there (no-build-package
# in pyproject.toml). The core's own dependencies are in the lock and install
# here; the core itself is the wheel, installed after them without its deps.
uv sync --locked --no-install-package gaspatchio --python "$ENGINE_PYTHON"
uv pip install --python .venv/bin/python --no-deps "$WHEEL"
.venv/bin/python - <<'PY'
import hashlib, platform, sys
from importlib.metadata import version
import jax, jaxlib, numpy, polars
import gaspatchio
from gaspatchio import _internal
path = _internal.__file__
digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
print(f"interpreter {sys.executable} {sys.version.split()[0]}")
print(f"platform {platform.platform()}")
print(f"jax {jax.__version__} jaxlib {jaxlib.__version__} numpy {numpy.__version__} polars {polars.__version__}")
print(f"gaspatchio {version('gaspatchio')}")
print(f"extension {path}")
print(f"extension sha256 {digest}")
PY
