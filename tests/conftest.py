"""Shared fixtures for pyntv2 tests."""

import pytest

from pyntv2 import Card


@pytest.fixture()
def card():
    with Card(device_index=0) as c:
        yield c
