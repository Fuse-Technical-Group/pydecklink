# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Devcontainer userns cleanup

- **userns-keep-id-ubuntu**: Switch `remoteUser` from `dev` to
  `ubuntu` (the pre-existing UID 1000 user in `ubuntu:24.04`).
  Remove the `dev` user creation, `userdel ubuntu`, sudo install,
  and `postCreateCommand` chown workaround from the Dockerfile.
  Remove `UV_PROJECT_ENVIRONMENT` / `VIRTUAL_ENV` overrides from
  `devcontainer.json` so host and container share a single `.venv`.
  Update mount paths from `/home/dev/` to `/home/ubuntu/`. Remove
  `.venv-dev/` from `.gitignore`. Adopt devcontainer features
  (`common-utils`, `github-cli`, `fish`) from humongous-boat and
  remove the manual gh CLI install from the Dockerfile.
  Update SPEC.md §2 Constraints. Aligns with the working userns
  pattern from humongous-boat.

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
