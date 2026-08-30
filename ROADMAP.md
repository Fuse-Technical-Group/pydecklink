# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## DeckLink IP as an ST 2110 far end §road:decklink-ip-streams

The address, the PTP role and the output groups are reachable now
(§spec:ethernet), and the card on the bench is configured static on the
media fabric as a PTP follower. What is not delivered is the stream half:
choosing the video output group per device, reading the groups a receiver
is bound to, and the SDP that names them — so a peer can be pointed at
this card without the Desktop Video GUI.

**Blocked on cabling, not on code.** The bench card reports
`EthernetLink: Disconnected` at 0 Mbps on every one of its eight
sub-devices, while the ConnectX-6 port facing it carries a 100G link with
zero packets received. One of those two readings is of a wire that is not
there. Until the card's own port reports `ConnectedUnbound` or better,
nothing here can be measured.

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

## Hoist packing to a shared library §road:hoist-packing

Move `pydecklink.packing`'s layout table and its pack/unpack
implementations into `Fuse-Technical-Group/pypixelpack` — a standalone,
array-namespace-generic package, sibling to this repository and
pyst2110 — and consume it here. pypixelpack's scope is the whole
encoding step, not layout alone: colour matrix (parameterised, BT.709
and BT.2020 at least), range, chroma subsampling, and layout. The
measure layer defines a patch as what the processor receives and must
declare an encoding for SDI without implementing one, so the conversion
that today lives only in backlit_molecule moves with the layouts
(umbrella `§spec:architecture` in color-wrangler) — keeping `_FORMATS`, the map from `PixelFormat` to a
layout name, which is the only Blackmagic-specific thing in the module.
§spec:pixel-packing.

**The condition §spec:pixel-packing set has arrived.** That section
co-locates packing "until packing earns an independent release
lifecycle (per YAGNI)". A second consumer now exists that cannot use
this implementation: backlit_molecule converts RGB→V210 on the GPU and
DMAs the packed result into a pinned SDK frame
(`§road:shared-pixel-packing` there). Routing that through a NumPy host
packer would drag an uncompressed frame back across PCIe every frame and
defeat its `torch.compile` fusion, so it keeps its own copy today — the
strand-reusable-code outcome this section exists to prevent, arrived at
from the other direction.

**The skew argument is weaker than the section states.** Packing is not
"keyed entirely to `PixelFormat`": `_LAYOUT` and every pack/unpack are
keyed on plain strings, and only `_FORMATS` touches the enum. Keeping
that dict here leaves the enum and its map in one package, so there is
no version skew to invite.

Scope is every layout, not v210 alone. `r210` is uncompressed 10-bit RGB
4:4:4 — a QuickTime FourCC FFmpeg also reads — so an RGB 4:4:4 SDI
consumer needs a device-side packer for it exactly as it does for v210,
and hoisting one format would reopen this on the next.

Two things to settle in the work: whether `2vuy` gains a layout entry, as
`PixelFormatType` names an 8-bit 4:2:2 format that neither codebase can
pack today; and whether `r10b`, `r10l`, `r12b` and `r12l` are standards
or SDK spellings, which is unresolved and does not block the cut — an
ambiguous layout costs nothing in a string-keyed table.

**Prior art, checked 2026-08-29.** Nothing on PyPI packs these layouts:
`pypixelpack`, `v210`, `pyv210`, `pixelpack`, `pixel-packing` and `uyvy`
are all unregistered, and imagecodecs, PyAV, vidgear and pyffmpeg name
none of these formats. The closest are libp2p, a C++ template library
with a special-cased v210, and FFmpeg's own v210/r210 codecs reachable
through PyAV — which operate on `AVFrame` and so require a copy in and
out, defeating in-place packing on a device and unable to touch a torch
tensor. Neither is a usable dependency here; both are worth reading as a
byte-layout oracle for the tests, and FFmpeg's format list would settle
whether `r10b`, `r10l`, `r12b` and `r12l` are standards.

The layouts are well documented elsewhere, so this is a re-implementation
rather than new ground. What does not exist is a pure-array,
namespace-generic one, which is what the device path needs.

### Consume pypixelpack's layouts §road:consume-pypixelpack

Replace every `_pack_*`/`_unpack_*` implementation and the `_LAYOUT`
table in `pydecklink/packing.py` with imports from `pypixelpack`,
keeping `_FORMATS` (the `PixelFormat` → layout-name map) and the
`pack`/`unpack` surface unchanged; pin pypixelpack by git tag as
display-patterns is pinned by its consumers. §spec:pixel-packing.
Blocked — pypixelpack has no release yet (`§road:first-release`
there). Unblocked when v0.1.0 is tagged.

### Record the moved boundary §road:packing-spec-boundary

Rewrite §spec:pixel-packing so it describes what this repository still
holds — the enum map and the surface — and points at pypixelpack for
the layouts, replacing the "keyed entirely to `PixelFormat`" and
co-location rationale that no longer describe the module.
§spec:pixel-packing. Depends on §road:consume-pypixelpack.

**Verify:** `pack`/`unpack` keep their surface and their
`unpack(pack(x)) == x` property for every format; importing
`pydecklink` still pulls no packing code; the same shared source packs
byte-identically on numpy here and on torch in backlit_molecule; and
§spec:pixel-packing records the moved boundary rather than describing a
module that no longer holds the layouts.

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
