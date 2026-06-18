# pydecklink

Python bindings for the [Blackmagic DeckLink SDK](https://www.blackmagicdesign.com/developer/product/capture-and-playback),
exposing the capture and scheduled playback APIs via CPU buffers (numpy).

## Requirements

- **Linux**, **macOS**, or **Windows** with
  [Blackmagic Desktop Video](https://www.blackmagicdesign.com/support/family/capture-and-playback)
  installed
- Blackmagic DeckLink hardware
- Python 3.12+

## Install

```bash
uv pip install pydecklink
```

Prebuilt wheels ship for Linux (manylinux x86_64), macOS, and Windows.
Building from source requires a C++ toolchain — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Quick start

```python
import pydecklink

# Desktop Video runtime version
print(pydecklink.api_version().string)

# Enumerate DeckLink devices
for info in pydecklink.list_devices():
    print(f"{info.index}: {info.model_name}")

# Display modes a device can output
dev = pydecklink.Device(0)
for m in dev.list_output_modes():
    fps = pydecklink.get_mode_fps(m.mode)
    print(f"{m.name}: {m.width}x{m.height} @ {fps:.2f}")
```

## Examples

The [`examples/`](examples) directory in the repo contains runnable scripts:

| Script | What it does |
|---|---|
| `passthrough.py` | Zero-copy SDI capture → playout loop. |
| `cuda_passthrough.py` | Canonical SDI → CUDA kernel → SDI recipe (drop in your own kernel callable). |
| `cuda_loopback_latency.py` | Fingerprint loopback benchmark for end-to-end latency. |
| `cuda_register_pinned.py` | Register CUDA pinned memory for the H2D capture path. |
| `detect_signals.py` | Walk all inputs, report which carry an active signal. |
| `dump_topology.py` | Print each device's identity and profile attributes. |

CUDA examples need the `cuda-examples` extra
(`uv pip install "pydecklink[cuda-examples]"`).

## License

BSD-3-Clause — see [LICENSE](LICENSE).
