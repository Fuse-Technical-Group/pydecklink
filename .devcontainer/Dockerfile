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
       python3.12 \
       python3.12-dev \
       python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${AJANTV2_TAG}" \
        https://github.com/aja-video/libajantv2.git /tmp/libajantv2 \
    && cmake -S /tmp/libajantv2 -B /tmp/libajantv2/build -G Ninja \
       -DCMAKE_BUILD_TYPE=Release \
       -DCMAKE_INSTALL_PREFIX=/usr/local \
       -DAJANTV2_BUILD_SHARED=ON \
       -DAJANTV2_DISABLE_DEMOS=ON \
       -DAJANTV2_DISABLE_DRIVER=ON \
       -DAJANTV2_DISABLE_TESTS=ON \
       -DAJANTV2_DISABLE_TOOLS=ON \
       -DAJANTV2_DISABLE_PLUGIN_LOAD=ON \
    && cmake --build /tmp/libajantv2/build \
    && cmake --install /tmp/libajantv2/build \
    && rm -rf /tmp/libajantv2

RUN ldconfig

RUN UV_INSTALL_DIR=/usr/local/bin curl -LsSf https://astral.sh/uv/install.sh | sh

RUN userdel -r ubuntu 2>/dev/null; \
    groupadd --gid 1000 dev || true \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash dev

USER dev
ENV PATH="${PATH}:/home/dev/.local/bin"

RUN curl -fsSL https://claude.ai/install.sh | bash
