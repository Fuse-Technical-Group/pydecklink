#include "bind_enums.h"
#include "platform.h"

void init_decklink_enums(nb::module_& m) {

    // -- BMDDisplayMode --
    // The SDK defines these as typedef uint32_t with an unnamed enum.
    // Use _BMDDisplayMode (the actual enum type) for nanobind.
    nb::enum_<_BMDDisplayMode>(m, "DisplayMode")
        // SD
        .value("NTSC", bmdModeNTSC)
        .value("NTSC2398", bmdModeNTSC2398)
        .value("PAL", bmdModePAL)
        .value("NTSCp", bmdModeNTSCp)
        .value("PALp", bmdModePALp)
        // HD 1080
        .value("HD1080p2398", bmdModeHD1080p2398)
        .value("HD1080p24", bmdModeHD1080p24)
        .value("HD1080p25", bmdModeHD1080p25)
        .value("HD1080p2997", bmdModeHD1080p2997)
        .value("HD1080p30", bmdModeHD1080p30)
        .value("HD1080p4795", bmdModeHD1080p4795)
        .value("HD1080p48", bmdModeHD1080p48)
        .value("HD1080p50", bmdModeHD1080p50)
        .value("HD1080p5994", bmdModeHD1080p5994)
        .value("HD1080p6000", bmdModeHD1080p6000)
        .value("HD1080p9590", bmdModeHD1080p9590)
        .value("HD1080p96", bmdModeHD1080p96)
        .value("HD1080p100", bmdModeHD1080p100)
        .value("HD1080p11988", bmdModeHD1080p11988)
        .value("HD1080p120", bmdModeHD1080p120)
        .value("HD1080i50", bmdModeHD1080i50)
        .value("HD1080i5994", bmdModeHD1080i5994)
        .value("HD1080i6000", bmdModeHD1080i6000)
        // HD 720
        .value("HD720p50", bmdModeHD720p50)
        .value("HD720p5994", bmdModeHD720p5994)
        .value("HD720p60", bmdModeHD720p60)
        // 2K
        .value("Mode2k2398", bmdMode2k2398)
        .value("Mode2k24", bmdMode2k24)
        .value("Mode2k25", bmdMode2k25)
        // 2K DCI
        .value("Mode2kDCI2398", bmdMode2kDCI2398)
        .value("Mode2kDCI24", bmdMode2kDCI24)
        .value("Mode2kDCI25", bmdMode2kDCI25)
        .value("Mode2kDCI2997", bmdMode2kDCI2997)
        .value("Mode2kDCI30", bmdMode2kDCI30)
        .value("Mode2kDCI4795", bmdMode2kDCI4795)
        .value("Mode2kDCI48", bmdMode2kDCI48)
        .value("Mode2kDCI50", bmdMode2kDCI50)
        .value("Mode2kDCI5994", bmdMode2kDCI5994)
        .value("Mode2kDCI60", bmdMode2kDCI60)
        .value("Mode2kDCI9590", bmdMode2kDCI9590)
        .value("Mode2kDCI96", bmdMode2kDCI96)
        .value("Mode2kDCI100", bmdMode2kDCI100)
        .value("Mode2kDCI11988", bmdMode2kDCI11988)
        .value("Mode2kDCI120", bmdMode2kDCI120)
        // 4K UHD
        .value("Mode4K2160p2398", bmdMode4K2160p2398)
        .value("Mode4K2160p24", bmdMode4K2160p24)
        .value("Mode4K2160p25", bmdMode4K2160p25)
        .value("Mode4K2160p2997", bmdMode4K2160p2997)
        .value("Mode4K2160p30", bmdMode4K2160p30)
        .value("Mode4K2160p4795", bmdMode4K2160p4795)
        .value("Mode4K2160p48", bmdMode4K2160p48)
        .value("Mode4K2160p50", bmdMode4K2160p50)
        .value("Mode4K2160p5994", bmdMode4K2160p5994)
        .value("Mode4K2160p60", bmdMode4K2160p60)
        .value("Mode4K2160p9590", bmdMode4K2160p9590)
        .value("Mode4K2160p96", bmdMode4K2160p96)
        .value("Mode4K2160p100", bmdMode4K2160p100)
        .value("Mode4K2160p11988", bmdMode4K2160p11988)
        .value("Mode4K2160p120", bmdMode4K2160p120)
        // 4K DCI
        .value("Mode4kDCI2398", bmdMode4kDCI2398)
        .value("Mode4kDCI24", bmdMode4kDCI24)
        .value("Mode4kDCI25", bmdMode4kDCI25)
        .value("Mode4kDCI2997", bmdMode4kDCI2997)
        .value("Mode4kDCI30", bmdMode4kDCI30)
        .value("Mode4kDCI4795", bmdMode4kDCI4795)
        .value("Mode4kDCI48", bmdMode4kDCI48)
        .value("Mode4kDCI50", bmdMode4kDCI50)
        .value("Mode4kDCI5994", bmdMode4kDCI5994)
        .value("Mode4kDCI60", bmdMode4kDCI60)
        .value("Mode4kDCI9590", bmdMode4kDCI9590)
        .value("Mode4kDCI96", bmdMode4kDCI96)
        .value("Mode4kDCI100", bmdMode4kDCI100)
        .value("Mode4kDCI11988", bmdMode4kDCI11988)
        .value("Mode4kDCI120", bmdMode4kDCI120)
        // 8K UHD
        .value("Mode8K4320p2398", bmdMode8K4320p2398)
        .value("Mode8K4320p24", bmdMode8K4320p24)
        .value("Mode8K4320p25", bmdMode8K4320p25)
        .value("Mode8K4320p2997", bmdMode8K4320p2997)
        .value("Mode8K4320p30", bmdMode8K4320p30)
        .value("Mode8K4320p4795", bmdMode8K4320p4795)
        .value("Mode8K4320p48", bmdMode8K4320p48)
        .value("Mode8K4320p50", bmdMode8K4320p50)
        .value("Mode8K4320p5994", bmdMode8K4320p5994)
        .value("Mode8K4320p60", bmdMode8K4320p60)
        // 8K DCI
        .value("Mode8kDCI2398", bmdMode8kDCI2398)
        .value("Mode8kDCI24", bmdMode8kDCI24)
        .value("Mode8kDCI25", bmdMode8kDCI25)
        .value("Mode8kDCI2997", bmdMode8kDCI2997)
        .value("Mode8kDCI30", bmdMode8kDCI30)
        .value("Mode8kDCI4795", bmdMode8kDCI4795)
        .value("Mode8kDCI48", bmdMode8kDCI48)
        .value("Mode8kDCI50", bmdMode8kDCI50)
        .value("Mode8kDCI5994", bmdMode8kDCI5994)
        .value("Mode8kDCI60", bmdMode8kDCI60)
        // PC modes (representative subset)
        .value("Mode640x480p60", bmdMode640x480p60)
        .value("Mode1920x1200p60", bmdMode1920x1200p60)
        // Special
        .value("Unknown", bmdModeUnknown);

    // -- BMDPixelFormat --
    nb::enum_<_BMDPixelFormat>(m, "PixelFormat")
        .value("Unspecified", bmdFormatUnspecified)
        .value("Format8BitYUV", bmdFormat8BitYUV)
        .value("Format10BitYUV", bmdFormat10BitYUV)
        .value("Format10BitYUVA", bmdFormat10BitYUVA)
        .value("Format8BitARGB", bmdFormat8BitARGB)
        .value("Format8BitBGRA", bmdFormat8BitBGRA)
        .value("Format10BitRGB", bmdFormat10BitRGB)
        .value("Format12BitRGB", bmdFormat12BitRGB)
        .value("Format12BitRGBLE", bmdFormat12BitRGBLE)
        .value("Format10BitRGBXLE", bmdFormat10BitRGBXLE)
        .value("Format10BitRGBX", bmdFormat10BitRGBX)
        .value("FormatH265", bmdFormatH265)
        .value("FormatDNxHR", bmdFormatDNxHR);

    // -- BMDFieldDominance --
    nb::enum_<_BMDFieldDominance>(m, "FieldDominance")
        .value("Unknown", bmdUnknownFieldDominance)
        .value("LowerFieldFirst", bmdLowerFieldFirst)
        .value("UpperFieldFirst", bmdUpperFieldFirst)
        .value("ProgressiveFrame", bmdProgressiveFrame)
        .value("ProgressiveSegmentedFrame", bmdProgressiveSegmentedFrame);

    // -- BMDVideoInputFlags --
    nb::enum_<_BMDVideoInputFlags>(m, "VideoInputFlag")
        .value("Default", bmdVideoInputFlagDefault)
        .value("EnableFormatDetection", bmdVideoInputEnableFormatDetection)
        .value("DualStream3D", bmdVideoInputDualStream3D)
        .value("SynchronizeToCaptureGroup", bmdVideoInputSynchronizeToCaptureGroup);

    // -- BMDVideoOutputFlags --
    nb::enum_<_BMDVideoOutputFlags>(m, "VideoOutputFlag", nb::is_arithmetic())
        .value("Default", bmdVideoOutputFlagDefault)
        .value("VANC", bmdVideoOutputVANC)
        .value("VITC", bmdVideoOutputVITC)
        .value("RP188", bmdVideoOutputRP188)
        .value("DualStream3D", bmdVideoOutputDualStream3D)
        .value("SynchronizeToPlaybackGroup", bmdVideoOutputSynchronizeToPlaybackGroup)
        .value("DolbyVision", bmdVideoOutputDolbyVision);

    // -- BMDFrameFlags --
    nb::enum_<_BMDFrameFlags>(m, "FrameFlag")
        .value("Default", bmdFrameFlagDefault)
        .value("FlipVertical", bmdFrameFlagFlipVertical)
        .value("MonitorOutOnly", bmdFrameFlagMonitorOutOnly)
        .value("ContainsHDRMetadata", bmdFrameContainsHDRMetadata)
        .value("ContainsDolbyVisionMetadata", bmdFrameContainsDolbyVisionMetadata)
        .value("CapturedAsPsF", bmdFrameCapturedAsPsF)
        .value("HasNoInputSource", bmdFrameHasNoInputSource);

    // -- BMDDetectedVideoInputFormatFlags --
    nb::enum_<_BMDDetectedVideoInputFormatFlags>(m, "DetectedInputFormat")
        .value("YCbCr422", bmdDetectedVideoInputYCbCr422)
        .value("RGB444", bmdDetectedVideoInputRGB444)
        .value("DualStream3D", bmdDetectedVideoInputDualStream3D)
        .value("Depth12Bit", bmdDetectedVideoInput12BitDepth)
        .value("Depth10Bit", bmdDetectedVideoInput10BitDepth)
        .value("Depth8Bit", bmdDetectedVideoInput8BitDepth);

    // -- BMDOutputFrameCompletionResult --
    nb::enum_<_BMDOutputFrameCompletionResult>(m, "OutputFrameResult")
        .value("Completed", bmdOutputFrameCompleted)
        .value("DisplayedLate", bmdOutputFrameDisplayedLate)
        .value("Dropped", bmdOutputFrameDropped)
        .value("Flushed", bmdOutputFrameFlushed);

    // -- BMDVideoIOSupport --
    nb::enum_<_BMDVideoIOSupport>(m, "VideoIOSupport")
        .value("Capture", bmdDeviceSupportsCapture)
        .value("Playback", bmdDeviceSupportsPlayback);

    // -- BMDDeckLinkConfigurationID (subset relevant to phase 1) --
    nb::enum_<_BMDDeckLinkConfigurationID>(m, "ConfigurationID")
        // Video output flags
        .value("Config444SDIVideoOutput", bmdDeckLinkConfig444SDIVideoOutput)
        .value("ConfigLowLatencyVideoOutput", bmdDeckLinkConfigLowLatencyVideoOutput)
        .value("ConfigSMPTELevelAOutput", bmdDeckLinkConfigSMPTELevelAOutput)
        .value("ConfigRec2020Output", bmdDeckLinkConfigRec2020Output)
        .value("ConfigOutput1080pAsPsF", bmdDeckLinkConfigOutput1080pAsPsF)
        // Video output integers
        .value("ConfigVideoOutputConnection", bmdDeckLinkConfigVideoOutputConnection)
        .value("ConfigVideoOutputConversionMode", bmdDeckLinkConfigVideoOutputConversionMode)
        .value("ConfigVideoOutputIdleOperation", bmdDeckLinkConfigVideoOutputIdleOperation)
        .value("ConfigSDIOutputLinkConfiguration", bmdDeckLinkConfigSDIOutputLinkConfiguration)
        // Video input flags
        .value("ConfigUseDedicatedLTCInput", bmdDeckLinkConfigUseDedicatedLTCInput)
        .value("ConfigCapture1080pAsPsF", bmdDeckLinkConfigCapture1080pAsPsF)
        // Video input integers
        .value("ConfigVideoInputConnection", bmdDeckLinkConfigVideoInputConnection)
        .value("ConfigCapturePassThroughMode", bmdDeckLinkConfigCapturePassThroughMode)
        // Serial port
        .value("ConfigSwapSerialRxTx", bmdDeckLinkConfigSwapSerialRxTx);

    // -- BMDDeckLinkAttributeID (subset relevant to phase 1) --
    nb::enum_<_BMDDeckLinkAttributeID>(m, "AttributeID")
        // Flags
        .value("SupportsInternalKeying", BMDDeckLinkSupportsInternalKeying)
        .value("SupportsExternalKeying", BMDDeckLinkSupportsExternalKeying)
        .value("SupportsInputFormatDetection", BMDDeckLinkSupportsInputFormatDetection)
        .value("HasReferenceInput", BMDDeckLinkHasReferenceInput)
        .value("SupportsHDRMetadata", BMDDeckLinkSupportsHDRMetadata)
        .value("SupportsColorspaceMetadata", BMDDeckLinkSupportsColorspaceMetadata)
        .value("SupportsIdleOutput", BMDDeckLinkSupportsIdleOutput)
        .value("SupportsSMPTELevelAOutput", BMDDeckLinkSupportsSMPTELevelAOutput)
        // Integers
        .value("MaximumAudioChannels", BMDDeckLinkMaximumAudioChannels)
        .value("NumberOfSubDevices", BMDDeckLinkNumberOfSubDevices)
        .value("SubDeviceIndex", BMDDeckLinkSubDeviceIndex)
        .value("PersistentID", BMDDeckLinkPersistentID)
        .value("VideoOutputConnections", BMDDeckLinkVideoOutputConnections)
        .value("VideoInputConnections", BMDDeckLinkVideoInputConnections)
        .value("VideoIOSupport", BMDDeckLinkVideoIOSupport)
        .value("DeviceInterface", BMDDeckLinkDeviceInterface)
        .value("Duplex", BMDDeckLinkDuplex)
        .value("MinimumPrerollFrames", BMDDeckLinkMinimumPrerollFrames)
        .value("ProfileID", BMDDeckLinkProfileID)
        // Strings
        .value("VendorName", BMDDeckLinkVendorName)
        .value("DisplayName", BMDDeckLinkDisplayName)
        .value("ModelName", BMDDeckLinkModelName)
        .value("DeviceHandle", BMDDeckLinkDeviceHandle);

    // -- BMDDisplayModeFlags --
    nb::enum_<_BMDDisplayModeFlags>(m, "DisplayModeFlag")
        .value("Supports3D", bmdDisplayModeSupports3D)
        .value("ColorspaceRec601", bmdDisplayModeColorspaceRec601)
        .value("ColorspaceRec709", bmdDisplayModeColorspaceRec709)
        .value("ColorspaceRec2020", bmdDisplayModeColorspaceRec2020);

    // -- BMDVideoConnection --
    nb::enum_<_BMDVideoConnection>(m, "VideoConnection")
        .value("Unspecified", bmdVideoConnectionUnspecified)
        .value("SDI", bmdVideoConnectionSDI)
        .value("HDMI", bmdVideoConnectionHDMI)
        .value("OpticalSDI", bmdVideoConnectionOpticalSDI)
        .value("Component", bmdVideoConnectionComponent)
        .value("Composite", bmdVideoConnectionComposite)
        .value("SVideo", bmdVideoConnectionSVideo)
        .value("Ethernet", bmdVideoConnectionEthernet)
        .value("OpticalEthernet", bmdVideoConnectionOpticalEthernet)
        .value("Internal", bmdVideoConnectionInternal);

    // -- BMDDuplexMode --
    nb::enum_<_BMDDuplexMode>(m, "DuplexMode")
        .value("Full", bmdDuplexFull)
        .value("Half", bmdDuplexHalf)
        .value("Simplex", bmdDuplexSimplex)
        .value("Inactive", bmdDuplexInactive);

    // -- BMDSupportedVideoModeFlags --
    nb::enum_<_BMDSupportedVideoModeFlags>(m, "SupportedVideoModeFlag")
        .value("Default", bmdSupportedVideoModeDefault)
        .value("Keying", bmdSupportedVideoModeKeying)
        .value("DualStream3D", bmdSupportedVideoModeDualStream3D)
        .value("SDISingleLink", bmdSupportedVideoModeSDISingleLink)
        .value("SDIDualLink", bmdSupportedVideoModeSDIDualLink);

    // -- BMDVideoOutputConversionMode --
    nb::enum_<_BMDVideoOutputConversionMode>(m, "VideoOutputConversionMode")
        .value("NoConversion", bmdNoVideoOutputConversion)
        .value("LetterboxDownconversion", bmdVideoOutputLetterboxDownconversion)
        .value("AnamorphicDownconversion", bmdVideoOutputAnamorphicDownconversion)
        .value("HD720toHD1080", bmdVideoOutputHD720toHD1080Conversion)
        .value("HardwareLetterboxDownconversion", bmdVideoOutputHardwareLetterboxDownconversion)
        .value("HardwareAnamorphicDownconversion", bmdVideoOutputHardwareAnamorphicDownconversion)
        .value("HardwareCenterCutDownconversion", bmdVideoOutputHardwareCenterCutDownconversion)
        .value("Hardware720p1080pCrossconversion", bmdVideoOutputHardware720p1080pCrossconversion)
        .value("HardwareAnamorphic720pUpconversion", bmdVideoOutputHardwareAnamorphic720pUpconversion);

    // -- BMDProfileID --
    nb::enum_<_BMDProfileID>(m, "ProfileID")
        .value("OneSubDeviceFullDuplex", bmdProfileOneSubDeviceFullDuplex)
        .value("OneSubDeviceHalfDuplex", bmdProfileOneSubDeviceHalfDuplex)
        .value("TwoSubDevicesFullDuplex", bmdProfileTwoSubDevicesFullDuplex)
        .value("TwoSubDevicesHalfDuplex", bmdProfileTwoSubDevicesHalfDuplex)
        .value("FourSubDevicesHalfDuplex", bmdProfileFourSubDevicesHalfDuplex);
}
