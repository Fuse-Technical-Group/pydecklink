# pydecklink

Python bindings for the [Blackmagic DeckLink SDK](https://www.blackmagicdesign.com/developer/product/capture-and-playback),
exposing the capture and scheduled playback APIs via CPU buffers (numpy).

## Requirements

- **Linux** or **Windows** (Blackmagic Desktop Video installed)
- Blackmagic DeckLink hardware
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies)

The DeckLink SDK headers are vendored in the repo.

| | Linux | Windows |
|---|---|---|
| Runtime library | `libDeckLinkAPI.so` loaded via `dlopen` | COM interfaces via `CoCreateInstance` |
| Build toolchain | C++ compiler, CMake | MSVC, Windows SDK (provides MIDL), CMake |
| SDK artefacts | Pre-compiled headers + dispatch source | IDL files compiled to headers by MIDL at build time |

Install Blackmagic Desktop Video on the host for both platforms.

## Install

```bash
uv pip install .
```

Or for development (editable build with the `dev` dependency group —
pytest, mypy, psutil):

```bash
uv sync
```

### Windows

Building on Windows requires Visual Studio
with the **Desktop development with C++** workload (includes MSVC and
the Windows SDK). CMake automatically locates `midl.exe` from the
Windows SDK to compile the vendored DeckLink IDL files into C++ headers
and COM stubs.

```bash
uv sync
```

### Devcontainer (Linux)

A VS Code devcontainer provides a ready-to-code environment. It
bind-mounts the host's Desktop Video libraries and DeckLink device
nodes for hardware testing inside the container.

The container exposes Blackmagic's firmware tooling on `PATH` via
`/var/lib/blackmagic/bin`. `BlackmagicFirmwareUpdater` and
`DesktopVideoUpdateTool` are the same multi-call binary dispatched
on `argv[0]`; prefer `DesktopVideoUpdateTool` for scripted
invocations — its flag interface (`--list`, `--device ID`,
`--all`, `--quiet`) is the automation-friendly surface.
`BlackmagicFirmwareUpdater` is the interactive shorthand (`status`,
`update [device]`).

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

| Script | What it does |
|---|---|
| `passthrough.py` | Zero-copy SDI capture → playout loop. |
| `cuda_passthrough.py` | Canonical SDI → CUDA kernel → SDI recipe (drop in your own kernel callable). |
| `cuda_loopback_latency.py` | Fingerprint loopback benchmark for end-to-end latency. |
| `cuda_register_pinned.py` | Register CUDA pinned memory for the H2D capture path. |
| `detect_signals.py` | Walk all inputs, report which carry an active signal. |
| `dump_topology.py` | Print each device's identity and profile attributes. |

CUDA examples need the `cuda-examples` extra (`uv pip install ".[cuda-examples]"`).

## Running hardware tests

Hardware tests require a DeckLink card. They are excluded by default;
opt in with `-m hardware`.

```bash
uv run pytest -m hardware -v
```

## License

MIT — see [LICENSE](LICENSE).
