FROM nvidia/cuda:13.0.0-runtime-ubuntu24.04

# Mirrors .devcontainer/Dockerfile but on a CUDA-runtime base so cuda-python
# can dlopen libcudart.so. No nvcc — examples are pure-Python (cuda-python
# bindings); pydecklink itself never imports a GPU toolkit (SPEC §gpu-pinned-memory).
#
# Tag tracks `cuda-python` on PyPI, which is currently 13.x and links to
# libcudart 13. If a downstream tool forces CUDA 12 (e.g. ONNX Runtime, which
# lags major CUDA bumps), swap the tag and pin `cuda-python>=12,<13` in
# pyproject's [cuda-examples] extra.

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       build-essential \
       cmake \
       ninja-build \
       git \
       ca-certificates \
       curl \
       openssh-client \
       pkg-config \
       sudo \
    && rm -rf /var/lib/apt/lists/*

# nvidia/cuda images don't ship the `ubuntu` user — create it to match the
# default devcontainer (UID 1000). common-utils feature in devcontainer.json
# will reconcile UID/GID at start.
RUN useradd -m -u 1000 -s /bin/bash ubuntu \
    && echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh \
    && uv python install 3.13

# Tell the linker where Desktop Video SDK libs live (bind-mounted from host).
RUN echo "/var/lib/blackmagic/lib" > /etc/ld.so.conf.d/blackmagic.conf

# Unlimited memlock for page-locked DMA buffers. cudaHostAlloc pins pages;
# DeckLink DMA also wants page-locked memory. Default RLIMIT_MEMLOCK (~64MB)
# is too small for multi-buffer 1080p+ capture. The matching
# --ulimit=memlock=-1 in devcontainer.json is silently ignored by the
# devcontainer CLI, so we bake the limit into limits.conf here.
RUN echo "* - memlock unlimited" >> /etc/security/limits.conf

# Pre-seed GitHub SSH host key so git-over-SSH works immediately
# with the forwarded SSH agent.
RUN mkdir -p /root/.ssh /home/ubuntu/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && cp /root/.ssh/known_hosts /home/ubuntu/.ssh/known_hosts \
    && chown -R 1000:1000 /home/ubuntu/.ssh

# Install Claude Code for root and ubuntu user.
RUN curl -fsSL https://claude.ai/install.sh | bash
USER ubuntu
ENV PATH="${PATH}:/home/ubuntu/.local/bin"
RUN curl -fsSL https://claude.ai/install.sh | bash
