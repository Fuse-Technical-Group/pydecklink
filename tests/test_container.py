"""Container environment tests — validate devcontainer config takes effect.

Run with: pytest tests/test_container.py -v

Every container setting that the hardware tests depend on gets a test
here.  Each test docstring states where the setting is configured so
you know what to fix when it breaks.

Settings may live in two places:
  - .devcontainer/devcontainer.json  (runArgs — runtime flags)
  - .devcontainer/Dockerfile          (image-level config)

The devcontainer CLI does not faithfully pass all runArgs to
Podman/Docker.  When a runtime flag is silently dropped, the fix
is to move the setting into the Dockerfile.  These tests catch that.
"""

from __future__ import annotations

import os
import sys

import pytest

if sys.platform == "win32":
    pytest.skip("Linux container tests", allow_module_level=True)

import resource  # noqa: E402  # Unix-only; guarded above

pytestmark = pytest.mark.hardware


class TestUlimits:
    """Validate memlock ulimit.

    Configured in: Dockerfile (/etc/security/limits.conf).
    The devcontainer CLI silently drops --ulimit=memlock=-1:-1 from
    runArgs, so this is set image-side instead.
    """

    def test_memlock_unlimited(self) -> None:
        soft, hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        # -1 in podman/docker maps to RLIM_INFINITY
        assert hard == resource.RLIM_INFINITY, (
            f"memlock hard limit is {hard} bytes ({hard // 1024} KB), "
            f"expected unlimited (-1). "
            f"--ulimit=memlock=-1:-1 is not taking effect."
        )
        assert soft == resource.RLIM_INFINITY, (
            f"memlock soft limit is {soft} bytes ({soft // 1024} KB), "
            f"expected unlimited (-1)."
        )


class TestSharedMemory:
    """Validate shared memory size.

    Configured in: devcontainer.json runArgs (--shm-size=1g).
    """

    def test_shm_size_at_least_1g(self) -> None:
        stat = os.statvfs("/dev/shm")
        size_bytes = stat.f_blocks * stat.f_frsize
        one_gb = 1024**3
        assert size_bytes >= one_gb, (
            f"/dev/shm is {size_bytes / (1024**2):.0f} MB, expected >= 1024 MB. "
            f"--shm-size=1g is not taking effect."
        )


class TestDevice:
    """Validate AJA device is mapped into container.

    Configured in: devcontainer.json runArgs (--device=/dev/ajantv20).
    """

    def test_aja_device_exists(self) -> None:
        assert os.path.exists("/dev/ajantv20"), (
            "/dev/ajantv20 not found. --device=/dev/ajantv20 is not taking effect "
            "or no AJA card is installed."
        )

    def test_aja_device_readable(self) -> None:
        assert os.access("/dev/ajantv20", os.R_OK | os.W_OK), (
            "/dev/ajantv20 exists but is not readable/writable. "
            "Check --userns=keep-id and device node permissions (expect mode 666)."
        )
