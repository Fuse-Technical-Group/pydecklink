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
import resource
import struct


def _read_cap_set(name: str) -> int:
    """Read a capability set from /proc/self/status as an int."""
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(name + ":\t"):
                return int(line.split("\t")[1].strip(), 16)
    msg = f"capability set {name!r} not found in /proc/self/status"
    raise RuntimeError(msg)


def _has_cap(capset_hex: int, cap_number: int) -> bool:
    return bool(capset_hex & (1 << cap_number))


# Linux capability bit numbers (from linux/capability.h)
CAP_IPC_LOCK = 14
CAP_SYS_RAWIO = 17
CAP_SYS_ADMIN = 21


class TestCapabilities:
    """Validate --cap-add flags.

    Configured in: devcontainer.json runArgs (--cap-add=...).
    """

    def test_cap_sys_rawio(self) -> None:
        eff = _read_cap_set("CapEff")
        assert _has_cap(eff, CAP_SYS_RAWIO), (
            f"CAP_SYS_RAWIO (bit {CAP_SYS_RAWIO}) not in CapEff=0x{eff:x}"
        )

    def test_cap_sys_admin(self) -> None:
        eff = _read_cap_set("CapEff")
        assert _has_cap(eff, CAP_SYS_ADMIN), (
            f"CAP_SYS_ADMIN (bit {CAP_SYS_ADMIN}) not in CapEff=0x{eff:x}"
        )

    def test_cap_ipc_lock(self) -> None:
        eff = _read_cap_set("CapEff")
        assert _has_cap(eff, CAP_IPC_LOCK), (
            f"CAP_IPC_LOCK (bit {CAP_IPC_LOCK}) not in CapEff=0x{eff:x}"
        )


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
        one_gb = 1024 ** 3
        assert size_bytes >= one_gb, (
            f"/dev/shm is {size_bytes / (1024**2):.0f} MB, expected >= 1024 MB. "
            f"--shm-size=1g is not taking effect."
        )


class TestSeccomp:
    """Validate seccomp is disabled.

    Configured in: devcontainer.json runArgs
    (--security-opt=seccomp=unconfined).
    """

    def test_seccomp_unconfined(self) -> None:
        # /proc/self/status Seccomp field: 0=disabled, 1=strict, 2=filter
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("Seccomp:"):
                    mode = int(line.split(":")[1].strip())
                    assert mode == 0, (
                        f"Seccomp mode is {mode} (0=disabled, 2=filter). "
                        f"--security-opt=seccomp=unconfined is not taking effect."
                    )
                    return
        # If Seccomp line missing, kernel doesn't support it — fine.


class TestDevice:
    """Validate AJA device is mapped into container.

    Configured in: devcontainer.json runArgs (--device=/dev/ajantv20).
    """

    def test_aja_device_exists(self) -> None:
        assert os.path.exists("/dev/ajantv20"), (
            "/dev/ajantv20 not found. --device=/dev/ajantv20 is not taking effect "
            "or no AJA card is installed."
        )
