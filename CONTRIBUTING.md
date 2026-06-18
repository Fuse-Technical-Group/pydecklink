# Contributing

## Platform build matrix

The DeckLink SDK headers are vendored in the repo. Install Blackmagic
Desktop Video on the host for all platforms.

| | Linux | macOS | Windows |
|---|---|---|---|
| Runtime library | `libDeckLinkAPI.so` loaded via `dlopen` | CoreFoundation plug-in via `DeckLinkAPIDispatch.cpp` | COM interfaces via `CoCreateInstance` |
| Build toolchain | C++ compiler, CMake | clang, CMake (links CoreFoundation) | MSVC, Windows SDK (provides MIDL), CMake |
| SDK artefacts | Pre-compiled headers + dispatch source | Pre-compiled headers + dispatch source | IDL files compiled to headers by MIDL at build time |

## Building from source

Editable build with the `dev` dependency group (pytest, mypy, psutil):

```bash
uv sync
```

### Windows

Building on Windows requires Visual Studio with the **Desktop development
with C++** workload (includes MSVC and the Windows SDK). CMake automatically
locates `midl.exe` from the Windows SDK to compile the vendored DeckLink IDL
files into C++ headers and COM stubs.

## Devcontainer (Linux)

A VS Code devcontainer provides a ready-to-code environment. It bind-mounts
the host's Desktop Video libraries and DeckLink device nodes for hardware
testing inside the container.

The container exposes Blackmagic's firmware tooling on `PATH` via
`/var/lib/blackmagic/bin`. `BlackmagicFirmwareUpdater` and
`DesktopVideoUpdateTool` are the same multi-call binary dispatched on
`argv[0]`; prefer `DesktopVideoUpdateTool` for scripted invocations — its
flag interface (`--list`, `--device ID`, `--all`, `--quiet`) is the
automation-friendly surface. `BlackmagicFirmwareUpdater` is the interactive
shorthand (`status`, `update [device]`).

## Running hardware tests

Hardware tests require a DeckLink card. They are excluded by default; opt in
with `-m hardware`:

```bash
uv run pytest -m hardware -v
```
