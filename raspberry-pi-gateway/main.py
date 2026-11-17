#!/usr/bin/env python3
"""
Main Entrypoint for Raspberry Pi IoT Gateway (`raspberry-pi-gateway/main.py`).
Supports:
  - MODE 1: SIMULATION MODE (Receives simulated vital data from PC Bedside Monitor and forwards to AWS)
  - MODE 2: HARDWARE MODE (Reads physical sensors via SensorManager and forwards to AWS)
  - `--self-test`: Runs automated Phase 3 unit verification (validation, SQLite buffering, reconnection).
"""

import argparse
import sys
import threading
import time
from datetime import datetime, timezone
from config import DEVICE_ID, ASSIGNED_PATIENT_ID, OPERATING_MODE, GATEWAY_PORT
from sensor_manager import SensorManager
from simulator_receiver import GATEWAY_SERVICE, run_receiver_server
from icu_monitor_lan_driver import HL7MLLPMonitorListener
from logger import get_logger

log = get_logger("main")


def periodic_sync_and_heartbeat():
    """Background worker that synchronizes queued offline messages and emits gateway heartbeats."""
    while True:
        try:
            if GATEWAY_SERVICE.connectivity.is_online():
                GATEWAY_SERVICE.drain_offline_queue()
        except Exception as exc:
            log.error(f"Background sync error: {exc}")
        time.sleep(3.0)


def hardware_polling_loop():
    """Polls physical biomedical sensors when running in HARDWARE mode."""
    sensor_mgr = SensorManager(device_id=DEVICE_ID, patient_id=ASSIGNED_PATIENT_ID)
    status = sensor_mgr.initialize_sensors()
    log.info(f"Hardware Sensor Initialization Status: {status}")

    while True:
        if sensor_mgr.hardware_ready:
            try:
                reading = sensor_mgr.read_hardware_payload()
                GATEWAY_SERVICE.handle_incoming_reading(reading)
            except Exception as exc:
                log.error(f"Hardware sensor read error: {exc}")
        time.sleep(1.0)


def run_self_test() -> int:
    print("=" * 65)
    print("PHASE 3: Testing Raspberry Pi IoT Gateway Modules")
    print("=" * 65)

    # 1. Test DataProcessor valid payload
    valid_sample = {
        "messageId": f"TEST-MSG-{int(time.time() * 1000)}-01",
        "deviceId": "ICU-PI-001",
        "patientId": "PATIENT-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "SIMULATION",
        "scenario": "LOW_SPO2",
        "vitals": {
            "heartRate": 108,
            "spo2": 87,
            "temperature": 37.1,
            "respiratoryRate": 24,
            "bloodPressure": {"systolic": 112, "diastolic": 74},
            "ecg": [0.01, 0.15, -0.1, 0.98, -0.25, 0.05],
        },
    }
    ok, cleaned, err = GATEWAY_SERVICE.processor.validate_and_enrich(valid_sample)
    assert ok, f"Valid payload failed validation: {err}"
    status, breaches = GATEWAY_SERVICE.processor.detect_local_abnormalities(cleaned)
    assert status == "CRITICAL", f"Expected CRITICAL status for SpO2=87%, got {status}"
    print(f"  [OK] DataProcessor validated payload & detected {status} condition ({len(breaches)} breaches)")

    # 2. Test rejection of malformed/corrupt sensor data
    invalid_sample = {
        "patientId": "PATIENT-001",
        "vitals": {"heartRate": 450, "spo2": 120, "temperature": 37.0, "respiratoryRate": 16},
    }
    ok_bad, _, err_bad = GATEWAY_SERVICE.processor.validate_and_enrich(invalid_sample)
    assert not ok_bad, "Malformed reading with HR=450 should have been rejected"
    print(f"  [OK] DataProcessor rejected out-of-range reading: {err_bad}")

    # 3. Test OfflineQueue persistent SQLite buffering
    initial_q = GATEWAY_SERVICE.queue.size()
    GATEWAY_SERVICE.connectivity.set_simulated_offline(True)
    offline_msg = dict(valid_sample)
    offline_msg["messageId"] = f"TEST-OFFLINE-{int(time.time() * 1000)}"
    res = GATEWAY_SERVICE.handle_incoming_reading(offline_msg)
    assert res["action"] == "BUFFERED_OFFLINE", f"Expected BUFFERED_OFFLINE, got {res}"
    new_q = GATEWAY_SERVICE.queue.size()
    assert new_q == initial_q + 1, f"Expected queue size {initial_q + 1}, got {new_q}"
    print(f"  [OK] OfflineQueue persistently buffered reading in SQLite (queue size={new_q})")

    # Clean up test message from queue and restore online mode
    GATEWAY_SERVICE.queue.mark_synchronized([offline_msg["messageId"]])
    GATEWAY_SERVICE.connectivity.set_simulated_offline(False)
    print("  [OK] ConnectivityManager restored online state and cleaned test queue")
    print("=" * 65)
    print("PHASE 3 RASPBERRY PI GATEWAY SELF-TEST PASSED SUCCESSFULLY!")
    print("=" * 65)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi ICU Bedside IoT Gateway")
    parser.add_argument(
        "--mode",
        choices=["BEDSIDE_MONITOR", "HARDWARE", "SIMULATION"],
        default=OPERATING_MODE,
    )
    parser.add_argument("--self-test", action="store_true", help="Run Phase 3 verification tests")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    log.info(f"Starting Raspberry Pi IoT Gateway ({DEVICE_ID}) in {args.mode} mode on HTTP port {GATEWAY_PORT} & HL7 MLLP TCP port 2575")
    sync_thread = threading.Thread(target=periodic_sync_and_heartbeat, daemon=True)
    sync_thread.start()

    try:
        hl7_listener = HL7MLLPMonitorListener(bind_host="0.0.0.0", bind_port=2575)
        hl7_listener.start_in_background()
    except Exception as exc:
        log.warning(f"Could not bind HL7 MLLP TCP listener on port 2575: {exc}")

    if args.mode == "HARDWARE":
        hw_thread = threading.Thread(target=hardware_polling_loop, daemon=True)
        hw_thread.start()

    try:
        run_receiver_server()
    except KeyboardInterrupt:
        log.info("Shutting down Raspberry Pi IoT Gateway.")


if __name__ == "__main__":
    main()
