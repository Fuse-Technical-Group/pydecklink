#!/usr/bin/env bash
# Ensure bind-mount source paths exist on the host so Podman doesn't
# fail with "statfs: no such file or directory".
# Creates empty stubs only — the container starts in degraded mode
# (no Claude, no gh auth, etc.) when the real files are absent.
set -euo pipefail

ensure_dir() {
    [ -d "$1" ] || mkdir -p "$1"
}

ensure_file() {
    local dir
    dir="$(dirname "$1")"
    [ -d "$dir" ] || mkdir -p "$dir"
    [ -e "$1" ] || touch "$1"
}

# Claude config files
ensure_file "${HOME}/.claude/.credentials.json"
ensure_file "${HOME}/.claude/settings.json"
ensure_file "${HOME}/.claude/CLAUDE.md"
ensure_dir "${HOME}/.claude/commands"

# Git / GitHub CLI config
ensure_file "${HOME}/.gitconfig"
ensure_dir "${HOME}/.config/gh"

# SSH agent socket — devcontainer.json bind-mounts a fixed host path
# (`/tmp/ssh-agent-pydecklink-${USER}.sock`) regardless of agent state.
# We can't export SSH_AUTH_SOCK back to the parent devcontainer CLI
# (this script runs in a child process), so we instead make the fixed
# host path resolve to either the live agent socket (via symlink) or
# a dead placeholder file. The container engine follows host-side
# symlinks at mount time, so the symlink path forwards the live socket
# transparently. The placeholder is a regular file: bind mount succeeds,
# `ssh` inside the container fails cleanly with "Bad file descriptor"
# instead of aborting container startup.
ssh_link="/tmp/ssh-agent-pydecklink-${USER}.sock"
rm -f "$ssh_link"
if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
    ln -s "${SSH_AUTH_SOCK}" "$ssh_link"
else
    touch "$ssh_link"
    echo "Warning: SSH_AUTH_SOCK not set or not a socket; SSH agent forwarding disabled inside container." >&2
fi
