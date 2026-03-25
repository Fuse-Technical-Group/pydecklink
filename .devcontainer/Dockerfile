FROM ubuntu:24.04

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
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh \
    && uv python install 3.13

# Tell the linker where Desktop Video SDK libs live (bind-mounted from host).
# The mount won't exist at build time, but ldconfig will re-run at container
# start when the mount appears (or we can run it in postCreateCommand).
RUN echo "/var/lib/blackmagic/lib" > /etc/ld.so.conf.d/blackmagic.conf

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
