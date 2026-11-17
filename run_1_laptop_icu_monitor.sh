#!/usr/bin/env bash
# ==============================================================================
# DEVICE 1: YOUR LAPTOP (Acting as the Bedside ICU Patient Monitor)
# Connects over the Ethernet LAN cable to Raspberry Pi 5 (192.168.50.1:5050)
# Dashboard URL on your laptop: http://localhost:3001
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_ETHERNET_IP="${1:-192.168.50.1}"

export MONITOR_PORT=3001
export GATEWAY_URL="http://${PI_ETHERNET_IP}:5050/gateway/telemetry"

echo "=========================================================================="
echo "  DEVICE 1: LAPTOP BEDSIDE ICU PATIENT MONITOR"
echo "--------------------------------------------------------------------------"
echo "  1. Open in Laptop Browser:  http://localhost:3001"
echo "  2. Sending LAN Data To Pi:  ${GATEWAY_URL}"
echo "=========================================================================="

python3 "$SCRIPT_DIR/patient-monitor-pc/server.py"
