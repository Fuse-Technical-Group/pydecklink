#!/usr/bin/env bash
# Guard against the one devcontainer combination that silently corrupts
# host file ownership under rootless Podman.
#
# Rootless Podman maps container UID 0 (root) to the host user by default,
# but `--userns=keep-id` inverts that: it maps the *host* user to the same
# UID in-container, sending container root to a host subuid (e.g. 524288).
# So a keep-id container that runs as root writes every file it touches --
# including .git -- as that subuid, blocking host-side git writes until a
# `chown` rescue. Run as a non-root user (UID 1000) instead.
#
# Fails if any devcontainer config sets keep-id while remoteUser is root.
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if grep -rqs 'keep-id' "$dir" \
   && grep -rEqs '"remoteUser"[[:space:]]*:[[:space:]]*"root"' "$dir"; then
  echo "ERROR: devcontainer sets --userns=keep-id together with remoteUser:root." >&2
  echo "Under rootless Podman this writes files (incl. .git) as a host subuid," >&2
  echo "not your user. Run as a non-root user (e.g. remoteUser: ubuntu, UID 1000)." >&2
  exit 1
fi

echo "devcontainer userns/user guard: OK"
