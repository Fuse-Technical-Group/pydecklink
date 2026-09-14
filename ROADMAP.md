# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## DeckLink IP as an ST 2110 far end §road:decklink-ip-streams

Each connector's address and output groups, the device-wide PTP role, and
the link, packet counters and optical module of each connector are
reachable now (§spec:ethernet, §spec:statistics). What is not delivered
is the stream half: `IDeckLinkIPExtensions` and the `IDeckLinkIPFlow`
family, which read the groups a receiver is bound to and the SDP that
names a flow, and accept a peer's SDP — so a peer can be pointed at this
card without the Desktop Video GUI.

**The link is up.** Passive QSFP28 DACs never brought the bench card's
port up — the ConnectX-6 facing it trained, the card reported
`Disconnected` — and 100G optical modules did: both connectors report
`ConnectedBound` at 100000 Mbps, and traffic crosses in both directions.

**Verify:** With the link up, a `packet_engine` receive stream on the
ConnectX-6 port digests a flow this card sends, and the card's status
address matches the configured one.

## Sub-frame phase tuning §road:config-reference-input-timing-offset

Add a `--phase-sweep` mode to `examples/cuda_loopback_latency.py` that
walks the timing offset across one frame period in configurable steps
and reports RTT at each step. The `ConfigurationID.ConfigReferenceInputTimingOffset`
and `AttributeID.SupportsFullFrameReferenceInputTimingOffset` enums it
drives are already bound (9c66a02). Requires REF IN wired to an external
reference for the sweep to have an anchor; the SDK does not expose locking
the output PLL to the SDI input clock. §spec:latency-characterization.

**Verify:** With REF IN connected to an external reference shared with
the upstream source, run `python examples/cuda_loopback_latency.py
--ref-locked --phase-sweep`. Output prints an offset-vs-RTT table.
The minimum RTT across the sweep occurs at a non-zero offset and is
strictly less than the integer-frame floor of the free-running run.
Health counters remain zero at the reported optimum.

## Headroom and preroll sweep §road:headroom-preroll-sweep

Add a `--sweep` mode to `examples/cuda_loopback_latency.py` that varies
headroom and preroll across configurable ranges and reports a 2D
matrix of per-cell `OutputStatus.late + dropped + underrun` over a
sustained run per cell, identifying the configuration floor. Depends
on §road:config-reference-input-timing-offset.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py --sweep
--duration 60`. Output prints a 2D matrix indexed by (headroom,
preroll) showing per-cell health counters and identifies the minimum
stable configuration. Cells below the floor show nonzero counters;
cells at or above show zero. The benchmark exits with a nonzero
status if no stable configuration exists in the input range.

## HDR metadata capture §road:hdr-metadata-capture

Expose received HDR10 static metadata on captured frames, mirroring the
output write surface. Add `hdr_metadata → HDRMetadata | None` to
`CaptureFrame` and `CaptureFrameRef` in `bind_input.{h,cpp}`: query
`IID_IDeckLinkVideoFrameMetadataExtensions` (the read interface) off the
captured `IDeckLinkVideoInputFrame`, read the mastering-display,
white-point, and content-light-level IDs plus the EOTF/colorspace, and
return `None` when `FrameFlag.ContainsHDRMetadata` is absent. Reuse the
`HDRMetadata` / `EOTF` / `Colorspace` types from the output surface.
§spec:hdr-metadata-capture. Builds on the output HDR surface
(§spec:hdr-metadata / PR #198).

**Verify:** With an HDMI OUT → IN loopback on an `supports_hdr` device,
build a frame, `set_hdr_metadata(EOTF.PQ, Colorspace.Rec2020,
max_cll=10000)`, display it, capture it back, and assert
`frame.hdr_metadata` reports the same EOTF, colorspace, and MaxCLL.
Without hardware: assert `hdr_metadata` returns `None` for a plain SDR
capture and that the accessor exists on both `CaptureFrame` and
`CaptureFrameRef`.

## Future §road:future

- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **status-change-notifications**: Push-based status updates via
  `IDeckLinkNotification::Subscribe(bmdStatusChanged)` —
  `device.subscribe_status_changes() → StatusChangeQueue` per
  §spec:device-status. Deferred until a long-running monitor surface
  exists to consume it; the synchronous status getter already
  covers one-shot diagnostics.
