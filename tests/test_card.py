"""Tests for Card class bindings (no hardware required)."""

import pytest

from pyntv2 import (
    Card,
    Channel,
    Mode,
)


class TestCardConstruction:
    def test_default_constructor(self):
        card = Card()
        assert card.is_open is False

    def test_context_manager_protocol(self):
        card = Card()
        with card as c:
            assert c is card
        assert card.is_open is False


class TestCardTypeErrors:
    """Verify wrong enum types raise TypeError."""

    @pytest.fixture()
    def card(self):
        return Card()

    def test_set_mode_wrong_type(self, card):
        with pytest.raises(TypeError):
            card.set_mode("not_a_channel", Mode.CAPTURE)

    def test_set_video_format_wrong_type(self, card):
        with pytest.raises(TypeError):
            card.set_video_format("not_a_format")

    def test_connect_wrong_types(self, card):
        with pytest.raises(TypeError):
            card.connect(42, 43)


class TestFrameCountValidation:
    """Verify frame_count < 3 raises ValueError."""

    @pytest.fixture()
    def card(self):
        return Card()

    @pytest.mark.parametrize("frame_count", [0, 1, 2])
    def test_init_for_input_rejects_low_frame_count(self, card, frame_count):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_input(Channel.CH1, frame_count=frame_count)

    @pytest.mark.parametrize("frame_count", [0, 1, 2])
    def test_init_for_output_rejects_low_frame_count(self, card, frame_count):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_output(Channel.CH1, frame_count=frame_count)
