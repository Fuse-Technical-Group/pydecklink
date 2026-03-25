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

# Unlimited memlock — the NTV2 driver pins user-space pages via
# get_user_pages for DMA transfers.  --ulimit=memlock=-1:-1 in
# devcontainer.json is silently ignored by the devcontainer CLI,
# so we set it here instead.  The ubuntu user entry covers non-root
# shells; root is unlimited by default.
RUN echo "ubuntu  -  memlock  unlimited" >> /etc/security/limits.conf

# Pre-seed GitHub SSH host key so git-over-SSH works immediately
# with the forwarded SSH agent (mounted via devcontainer.json).
RUN mkdir -p /root/.ssh /home/ubuntu/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && cp /root/.ssh/known_hosts /home/ubuntu/.ssh/known_hosts \
    && chown -R 1000:1000 /home/ubuntu/.ssh

# Install Claude Code for root and ubuntu user.
RUN curl -fsSL https://claude.ai/install.sh | bash
USER ubuntu
ENV PATH="${PATH}:/home/ubuntu/.local/bin"
RUN curl -fsSL https://claude.ai/install.sh | bash
