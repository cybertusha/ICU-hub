#!/usr/bin/env bash
# ==============================================================================
# DEVICE 3: CLOUD BACKEND & DOCTOR DASHBOARD (ICUGuardian)
# Can run on AWS EC2 OR on your Laptop / Second Laptop
# Doctor Dashboard URL: http://localhost:3000 (or http://<YOUR_IP>:3000 on Phone)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Stopping Cloud Backend & Doctor Dashboard..."
  kill "${PID_CLOUD:-}" "${PID_DASH:-}" 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "=========================================================================="
echo "  DEVICE 3: CLOUD BACKEND (:8000) & DOCTOR DASHBOARD (:3000)"
echo "=========================================================================="

python3 "$SCRIPT_DIR/aws-cloud/cloud_backend_server.py" &
PID_CLOUD=$!
sleep 1

python3 "$SCRIPT_DIR/doctor-dashboard/server.py" &
PID_DASH=$!
sleep 1

echo ""
echo "=========================================================================="
echo "  DOCTOR DASHBOARD IS LIVE!"
echo "--------------------------------------------------------------------------"
echo "  - On this computer:     http://localhost:3000"
echo "  - On your Phone/Tablet: http://$(hostname -I | awk '{print $1}'):3000"
echo "  - Login Credentials:"
echo "      Physician: sarah.smith   / doctor123"
echo "      Nurse:     michael.jones / nurse123"
echo "      Admin:     lisa.wilson   / admin123"
echo "=========================================================================="
echo "Press Ctrl+C to stop."

wait
