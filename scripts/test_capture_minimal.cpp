// Minimal C2H DMA capture test — checks return values, dumps diagnostics.
#include "ntv2card.h"
#include "ntv2utils.h"
#include "ntv2devicefeatures.h"
#include "ajabase/system/process.h"
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <cstdlib>

int main()
{
    CNTV2Card card;
    if (!card.Open(0))
    {   fprintf(stderr, "open failed\n"); return 1; }

    printf("Card opened: %s\n", card.GetDisplayName().c_str());

    // Acquire ownership (like the AJA demo does)
    ULWord appSig = NTV2_FOURCC('T','E','S','T');
    int32_t pid   = int32_t(AJAProcess::GetPid());
    if (!card.AcquireStreamForApplication(appSig, pid))
        fprintf(stderr, "WARN: AcquireStream failed\n");

    // Save + set OEM task mode
    NTV2EveryFrameTaskMode savedMode;
    card.GetEveryFrameServices(savedMode);
    card.SetEveryFrameServices(NTV2_OEM_TASKS);

    NTV2Channel    ch  = NTV2_CHANNEL1;
    NTV2InputSource src = NTV2_INPUTSOURCE_SDI1;

    int exitCode = 1;
    ULWord* buf = nullptr;
    bool bufLocked = false;
    NTV2Buffer lockBuf;
    bool xferOk = false;

    // Detect input format
    NTV2VideoFormat vf = card.GetInputVideoFormat(src);
    printf("Detected input format: %d (%s)\n", vf, NTV2VideoFormatToString(vf).c_str());
    if (vf == NTV2_FORMAT_UNKNOWN)
    {   fprintf(stderr, "No signal on SDI1\n"); goto cleanup; }

    // Configure channel
    card.SetSDITransmitEnable(ch, false);
    card.EnableChannel(ch);
    card.SetMode(ch, NTV2_MODE_CAPTURE);
    card.SetVideoFormat(vf, false, false, ch);
    card.SetFrameBufferFormat(ch, NTV2_FBF_10BIT_YCBCR);
    card.SetReference(NTV2_REFERENCE_FREERUN);

    // Route: SDI1 → FB1
    card.ClearRouting();
    card.Connect(NTV2_XptFrameBuffer1Input, NTV2_XptSDIIn1);
    printf("Routing configured\n");

    {
        // Get frame size — use a generous allocation
        // 1080p 10-bit YCbCr v210: 1920*1080*8/3 ≈ 5.5MB, round up
        ULWord frameBytes = 1920 * 1080 * 4;  // 8MB, oversized but safe
        printf("Using buffer size: %u bytes\n", frameBytes);

        // Allocate a host buffer (page-aligned, like the AJA demo uses)
        int ret = posix_memalign(reinterpret_cast<void**>(&buf), 4096, frameBytes);
        if (ret || !buf)
        {   fprintf(stderr, "posix_memalign failed: %d\n", ret); goto cleanup; }
        memset(buf, 0, frameBytes);
        printf("Host buffer: %p  size=%u  (page-aligned)\n", (void*)buf, frameBytes);

        // Pre-lock the DMA buffer (like the demo does with NTV2_BUFFER_LOCK)
        lockBuf = NTV2Buffer(buf, frameBytes);
        bool lockOk = card.DMABufferLock(lockBuf, true);
        printf("DMABufferLock: %s\n", lockOk ? "OK" : "FAILED");
        bufLocked = lockOk;

        // Stop any prior autocirculate
        card.AutoCirculateStop(ch, true /*abort*/);

        // Init autocirculate for input
        if (!card.AutoCirculateInitForInput(ch, 7, NTV2_AUDIOSYSTEM_INVALID, 0))
        {   fprintf(stderr, "AutoCirculateInitForInput FAILED\n"); goto cleanup; }
        if (!card.AutoCirculateStart(ch))
        {   fprintf(stderr, "AutoCirculateStart FAILED\n"); goto cleanup; }
        printf("AutoCirculate started\n");

        // Wait for a captured frame
        bool gotFrame = false;
        for (int i = 0; i < 60; i++)
        {
            card.WaitForInputVerticalInterrupt(ch);
            AUTOCIRCULATE_STATUS st;
            card.AutoCirculateGetStatus(ch, st);
            if (st.HasAvailableInputFrame())
            {
                printf("Frame available after %d VBIs  bufLevel=%d\n",
                       i + 1, st.GetBufferLevel());
                gotFrame = true;
                break;
            }
        }
        if (!gotFrame)
        {   fprintf(stderr, "No frame available after 60 VBIs\n"); goto cleanup; }

        // Attempt the C2H DMA transfer
        AUTOCIRCULATE_TRANSFER xfer;
        xfer.SetVideoBuffer(buf, frameBytes);

        printf("Attempting AutoCirculateTransfer (C2H DMA)...\n");
        printf("  xfer vidBuf ptr=%p  size=%u\n",
               xfer.GetVideoBuffer().GetHostPointer(),
               xfer.GetVideoBuffer().GetByteCount());

        errno = 0;
        xferOk = card.AutoCirculateTransfer(ch, xfer);
        int savedErrno = errno;

        if (xferOk)
        {
            // Count non-zero bytes
            int nonzero = 0;
            auto p = reinterpret_cast<unsigned char*>(buf);
            for (ULWord i = 0; i < frameBytes; i++)
                if (p[i]) nonzero++;
            printf("TRANSFER OK!  nonzero=%d / %u\n", nonzero, frameBytes);
        }
        else
        {
            AUTOCIRCULATE_STATUS st;
            card.AutoCirculateGetStatus(ch, st);
            printf("TRANSFER FAILED  state=%d  bufLevel=%d  errno=%d (%s)\n",
                   st.acState, st.GetBufferLevel(), savedErrno, strerror(savedErrno));
        }

        // Try more transfers to see if the engine recovers
        if (xferOk)
        {
            printf("\nTransferring 9 more frames...\n");
            int okCount = 0, failCount = 0;
            for (int f = 0; f < 9; f++)
            {
                card.WaitForInputVerticalInterrupt(ch);
                AUTOCIRCULATE_STATUS st;
                card.AutoCirculateGetStatus(ch, st);
                if (!st.HasAvailableInputFrame()) { continue; }

                memset(buf, 0, frameBytes);
                xfer.SetVideoBuffer(buf, frameBytes);
                if (card.AutoCirculateTransfer(ch, xfer))
                    okCount++;
                else
                    failCount++;
            }
            printf("Results: %d ok, %d failed\n", okCount, failCount);
        }

        exitCode = xferOk ? 0 : 1;
    }

cleanup:
    card.AutoCirculateStop(ch, true);
    if (bufLocked) card.DMABufferUnlock(lockBuf);
    free(buf);  // free(nullptr) is safe
    card.SetEveryFrameServices(savedMode);
    card.ReleaseStreamForApplication(appSig, pid);
    card.Close();
    return exitCode;
}
