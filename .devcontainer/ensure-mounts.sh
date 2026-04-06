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

# SSH agent socket — if SSH_AUTH_SOCK is unset or points to a
# non-existent path, create a placeholder so the bind mount succeeds.
# The socket won't function, but the container will start.
if [ -z "${SSH_AUTH_SOCK:-}" ] || [ ! -e "${SSH_AUTH_SOCK}" ]; then
    fallback="/tmp/ssh-agent-placeholder.sock"
    if [ ! -e "$fallback" ]; then
        touch "$fallback"
    fi
    export SSH_AUTH_SOCK="$fallback"
    echo "Warning: SSH_AUTH_SOCK not set or missing; using placeholder. SSH agent forwarding will not work." >&2
fi
