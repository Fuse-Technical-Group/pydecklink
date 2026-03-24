"""Convenience routing helpers for single-link capture and playout."""

from __future__ import annotations

from pyntv2._bindings import (
    Channel,
    InputSource,
    InputXpt,
    OutputDest,
    OutputXpt,
    PixelFormat,
)

# ── Lookup tables ────────────────────────────────────────────────────

# InputSource → SDI output crosspoint (the signal coming off the wire)
_INPUT_SOURCE_TO_OUTPUT_XPT: dict[InputSource, OutputXpt] = {
    InputSource.SDI1: OutputXpt.SDIIn1,
    InputSource.SDI2: OutputXpt.SDIIn2,
    InputSource.SDI3: OutputXpt.SDIIn3,
    InputSource.SDI4: OutputXpt.SDIIn4,
    InputSource.SDI5: OutputXpt.SDIIn5,
    InputSource.SDI6: OutputXpt.SDIIn6,
    InputSource.SDI7: OutputXpt.SDIIn7,
    InputSource.SDI8: OutputXpt.SDIIn8,
    InputSource.HDMI1: OutputXpt.HDMIIn1,
    InputSource.HDMI2: OutputXpt.HDMIIn2,
    InputSource.HDMI3: OutputXpt.HDMIIn3,
    InputSource.HDMI4: OutputXpt.HDMIIn4,
}

# Channel → FrameBuffer input crosspoint
_CHANNEL_TO_FB_INPUT: dict[Channel, InputXpt] = {
    Channel.CH1: InputXpt.FrameBuffer1Input,
    Channel.CH2: InputXpt.FrameBuffer2Input,
    Channel.CH3: InputXpt.FrameBuffer3Input,
    Channel.CH4: InputXpt.FrameBuffer4Input,
    Channel.CH5: InputXpt.FrameBuffer5Input,
    Channel.CH6: InputXpt.FrameBuffer6Input,
    Channel.CH7: InputXpt.FrameBuffer7Input,
    Channel.CH8: InputXpt.FrameBuffer8Input,
}

# Channel → FrameBuffer YUV output crosspoint
_CHANNEL_TO_FB_OUTPUT_YUV: dict[Channel, OutputXpt] = {
    Channel.CH1: OutputXpt.FrameBuffer1YUV,
    Channel.CH2: OutputXpt.FrameBuffer2YUV,
    Channel.CH3: OutputXpt.FrameBuffer3YUV,
    Channel.CH4: OutputXpt.FrameBuffer4YUV,
    Channel.CH5: OutputXpt.FrameBuffer5YUV,
    Channel.CH6: OutputXpt.FrameBuffer6YUV,
    Channel.CH7: OutputXpt.FrameBuffer7YUV,
    Channel.CH8: OutputXpt.FrameBuffer8YUV,
}

# Channel → FrameBuffer RGB output crosspoint
_CHANNEL_TO_FB_OUTPUT_RGB: dict[Channel, OutputXpt] = {
    Channel.CH1: OutputXpt.FrameBuffer1RGB,
    Channel.CH2: OutputXpt.FrameBuffer2RGB,
    Channel.CH3: OutputXpt.FrameBuffer3RGB,
    Channel.CH4: OutputXpt.FrameBuffer4RGB,
    Channel.CH5: OutputXpt.FrameBuffer5RGB,
    Channel.CH6: OutputXpt.FrameBuffer6RGB,
    Channel.CH7: OutputXpt.FrameBuffer7RGB,
    Channel.CH8: OutputXpt.FrameBuffer8RGB,
}

# Channel → CSC video input crosspoint
_CHANNEL_TO_CSC_VID_INPUT: dict[Channel, InputXpt] = {
    Channel.CH1: InputXpt.CSC1VidInput,
    Channel.CH2: InputXpt.CSC2VidInput,
    Channel.CH3: InputXpt.CSC3VidInput,
    Channel.CH4: InputXpt.CSC4VidInput,
    Channel.CH5: InputXpt.CSC5VidInput,
    Channel.CH6: InputXpt.CSC6VidInput,
    Channel.CH7: InputXpt.CSC7VidInput,
    Channel.CH8: InputXpt.CSC8VidInput,
}

# Channel → CSC YUV output crosspoint
_CHANNEL_TO_CSC_OUTPUT_YUV: dict[Channel, OutputXpt] = {
    Channel.CH1: OutputXpt.CSC1VidYUV,
    Channel.CH2: OutputXpt.CSC2VidYUV,
    Channel.CH3: OutputXpt.CSC3VidYUV,
    Channel.CH4: OutputXpt.CSC4VidYUV,
    Channel.CH5: OutputXpt.CSC5VidYUV,
    Channel.CH6: OutputXpt.CSC6VidYUV,
    Channel.CH7: OutputXpt.CSC7VidYUV,
    Channel.CH8: OutputXpt.CSC8VidYUV,
}

# Channel → CSC RGB output crosspoint
_CHANNEL_TO_CSC_OUTPUT_RGB: dict[Channel, OutputXpt] = {
    Channel.CH1: OutputXpt.CSC1VidRGB,
    Channel.CH2: OutputXpt.CSC2VidRGB,
    Channel.CH3: OutputXpt.CSC3VidRGB,
    Channel.CH4: OutputXpt.CSC4VidRGB,
    Channel.CH5: OutputXpt.CSC5VidRGB,
    Channel.CH6: OutputXpt.CSC6VidRGB,
    Channel.CH7: OutputXpt.CSC7VidRGB,
    Channel.CH8: OutputXpt.CSC8VidRGB,
}

# OutputDest → SDI output input crosspoint (the widget input feeding the connector)
_OUTPUT_DEST_TO_SDI_INPUT: dict[OutputDest, InputXpt] = {
    OutputDest.SDI1: InputXpt.SDIOut1Input,
    OutputDest.SDI2: InputXpt.SDIOut2Input,
    OutputDest.SDI3: InputXpt.SDIOut3Input,
    OutputDest.SDI4: InputXpt.SDIOut4Input,
    OutputDest.SDI5: InputXpt.SDIOut5Input,
    OutputDest.SDI6: InputXpt.SDIOut6Input,
    OutputDest.SDI7: InputXpt.SDIOut7Input,
    OutputDest.SDI8: InputXpt.SDIOut8Input,
    OutputDest.HDMI1: InputXpt.HDMIOutQ1Input,
}

# Pixel formats whose framebuffer stores RGB data
_RGB_PIXEL_FORMATS: frozenset[PixelFormat] = frozenset({
    PixelFormat.FBF_ARGB,
    PixelFormat.FBF_RGBA,
    PixelFormat.FBF_10BIT_RGB,
    PixelFormat.FBF_ABGR,
    PixelFormat.FBF_10BIT_DPX,
    PixelFormat.FBF_10BIT_DPX_LE,
    PixelFormat.FBF_24BIT_RGB,
    PixelFormat.FBF_24BIT_BGR,
    PixelFormat.FBF_48BIT_RGB,
    PixelFormat.FBF_12BIT_RGB_PACKED,
    PixelFormat.FBF_10BIT_RGB_PACKED,
    PixelFormat.FBF_10BIT_ARGB,
    PixelFormat.FBF_16BIT_ARGB,
    PixelFormat.FBF_10BIT_RAW_RGB,
})

# SDI carries YCbCr; HDMI can carry either but we assume YCbCr for
# routing purposes (the CSC handles conversion when needed).
_YCBCR_INPUT_SOURCES: frozenset[InputSource] = frozenset({
    InputSource.SDI1,
    InputSource.SDI2,
    InputSource.SDI3,
    InputSource.SDI4,
    InputSource.SDI5,
    InputSource.SDI6,
    InputSource.SDI7,
    InputSource.SDI8,
})


def _is_rgb(pixel_format: PixelFormat) -> bool:
    return pixel_format in _RGB_PIXEL_FORMATS


def _lookup(table: dict, key: object, param_name: str) -> object:
    """Look up *key* in *table*, raising ValueError on miss."""
    try:
        return table[key]
    except KeyError:
        raise ValueError(
            f"unsupported {param_name}: {key!r}"
        ) from None


def route_capture(
    source: InputSource,
    channel: Channel,
    pixel_format: PixelFormat,
) -> dict[InputXpt, OutputXpt]:
    """Build a crosspoint connection dict for single-link capture.

    Inserts a CSC widget when the input color space (YCbCr for SDI)
    differs from the framebuffer pixel format (RGB).
    """
    connections: dict[InputXpt, OutputXpt] = {}
    input_xpt = _lookup(_INPUT_SOURCE_TO_OUTPUT_XPT, source, "source")
    fb_input = _lookup(_CHANNEL_TO_FB_INPUT, channel, "channel")

    needs_csc = source in _YCBCR_INPUT_SOURCES and _is_rgb(pixel_format)

    if needs_csc:
        csc_input = _lookup(_CHANNEL_TO_CSC_VID_INPUT, channel, "channel")
        csc_output = _lookup(_CHANNEL_TO_CSC_OUTPUT_RGB, channel, "channel")
        connections[csc_input] = input_xpt
        connections[fb_input] = csc_output
    else:
        connections[fb_input] = input_xpt

    return connections


def route_playout(
    channel: Channel,
    output: OutputDest,
    pixel_format: PixelFormat,
) -> dict[InputXpt, OutputXpt]:
    """Build a crosspoint connection dict for single-link playout.

    Inserts a CSC widget when the framebuffer pixel format (RGB) differs
    from the output color space (YCbCr for SDI).
    """
    connections: dict[InputXpt, OutputXpt] = {}
    sdi_input = _lookup(_OUTPUT_DEST_TO_SDI_INPUT, output, "output")
    _lookup(_CHANNEL_TO_FB_OUTPUT_YUV, channel, "channel")  # validate channel early

    needs_csc = _is_rgb(pixel_format) and output not in {OutputDest.HDMI1}

    if needs_csc:
        fb_output = _CHANNEL_TO_FB_OUTPUT_RGB[channel]
        csc_input = _CHANNEL_TO_CSC_VID_INPUT[channel]
        csc_output = _CHANNEL_TO_CSC_OUTPUT_YUV[channel]
        connections[csc_input] = fb_output
        connections[sdi_input] = csc_output
    else:
        if _is_rgb(pixel_format):
            fb_output = _CHANNEL_TO_FB_OUTPUT_RGB[channel]
        else:
            fb_output = _CHANNEL_TO_FB_OUTPUT_YUV[channel]
        connections[sdi_input] = fb_output

    return connections
