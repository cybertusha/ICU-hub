#!/usr/bin/env bash
# ==============================================================================
# ICUGuardian — Real-Time Hospital ICU Patient Monitoring System Launcher
# Starts all 4 production tiers:
#   1. Cloud Backend & Real-Time WebSocket Server (Port 8000)
#   2. Raspberry Pi Bedside IoT Gateway (Port 5050)
#   3. Bedside ICU Multiparameter Patient Monitor Terminal (Port 3001)
#   4. Doctor Web Application — ICUGuardian (Port 3000)
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Stopping ICUGuardian services..."
  kill "${PID_CLOUD:-}" "${PID_PI:-}" "${PID_MONITOR:-}" "${PID_DASH:-}" 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "=========================================================================="
echo "  ICUGUARDIAN — Real-Time IoT-Based ICU Patient Monitoring System"
echo "=========================================================================="

echo "[1/4] Starting Cloud Backend & Real-Time WebSocket Server (:8000)..."
python3 "$ROOT_DIR/aws-cloud/cloud_backend_server.py" &
PID_CLOUD=$!
sleep 1

echo "[2/4] Starting Raspberry Pi Bedside IoT Gateway (:5050)..."
python3 "$ROOT_DIR/raspberry-pi-gateway/main.py" &
PID_PI=$!
sleep 1

echo "[3/4] Starting Bedside Multiparameter Monitor Terminal (:3001)..."
python3 "$ROOT_DIR/patient-monitor-pc/server.py" &
PID_MONITOR=$!
sleep 1

echo "[4/4] Starting Doctor Web Application — ICUGuardian (:3000)..."
python3 "$ROOT_DIR/doctor-dashboard/server.py" &
PID_DASH=$!
sleep 1

echo ""
echo "=========================================================================="
echo "  ALL 4 SYSTEM TIERS ARE ONLINE AND STREAMING REAL-TIME TELEMETRY"
echo "--------------------------------------------------------------------------"
echo "  1. Central Station Dashboard: http://localhost:3000"
echo "     - Physician: sarah.smith   / doctor123"
echo "     - ICU Nurse: michael.jones / nurse123"
echo "     - Admin/IT:  lisa.wilson   / admin123"
echo "  2. Bedside Monitor Terminal:  http://localhost:3001"
echo "  3. Raspberry Pi Gateway API:  http://localhost:5050/gateway/status"
echo "  4. Cloud REST & WebSocket:    http://localhost:8000/api/health"
echo "=========================================================================="
echo "Press Ctrl+C to stop all services."

wait
