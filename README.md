# pydecklink

Python bindings for the [Blackmagic DeckLink SDK](https://www.blackmagicdesign.com/developer/product/capture-and-playback),
exposing the capture and scheduled playback APIs via CPU buffers (numpy).

## Requirements

- Linux (Blackmagic Desktop Video installed)
- Blackmagic DeckLink hardware
- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies)

The DeckLink SDK headers are vendored in the repo. The runtime library
(`libDeckLinkAPI.so`) is loaded at import time via `dlopen` — install
Desktop Video on the host.

## Install

```bash
uv pip install .
```

Or for development (editable build with test dependencies):

```bash
uv pip install -e ".[dev]"
```

### Devcontainer

A VS Code devcontainer provides a ready-to-code environment. It
bind-mounts the host's Desktop Video libraries and DeckLink device
nodes for hardware testing inside the container.

## Quick start

```python
import pydecklink

for mode in pydecklink.display_modes():
    print(f"{mode.name}: {mode.width}x{mode.height} @ {mode.fps:.2f}")
```

See `examples/passthrough_decklink.py` for a capture → playout loop.

## Running hardware tests

Hardware tests require a DeckLink card. They are excluded by default;
opt in with `-m hardware`.

```bash
uv run pytest -m hardware -v
```

## License

MIT — see [LICENSE](LICENSE).
