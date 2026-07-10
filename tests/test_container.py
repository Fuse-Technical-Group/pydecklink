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

if sys.platform != "linux":
    # These validate the Linux devcontainer (memlock ulimit, /dev/blackmagic
    # device nodes). They are meaningless off Linux — macOS/Windows hosts run
    # the binding natively, not in the container.
    pytest.skip("Linux devcontainer tests", allow_module_level=True)

import resource  # Unix-only; guarded above

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


class TestDevice:
    """Validate DeckLink devices are mapped into container.

    Configured in: devcontainer.json runArgs (--device=/dev/blackmagic).
    Podman passes the directory through as char nodes /dev/blackmagic/io0..ioN.
    """

    DEVICE = "/dev/blackmagic/io0"

    def test_blackmagic_device_exists(self) -> None:
        assert os.path.exists(self.DEVICE), (
            f"{self.DEVICE} not found. --device=/dev/blackmagic is not taking "
            f"effect or no DeckLink card is installed."
        )

    def test_blackmagic_device_readable(self) -> None:
        assert os.access(self.DEVICE, os.R_OK | os.W_OK), (
            f"{self.DEVICE} exists but is not readable/writable. "
            f"Check --userns=keep-id and device node permissions (expect mode 666)."
        )
