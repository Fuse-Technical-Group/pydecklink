# pydecklink

Python bindings for the [Blackmagic DeckLink SDK](https://www.blackmagicdesign.com/developer/product/capture-and-playback),
exposing the capture and scheduled playback APIs via CPU buffers (numpy).

## Requirements

- **Linux** or **Windows** (Blackmagic Desktop Video installed)
- Blackmagic DeckLink hardware
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

Or for development (editable build with test dependencies):

```bash
uv pip install -e ".[dev]"
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

## Quick start

```python
import pydecklink

for mode in pydecklink.display_modes():
    print(f"{mode.name}: {mode.width}x{mode.height} @ {mode.fps:.2f}")
```

See `examples/passthrough.py` for a capture → playout loop.

## Running hardware tests

Hardware tests require a DeckLink card. They are excluded by default;
opt in with `-m hardware`.

```bash
uv run pytest -m hardware -v
```

## License

MIT — see [LICENSE](LICENSE).
