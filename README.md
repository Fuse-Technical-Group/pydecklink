# pyntv2

Python bindings for [AJA's libajantv2 SDK](https://github.com/aja-video/libajantv2),
exposing the AutoCirculate API for frame-accurate SDI/HDMI capture and
playout via CPU buffers (numpy).

> **Note:** The AJA NTV2 DMA engine is 32-bit addressable. GPU RDMA
> (CuPy/PyTorch) does not work on 64-bit systems. The bindings accept
> `nb::ndarray` from any device, but only CPU buffers are functional.

> **Note:** `iommu=pt` (passthrough) must be **disabled**. The kernel's
> SWIOTLB bounce-buffer path does not correctly map allocations down to
> the 32-bit address space when IOMMU passthrough is active, causing DMA
> failures. Remove `iommu=pt` from kernel command line parameters or set
> `iommu=soft` to use software translation.

## Requirements

- Linux (kernel module `ajantv2` loaded, **no** `iommu=pt`)
- AJA NTV2 hardware (Corvid, Kona, etc.)
- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies)

libajantv2 is statically linked into the wheel at build time — no
SDK install needed on the host. Building from source requires the
libajantv2 headers/static library and CMake ≥ 3.18 (the devcontainer
provides these).

## Install

```bash
uv pip install .
```

Or for development (editable build with test dependencies):

```bash
uv pip install -e ".[dev]"
```

### Devcontainer

A VS Code devcontainer builds libajantv2 from source at a pinned
release tag and provides a ready-to-code environment for the Python
and C++ layers.

> **Note:** DMA transfers do not yet work inside the container. The
> devcontainer is useful for building and editing, but capture/playout
> must run on the host. Container-based DMA is a work in progress —
> see SPEC.md §2 for the capability requirements under investigation.

## Quick start

```python
import numpy as np
from pyntv2 import (
    Card, Channel, InputSource, Mode, PixelFormat,
    ReferenceSource, Transfer, route_capture,
)

with Card(device_index=0) as card:
    fmt = card.get_input_video_format(InputSource.SDI1)

    card.set_sdi_transmit_enable(Channel.CH1, False)
    card.enable_channel(Channel.CH1)
    card.set_mode(Channel.CH1, Mode.CAPTURE)
    card.set_video_format(fmt, channel=Channel.CH1)
    card.set_frame_buffer_format(Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)
    card.set_reference(ReferenceSource.INPUT1)
    card.apply_signal_route(
        route_capture(InputSource.SDI1, Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)
    )

    buf = np.zeros(3840 * 2160 * 4, dtype=np.uint8)
    card.dma_buffer_lock(buf)

    card.autocirculate_init_for_input(Channel.CH1)
    card.autocirculate_start(Channel.CH1)

    xfer = Transfer()
    xfer.set_video_buffer(buf)
    card.autocirculate_transfer(Channel.CH1, xfer)
    # buf now contains one captured frame
```

See `examples/passthrough.py` for a full capture → playout loop.

## Running hardware tests

Hardware tests require an AJA card with a loopback cable between
CH3 (SDI3 out) and CH4 (SDI4 in). They are excluded by default;
opt in with `-m hardware`.

DMA operations need root privileges. Reset the card before each run
to clear any wedged DMA state:

```bash
# Reset the card (reloads kernel module)
sudo scripts/reset_card.sh

# Probe DMA on CH1 — quick sanity check
sudo .venv/bin/python3 scripts/probe_capture_dma.py

# Run the full integration suite
sudo scripts/reset_card.sh
sudo .venv/bin/python3 -m pytest tests/test_integration.py -m hardware -v
```

The card reset is necessary because a failed DMA transfer leaves the
Xilinx DMA engine in an error state. Subsequent transfers fail with
EPERM until the PCI device is reset and the driver is reloaded.

### Diagnostic scripts

| Script | Purpose |
|---|---|
| `scripts/reset_card.sh` | PCI function-level reset + driver reload |
| `scripts/probe_capture_dma.py` | Single-channel capture DMA smoke test |
| `scripts/test_capture_minimal.cpp` | Standalone C++ capture (bypasses Python) |

## License

MIT — see [LICENSE](LICENSE).
