"""Retroactive CUDA pinning of SDK-allocated capture buffers.

Alternative to ``cuda_pinned_pipelined.py`` for consumers who can't (or
don't want to) plug in a custom allocator. The SDK allocates buffers
with its default malloc as usual; on the first time we see each
buffer pointer we call ``cudaHostRegister`` to retroactively pin it
into CUDA's pinned-memory pool. From then on H2D copies hit the fast
PCIe-DMA path the same as if the SDK had allocated via cudaHostAlloc.

When to prefer this over the allocator pattern:

* You're embedding pydecklink in a host that owns its own allocation
  policy and doesn't want a CUDA dependency leaking into capture
  setup.
* You don't control the buffer count up front (cudaHostRegister is
  per-pointer, on demand).

When to prefer ``cuda_pinned_pipelined.py`` instead:

* You want full control over allocation (alignment, NUMA placement,
  write-combining, cudaHostAllocPortable / cudaHostAllocMapped flags).
* You want to know exactly how many pinned-memory buffers exist
  (a custom allocator gives you this; pin-on-sight does not).
* You want the multi-threaded capture pipeline pattern.

This example is intentionally minimal: synchronous, no profiling, no
threading. For production-shaped capture see
``cuda_pinned_pipelined.py``.

Install:
    pip install pydecklink[cuda-examples]

Usage:
    python examples/cuda_register_pinned.py --device 0 --frames 60

Defaults to 4K UHD 59.94p / 10-bit YUV.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time

import pydecklink

_DEFAULT_MODE = pydecklink.DisplayMode.Mode4K2160p5994
_DEFAULT_PIXEL_FORMAT = pydecklink.PixelFormat.Format10BitYUV


def _check(err: object, op: str) -> None:
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: cudaError={code}")


def _print_status(line: str) -> None:
    sys.stdout.write(f"\r{line}\033[K")
    sys.stdout.flush()


def run_register(
    device_index: int = 0,
    mode: pydecklink.DisplayMode = _DEFAULT_MODE,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 60,
) -> None:
    """Open input, capture ``frame_count`` valid frames, register each
    unique buffer pointer with CUDA on first sight, and unregister all
    on shutdown."""
    from cuda.bindings import runtime as cudart

    dev = pydecklink.Device(index=device_index)
    dev.enable_video_input(
        mode=mode,
        pixel_format=pixel_format,
        zero_copy=True,
        input_queue_depth=1,
    )
    dev.start_streams()

    registered: dict[int, int] = {}  # ptr -> size
    stop = [False]

    def _on_sigint(_sig: int, _frame: object) -> None:
        stop[0] = True

    prev = signal.signal(signal.SIGINT, _on_sigint)

    captured = 0
    started = time.monotonic()
    last_status = 0.0
    try:
        while captured < frame_count and not stop[0]:
            frame = dev.pop_capture_frame_ref(timeout_ms=1000)
            now = time.monotonic()
            if frame is None or not frame.has_signal:
                if now - last_status >= 0.5:
                    elapsed = int(now - started)
                    state = "waiting for signal" if captured == 0 else "signal lost"
                    _print_status(
                        f"{state}: {elapsed}s elapsed, {captured}/{frame_count} frames"
                    )
                    last_status = now
                continue
            arr = frame.data
            ptr = int(arr.ctypes.data)
            size = int(arr.nbytes)
            if ptr not in registered:
                (err,) = cudart.cudaHostRegister(
                    ptr,
                    size,
                    cudart.cudaHostRegisterDefault,
                )
                _check(err, "cudaHostRegister")
                registered[ptr] = size
            captured += 1
            _print_status(f"capturing: {captured}/{frame_count} frames")
        sys.stdout.write("\n")
        sys.stdout.flush()
        suffix = " (interrupted)" if stop[0] else ""
        print(f"[register] frames={captured} unique_buffers={len(registered)}{suffix}")
    finally:
        dev.stop_streams()
        dev.disable_video_input()
        # Unregister every pointer we touched, BEFORE the SDK eventually
        # frees the underlying memory. The SDK does that when its
        # internal pool is torn down, after disable_video_input.
        for ptr in registered:
            (err,) = cudart.cudaHostUnregister(ptr)
            _check(err, "cudaHostUnregister")
        signal.signal(signal.SIGINT, prev)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroactively CUDA-pin SDK-allocated capture buffers.",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="DeckLink device index for capture.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=60,
        help="Number of valid frames to capture.",
    )
    parser.add_argument(
        "--pixel-format",
        choices=["8bit", "10bit"],
        default="10bit",
    )
    args = parser.parse_args()

    pixel_format = (
        pydecklink.PixelFormat.Format10BitYUV
        if args.pixel_format == "10bit"
        else pydecklink.PixelFormat.Format8BitYUV
    )

    devices = pydecklink.list_devices()
    if args.device >= len(devices):
        print(
            f"Device index {args.device} out of range ({len(devices)} devices found).",
            file=sys.stderr,
        )
        sys.exit(1)

    run_register(
        device_index=args.device,
        pixel_format=pixel_format,
        frame_count=args.frames,
    )


if __name__ == "__main__":
    main()
