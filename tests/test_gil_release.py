"""Blocking SDK calls run with the GIL released (no hardware required).

A binding that holds the GIL while the driver works stalls every other
Python thread in the process for the length of the call. An application
that schedules output on one thread and prepares the next frame on another
then sees its frame thread's timing absorb the driver's.

This reads the binding source rather than timing a call, so it runs on any
host: each call into the SDK that can wait on the driver must sit inside a
``nb::gil_scoped_release`` scope in its binding.
"""

import pathlib
import re

import pytest

_SOURCE = (
    pathlib.Path(__file__).parent.parent / "src" / "pydecklink_ext" / "bind_output.cpp"
)

# SDK calls that hand a frame to the driver or wait on it.
_BLOCKING = ("ScheduleVideoFrame", "DisplayVideoFrameSync")


def _bindings(text: str) -> dict[str, str]:
    """Each ``device.def("name", ...)`` binding's source, up to the next."""
    starts = [
        (m.start(), m.group(1)) for m in re.finditer(r'device\.def\("(\w+)"', text)
    ]
    ends = [s for s, _ in starts[1:]] + [len(text)]
    return {
        name: text[start:end] for (start, name), end in zip(starts, ends, strict=True)
    }


def _calls() -> list[tuple[str, str, str]]:
    found = []
    for name, body in _bindings(_SOURCE.read_text()).items():
        for call in _BLOCKING:
            for match in re.finditer(rf"\b{call}\(", body):
                found.append((name, call, body[: match.start()]))
    return found


def test_the_bindings_make_blocking_calls():
    """Guards the guard: a refactor that renames the bindings or moves them
    out of this file must not leave the test below checking nothing."""
    assert {call for _, call, _ in _calls()} == set(_BLOCKING)


@pytest.mark.parametrize(
    ("binding", "call", "before"),
    _calls(),
    ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "",
)
def test_a_blocking_sdk_call_runs_with_the_gil_released(binding, call, before):
    assert "nb::gil_scoped_release" in before, (
        f"{binding} calls {call} while holding the GIL; release it for the call"
    )
