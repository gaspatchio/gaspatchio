# Background Agent Environment

This directory contains the Dockerfile used by Cursor background agents. It provides a dev-ready, non-root environment with `zsh`, Rust (stable + nightly), and Python via `uv`. It does not copy your source code; the agent will clone your repo at runtime.

## Build

From the repo root (preferred):

```bash
docker build -f .cursor/Dockerfile -t gaspatchio/cursor-agent:dev .cursor
```

Alternatively, from inside `.cursor/`:

```bash
cd .cursor
docker build -t gaspatchio/cursor-agent:dev .
```

Notes:
- The build context is `.cursor/` to avoid sending your whole repo (no COPY is used).
- Image runs as non-root user `ubuntu` with HOME and WORKDIR at `/home/ubuntu`.

## Quick test (interactive)

```bash
docker run --rm -it gaspatchio/cursor-agent:dev zsh
```

You should see `zsh` as the default shell. Verify toolchain:

```bash
uv --version
rustc --version
cargo --version
```

To mount your current repo for ad-hoc testing:

```bash
docker run --rm -it \
  -v "$PWD":/home/ubuntu/workspace \
  -w /home/ubuntu/workspace \
  gaspatchio/cursor-agent:dev zsh
```

## How Cursor uses this

- Cursor reads `.cursor/environment.json` to build and run background agents.
- This Dockerfile sets `USER=ubuntu` and `WORKDIR=/home/ubuntu`, matching background-agent guidance.
- No code is copied in the image. Agents clone your project after startup.
- The `install` step in `.cursor/environment.json` (`uv sync`) runs post-clone inside the container.

Current `.cursor/environment.json`:

```json
{
  "build": { "dockerfile": "Dockerfile", "context": "." },
  "terminals": [],
  "install": "uv sync"
}
```

If you prefer a prebuilt image, push this image to a registry and replace `build` with an `image` field in `environment.json`.

## Design choices

- Non-root `ubuntu` user with default shell `/usr/bin/zsh`.
- PATH includes user-local bins for `uv` and Rust toolchains.
- Locale and timezone set for reproducible behavior (UTC, en_US.UTF-8).
- Rust stable + nightly installed; nightly is the default (adjust if you prefer stable).

## Reference

- Creating a Dockerfile for background agents: https://cursor.com/environment-json-dockerfile.md
