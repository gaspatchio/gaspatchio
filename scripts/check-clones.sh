#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# Run from the repository root. CI and the documented reproduction command
# share this scope and fingerprint baseline.
set -euo pipefail
exec npx --yes jscpd@5.1.2 bindings/python/gaspatchio core/src engines/jax/src \
  --min-lines 12 --min-tokens 70 --reporters console \
  --ignore "**/tutorials/**,**/__pycache__/**,**/schemas/vectors/**,**/schemas/conformance/**" \
  --baseline .github/jscpd-baseline.json --fail-on-new-clones
