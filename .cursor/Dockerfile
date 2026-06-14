# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Base tools. git-lfs is required — *.parquet and *.csv fixtures are
# LFS-tracked (see .gitattributes); without it, clones get pointer files
# and fixture-based tests false-red.
RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update && apt-get install -y --no-install-recommends \
    bash zsh curl ca-certificates git git-lfs \
    build-essential pkg-config libssl-dev \
    xz-utils zstd patchelf cmake \
 && rm -rf /var/lib/apt/lists/*

# Optional: timezone/locale support for consistent tests
ENV TZ=UTC
RUN apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false update && apt-get install -y --no-install-recommends tzdata locales \
 && rm -rf /var/lib/apt/lists/*
RUN locale-gen en_US.UTF-8 || true
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# Create non-root user
RUN useradd -m -u 1000 -s /usr/bin/zsh ubuntu

# Use non-root user, set home, workdir, and PATH to user-local bins
ENV USER=ubuntu
ENV HOME=/home/ubuntu
WORKDIR /home/ubuntu
ENV PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
ENV SHELL=/usr/bin/zsh
USER ubuntu

# Register git-lfs smudge filter for the ubuntu user so clones
# auto-pull LFS content.
RUN git lfs install

# Install uv (Python env/packaging)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && uv --version

# Install Rust toolchains for the user
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable \
 && rustup toolchain install nightly \
 && rustup component add rustfmt clippy --toolchain stable \
 && rustup component add rustfmt clippy --toolchain nightly \
 && rustc --version && cargo --version && rustup show

# Use stable as default. Nightly's stricter transmute check rejects
# ethnum 1.5.0's `mem::transmute(())` (E0512), which polars pulls in
# transitively. Stable lets it compile.
RUN rustup default stable