# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Integration blockers

Cannot integrate pyntv2 into a three-thread capture/process/playout
app without these. Spec §5.4, §5.7, §5.9, §5.10.

- **gil-release**: Add `nb::call_guard<nb::gil_scoped_release>()` to
  `autocirculate_transfer()`, `wait_for_input_vertical_interrupt()`,
  and the new `wait_for_output_vertical_interrupt()`. Without this,
  Python threads serialize on blocking DMA/VBI calls.
- **output-vbi**: Bind `CNTV2Card::WaitForOutputVerticalInterrupt()`
  with GIL release. Needed for playout pacing. Depends on
  **gil-release** (same pattern).
- **format-metadata**: Expose `get_format_width()`,
  `get_format_height()`, `get_format_fps()` via
  `NTV2FormatDescriptor`. `get_frame_bytes()` already exists.

## Nice to have

- **transfer-status-fields**: Expose `acTransferStatus.acTransferFrame`
  on the `Transfer` object as `transferred_frame`. Debugging aid.
- **benchmark-4k60-dma**: Benchmark two-hop DMA throughput at 4K/60.
  Validate ~16.6 ms/frame budget fits. Requires hardware.

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
