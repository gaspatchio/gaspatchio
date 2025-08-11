# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive

# Base tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl ca-certificates git \
    build-essential pkg-config libssl-dev \
    xz-utils zstd patchelf cmake \
 && rm -rf /var/lib/apt/lists/*

# Optional: timezone/locale support for consistent tests
ENV TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends tzdata locales \
 && rm -rf /var/lib/apt/lists/*
RUN locale-gen en_US.UTF-8 || true
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash ubuntu

# Use non-root user, set home, workdir, and PATH to user-local bins
ENV USER=ubuntu
ENV HOME=/home/ubuntu
WORKDIR /home/ubuntu
ENV PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
USER ubuntu

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

# (Optional) make nightly default
RUN rustup default nightly