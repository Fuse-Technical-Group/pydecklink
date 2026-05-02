# CUDA devcontainer

Side-by-side variant of `.devcontainer/` with NVIDIA GPU passthrough,
for verifying `examples/cuda_pinned_capture.py` against real DeckLink
hardware + a CUDA GPU. The default devcontainer stays slim (no CUDA
toolkit). Use this one only when running CUDA-touching examples or
adding new ones.

## When to use this container

- Running `examples/cuda_pinned_capture.py` end-to-end against a
  DeckLink card and a CUDA GPU.
- Validating SPEC §gpu-pinned-memory claims (zero-copy DMA from
  DeckLink into pinned host memory).
- Iterating on `tests/test_examples_cuda.py` (the
  `pytest.importorskip("cuda")`-gated smoke test, which skips in the
  default container and runs here).

For everything else — daily development, `uv run pytest`, mypy, building
the binding — use the default `.devcontainer/`. It builds faster, has
no GPU dependency, and the unit test suite covers the allocator's
recycle semantics without needing CUDA.

## Host pre-requisites

- NVIDIA Container Toolkit installed.
- CDI spec generated:
  ```sh
  sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
  ```
  Re-run after driver upgrades.
- Blackmagic Desktop Video driver loaded (same as the slim devcontainer).

## Reopening in this container

VS Code: `Dev Containers: Reopen in Container` and pick `pydecklink (CUDA)`
from the list.

CLI:

```sh
devcontainer up --config .devcontainer/cuda/devcontainer.json --workspace-folder .
```

## Verification recipe

Inside the container:

```sh
uv sync --extra cuda-examples         # pulls cuda-python from the optional extra
uv run python -c "from cuda.bindings import runtime as cudart; \
    err, n = cudart.cudaGetDeviceCount(); print(err, n)"
ls /dev/blackmagic                     # io0..ioN should be present
uv run python examples/cuda_pinned_capture.py --mode=alloc
uv run python examples/cuda_pinned_capture.py --mode=register
uv run pytest tests/test_examples_cuda.py -v   # should run, not skip
```

Expected: `cudaGetDeviceCount` returns `(<cudaSuccess>, N>=1)`, both
`--mode` runs report frame arrivals, and the smoke test passes (does
not skip).

## Image / runtime choices

- **Base:** `nvidia/cuda:13.0.0-runtime-ubuntu24.04`. Runtime, not
  devel — `cuda-python` links to `libcudart.so` via `dlopen`, no `nvcc`
  needed. CUDA 13 matches `cuda-python` latest on PyPI; the optional
  pyproject extra (`cuda-examples = ["cuda-python>=12"]`) stays loose.
  If a downstream tool ever forces CUDA 12 (e.g. ONNX Runtime lags
  major CUDA bumps), swap the base tag and pin
  `cuda-python>=12,<13` in `pyproject.toml`.
- **GPU passthrough:** CDI (`--device=nvidia.com/gpu=all`) for podman
  + NVIDIA Container Toolkit. The legacy `--gpus=all` is Docker-only.
- **Memlock unlimited:** baked into `/etc/security/limits.conf` because
  the devcontainer CLI silently drops `--ulimit` runArgs. `cudaHostAlloc`
  pins pages; DeckLink DMA also wants page-locked memory; the default
  `RLIMIT_MEMLOCK` (~64 MB) blows up around the third 1080p buffer.
- **`--userns=keep-id`:** preserves the host UID through to the kernel
  so DMA via `get_user_pages()` (used by both the DeckLink driver and
  the NVIDIA driver for pinned memory) sees the real user, not a
  subordinate UID from podman's default mapping.
- **`NVIDIA_DRIVER_CAPABILITIES=compute,utility`:** `compute` for CUDA
  runtime, `utility` for `nvidia-smi`. `video` (NVENC/NVDEC) is omitted
  — pydecklink doesn't transcode.
- **Distinct Claude state volume:** `claude-config-cuda-${devcontainerId}`
  so this container's session state doesn't collide with the slim
  container's.

## Why pydecklink is not "the CUDA wrapper"

pydecklink itself imports zero GPU toolkits (SPEC.md §gpu-pinned-memory).
The allocator API takes plain `alloc(size) → ptr` / `free(ptr, size)`
callables. CUDA, HIP, and Intel Level Zero all fit that interface;
the consumer brings their toolkit. This container exists only to
verify the example ships correctly — not because pydecklink depends
on CUDA.
