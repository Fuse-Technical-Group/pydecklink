# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA (Phase 2)

- **cuda-pinned-alloc**: Wire CUDA `cudaHostAlloc`/`cudaFreeHost` as
  the allocation functions for `VideoBufferAllocator`. Requires CUDA
  toolkit in the devcontainer. The allocator infrastructure
  (**custom-allocator**, **gpu-output-pool**) is complete; this
  workstream adds the CUDA-specific backend.

## macOS Support

- **macos-build**: Add macOS path to `platform.h` and CMakeLists.txt.
  Mac SDK headers are already vendored. macOS uses CoreFoundation-based
  COM (`CFPlugIn`) rather than `dlopen` dispatch (Linux) or Windows COM.
  Extend `platform.h` with macOS type aliases and
  `CreateDeckLinkIteratorInstance`. Add CI workflow for macOS.

## Repo Hygiene

- **pre-commit**: Add `.pre-commit-config.yaml` with:
  - `pre-commit/pre-commit-hooks`: `end-of-file-fixer`,
    `trailing-whitespace`, `check-toml`, `check-yaml`,
    `check-merge-conflict`.
  - `astral-sh/ruff-pre-commit`: replace the CI `uv tool run ruff`
    step — runs ruff lint + format as a pre-commit hook.
  - `pre-commit/mirrors-clang-format` (or similar): consistent
    C++ formatting for `src/pydecklink_ext/`.
  Add `pre-commit run --all-files` to `ci-linux` so CI enforces the
  same hooks. Consider `pre-commit.ci` for automatic PR fixups.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
