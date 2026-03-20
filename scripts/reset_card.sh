#!/usr/bin/env bash
# Reset an AJA NTV2 card after a DMA timeout.
#
# A failed C2H (card-to-host) DMA transfer leaves the Xilinx DMA engine
# wedged ("dma hardware not done or error").  Subsequent transfers fail
# with EPERM until the card is reset.  Three steps:
#
#   1. PCI function-level reset — resets the FPGA and DMA engine.
#   2. rmmod ajantv2           — tears down stale driver state.
#   3. modprobe ajantv2        — re-probes the card cleanly.
#
# Usage:  sudo ./scripts/reset_card.sh [PCI_ADDR]
#
# PCI_ADDR defaults to the first AJA device found by lspci.

set -euo pipefail

PCI_ADDR="${1:-}"

if [[ -z "$PCI_ADDR" ]]; then
    PCI_ADDR=$(lspci -D | grep -i aja | head -1 | cut -d' ' -f1)
    if [[ -z "$PCI_ADDR" ]]; then
        echo "error: no AJA device found" >&2
        exit 1
    fi
fi

RESET_PATH="/sys/bus/pci/devices/${PCI_ADDR}/reset"

if [[ ! -w "$RESET_PATH" ]]; then
    echo "error: cannot write $RESET_PATH (not root?)" >&2
    exit 1
fi

echo "Resetting PCI device $PCI_ADDR ..."
echo 1 > "$RESET_PATH"

echo "Unloading ajantv2 driver ..."
rmmod ajantv2 2>/dev/null || true

echo "Reloading ajantv2 driver ..."
modprobe ajantv2

echo "Done. Card should be ready."
