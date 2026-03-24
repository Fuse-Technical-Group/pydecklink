"""Shared fixtures for pyntv2 tests."""

from __future__ import annotations

import contextlib
import mmap
import os
from dataclasses import dataclass, field

import numpy as np
import pytest

from _helpers import APP_SIG, OEM_TASKS, page_aligned_buffer, stop_pair
from pyntv2 import Card


@dataclass
class LoopbackSession:
    """Card wrapper that tracks DMA buffers for automatic teardown."""

    card: Card
    _locked: list[np.ndarray] = field(default_factory=list, init=False)
    _backings: list[mmap.mmap] = field(default_factory=list, init=False)

    def alloc_buffer(self, size: int) -> tuple[mmap.mmap, np.ndarray]:
        """Allocate a page-aligned buffer, lock it for DMA, and track it."""
        mm, buf = page_aligned_buffer(size)
        self._backings.append(mm)
        self.card.dma_buffer_lock(buf)
        self._locked.append(buf)
        return mm, buf


@pytest.fixture()
def card():
    with Card(device_index=0) as c:
        yield c


@pytest.fixture()
def loopback_card():
    with Card(device_index=0) as c:
        c.acquire_stream_for_application(APP_SIG, os.getpid())
        c.set_every_frame_services(OEM_TASKS)
        session = LoopbackSession(card=c)
        try:
            yield session
        finally:
            stop_pair(c)
            for buf in session._locked:
                with contextlib.suppress(RuntimeError):
                    c.dma_buffer_unlock(buf)
            c.clear_routing()
            c.release_stream_for_application(APP_SIG, os.getpid())
