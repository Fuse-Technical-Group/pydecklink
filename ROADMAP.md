# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Reliability Engineering (Spec §9)

- **ci-static-analysis**: Add ruff (lint + format) and mypy (strict) to
  CI pipeline. Configure `pyproject.toml` with ruff rules and mypy
  settings. Fix any violations in existing code. (§9.1)
- **ci-unit-tests**: Run the five no-hardware test modules in CI after
  the build step. Requires no new infrastructure — just a `uv run pytest`
  invocation in `ci-linux.yml`. (§9.2)
- **buffer-validation**: Add contiguity and writability checks to
  `set_video_buffer()`, `dma_read_frame()`, and `dma_write_frame()` in
  the C++ bindings. (§9.3)
- **bind-task-mode-enum**: Bind `NTV2EveryFrameTaskMode` as a `TaskMode`
  enum and update `get_every_frame_services()` /
  `set_every_frame_services()` signatures. (§9.4)
- **routing-input-validation**: Replace bare `KeyError` with descriptive
  `ValueError` in `route_capture()` and `route_playout()`. (§9.5)
- **rich-check-errors**: Extend `check()` in `bind_common.h` to accept
  formatted strings with argument values. Update callers that take enum
  arguments. Add state-query-on-failure to AutoCirculate transition
  methods (`start`, `stop`, `init_for_input`, `init_for_output`) so
  errors report the channel's current `acState`. (§9.6)
- **expand-unit-tests**: Add tests for `get_frame_bytes`, exhaustive
  channel coverage on routing tables, routing negative paths,
  `frame_count < 3` validation, buffer validation negative paths, and
  all SDI output destinations. Depends on buffer-validation,
  routing-input-validation. (§9.7)
- **define-public-all**: Add `__all__` to `__init__.py` listing every
  public name. (§9.8)
- **retire-scripts**: Delete `test_capture_minimal.cpp`,
  `CMakeLists.txt`, and `probe_capture_dma.py` from `scripts/`.
  Simplify `scripts/.gitignore`. Keep `reset_card.sh`. (§9.9)

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
