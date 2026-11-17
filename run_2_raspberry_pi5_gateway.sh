#!/usr/bin/env bash
# ==============================================================================
# DEVICE 2: RASPBERRY PI 5 (Bedside IoT Gateway + Local Pi Dashboard)
# Receives data on Ethernet (eth0: 192.168.50.1:5050) from your Laptop
# Forwards data over Wi-Fi (wlan0) to AWS Cloud / Doctor Dashboard Server
# Local Pi Dashboard URL: http://localhost:5050
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_SERVER_IP="${1:-192.168.50.10}"

export DEVICE_ID="ICU-PI-001"
export DEVICE_NAME="ICU-01 Raspberry Pi 5 Gateway"
export OPERATING_MODE="BEDSIDE_MONITOR"
export GATEWAY_PORT=5050
export CLOUD_BACKEND_URL="http://${CLOUD_SERVER_IP}:8000"

echo "=========================================================================="
echo "  DEVICE 2: RASPBERRY PI 5 IoT GATEWAY & LOCAL DASHBOARD"
echo "--------------------------------------------------------------------------"
echo "  1. Local Pi Dashboard URL:   http://localhost:5050"
echo "  2. Listening on LAN (eth0):  http://192.168.50.1:5050/gateway/telemetry"
echo "  3. Uploading to Cloud/Dr UI: ${CLOUD_BACKEND_URL}"
echo "=========================================================================="

cd "$SCRIPT_DIR/raspberry-pi-gateway"
python3 main.py --mode BEDSIDE_MONITOR
