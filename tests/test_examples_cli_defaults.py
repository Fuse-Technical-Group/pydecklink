"""Regression tests for example CLI default-bound behavior.

Both ``cuda_passthrough.py`` and ``cuda_loopback_latency.py`` advertise
``--frames 0``/``--duration 0`` as "unlimited (use --duration or
Ctrl-C)" via their argparse ``help`` strings. Earlier revisions of
``main()`` silently autoset ``args.duration`` (to 5.0 and 30.0
respectively) when both bounds were left at the default, which
contradicted that contract — invocations without explicit bounds
exited after a few seconds instead of running until SIGINT.

Per §spec:canonical-gpu-passthrough and §spec:latency-characterization
(workstream §road:examples-default-indefinite), unbound invocations
shall run until SIGINT. The run loops in ``run_passthrough`` /
``run_loopback`` already treat ``(frame_count=0, duration_seconds=0)``
as unbounded; the regression lived in the CLI shim only.

These tests are source-level — they assert the autoset pattern is
absent from each example. They run on any host (no cuda required),
in contrast with the peer ``test_examples_cuda_passthrough.py`` and
``test_cuda_loopback_latency.py`` which gate on ``importorskip("cuda")``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize(
    "example_name",
    ["cuda_passthrough.py", "cuda_loopback_latency.py"],
)
def test_main_does_not_autoset_duration_when_unbounded(example_name: str) -> None:
    """``main()`` shall not assign a non-zero ``args.duration`` default
    when both ``--frames`` and ``--duration`` are left at zero. The
    argparse ``default=0`` already encodes the "unlimited" contract;
    the run loop honors it; the CLI shim must not override it."""
    source = (EXAMPLES_DIR / example_name).read_text()
    assert "args.duration =" not in source, (
        f"{example_name}: main() reassigns args.duration, contradicting "
        f"the '0 = unlimited' help text. Remove the autoset block so "
        f"unbound invocations run until SIGINT."
    )


@pytest.mark.parametrize(
    "example_name",
    ["cuda_passthrough.py", "cuda_loopback_latency.py"],
)
def test_argparse_help_advertises_zero_as_unlimited(example_name: str) -> None:
    """Belt-and-braces: the help text shall keep advertising the
    unbounded contract. If a future edit changes the help text away
    from '0 = unlimited' the autoset-removal regression test stops
    being meaningful — guard the contract on both sides."""
    source = (EXAMPLES_DIR / example_name).read_text()
    assert "0 = unlimited" in source, (
        f"{example_name}: --frames/--duration help no longer advertises "
        f"'0 = unlimited'. Update the help text or the contract."
    )
