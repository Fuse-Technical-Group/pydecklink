"""Tests for Card class bindings (no hardware required)."""

import pytest

from pyntv2 import (
    AudioSystem,
    Card,
    Channel,
    InputSource,
    InputXpt,
    Mode,
    OutputXpt,
    PixelFormat,
    ReferenceSource,
    VideoFormat,
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


class TestCardMethodsExist:
    """Verify all expected methods are bound and callable attributes."""

    @pytest.fixture()
    def card(self):
        return Card()

    def test_lifecycle_methods(self, card):
        assert callable(card.open)
        assert callable(card.close)

    def test_format_methods(self, card):
        assert callable(card.get_input_video_format)
        assert callable(card.set_video_format)
        assert callable(card.set_frame_buffer_format)
        assert callable(card.enable_channel)
        assert callable(card.set_mode)
        assert callable(card.set_sdi_transmit_enable)
        assert callable(card.set_reference)

    def test_routing_methods(self, card):
        assert callable(card.connect)
        assert callable(card.disconnect)
        assert callable(card.clear_routing)
        assert callable(card.apply_signal_route)

    def test_autocirculate_methods(self, card):
        assert callable(card.autocirculate_init_for_input)
        assert callable(card.autocirculate_init_for_output)
        assert callable(card.autocirculate_start)
        assert callable(card.autocirculate_stop)
        assert callable(card.autocirculate_get_status)
        assert callable(card.autocirculate_transfer)

    def test_vbi_methods(self, card):
        assert callable(card.wait_for_input_vertical_interrupt)
        assert callable(card.wait_for_output_vertical_interrupt)

    def test_dma_methods(self, card):
        assert callable(card.dma_buffer_lock)
        assert callable(card.dma_buffer_unlock)

    def test_identity_properties(self, card):
        assert hasattr(card, "device_id")
        assert hasattr(card, "display_name")


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
    """Verify frame_count < 3 raises InvalidArgumentError."""

    @pytest.fixture()
    def card(self):
        return Card()

    def test_init_for_input_frame_count_zero(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_input(Channel.CH1, frame_count=0)

    def test_init_for_input_frame_count_one(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_input(Channel.CH1, frame_count=1)

    def test_init_for_input_frame_count_two(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_input(Channel.CH1, frame_count=2)

    def test_init_for_output_frame_count_zero(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_output(Channel.CH1, frame_count=0)

    def test_init_for_output_frame_count_one(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_output(Channel.CH1, frame_count=1)

    def test_init_for_output_frame_count_two(self, card):
        with pytest.raises(ValueError, match="frame_count must be >= 3"):
            card.autocirculate_init_for_output(Channel.CH1, frame_count=2)
