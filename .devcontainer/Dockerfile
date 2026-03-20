FROM ubuntu:24.04

ARG AJANTV2_TAG=ntv2_17_5_0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       build-essential \
       cmake \
       ninja-build \
       git \
       ca-certificates \
       curl \
       openssh-client \
       libudev-dev \
       pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${AJANTV2_TAG}" \
        https://github.com/aja-video/libajantv2.git /tmp/libajantv2 \
    && cmake -S /tmp/libajantv2 -B /tmp/libajantv2/build -G Ninja \
       -DCMAKE_BUILD_TYPE=Release \
       -DCMAKE_INSTALL_PREFIX=/usr/local \
       -DAJANTV2_DISABLE_DEMOS=ON \
       -DAJANTV2_DISABLE_DRIVER=ON \
       -DAJANTV2_DISABLE_TESTS=ON \
       -DAJANTV2_DISABLE_TOOLS=ON \
       -DAJANTV2_DISABLE_PLUGIN_LOAD=ON \
    && cmake --build /tmp/libajantv2/build \
    && cmake --install /tmp/libajantv2/build \
    && rm -rf /tmp/libajantv2/build

RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh \
    && uv python install 3.13

RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN userdel -r ubuntu 2>/dev/null; \
    groupadd --gid 1000 dev || true \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash dev

# Unlimited memlock — the NTV2 driver pins user-space pages via
# get_user_pages for DMA transfers.  --ulimit=memlock=-1:-1 in
# devcontainer.json is silently ignored by the devcontainer CLI,
# so we set it here instead.  The dev user entry covers non-root
# shells; root is unlimited by default.
RUN echo "dev  -  memlock  unlimited" >> /etc/security/limits.conf

# Install Claude Code for root (remoteUser) and dev (fallback).
RUN curl -fsSL https://claude.ai/install.sh | bash
USER dev
ENV PATH="${PATH}:/home/dev/.local/bin"
RUN curl -fsSL https://claude.ai/install.sh | bash
