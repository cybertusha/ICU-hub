#!/usr/bin/env python3
"""
Bedside ICU Patient Monitor Server (PC Terminal)
Serves the Bedside Patient Monitor UI on port 3001, runs the multi-bed simulation loop,
and transmits real-time vital readings to the Raspberry Pi IoT Gateway.
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "simulator"))
from patient_simulator import BedsidePatientSimulator, SCENARIOS

PORT = int(os.environ.get("MONITOR_PORT", "3001"))
GATEWAY_URL = os.environ.get("GATEWAY_TELEMETRY_URL") or os.environ.get("GATEWAY_URL", "http://127.0.0.1:5050/gateway/telemetry")
CLOUD_BACKEND_URL = os.environ.get("CLOUD_BACKEND_URL", "http://127.0.0.1:8000")
FRONTEND_HTML = Path(__file__).parent / "frontend" / "index.html"

PATIENT_DEFINITIONS = [
    {"patientId": "PATIENT-001", "name": "Emily Johnson", "bed": "ICU-01", "deviceId": "ICU-PI-001", "defaultScenario": "NORMAL"},
    {"patientId": "PATIENT-002", "name": "Michael Chen", "bed": "ICU-02", "deviceId": "ICU-PI-002", "defaultScenario": "NORMAL"},
    {"patientId": "PATIENT-003", "name": "Sarah Davis", "bed": "ICU-03", "deviceId": "ICU-PI-003", "defaultScenario": "NORMAL"},
    {"patientId": "PATIENT-004", "name": "James Thompson", "bed": "ICU-04", "deviceId": "ICU-PI-004", "defaultScenario": "NORMAL"},
    {"patientId": "PATIENT-005", "name": "Maria Rodriguez", "bed": "ICU-05", "deviceId": "ICU-PI-005", "defaultScenario": "NORMAL"},
    {"patientId": "PATIENT-006", "name": "Robert Kim", "bed": "ICU-06", "deviceId": "ICU-PI-006", "defaultScenario": "NORMAL"},
]


class SimulatorRuntime:
    def __init__(self):
        self.running = True
        self.active_patient_id = "PATIENT-001"
        self.simulators = {}
        self.latest_readings = {}
        self.packets_sent = 0
        self.gateway_status = "WAITING"
        self.cloud_connected = True
        self.offline_queue_size = 0
        self.lock = threading.Lock()

        for p in PATIENT_DEFINITIONS:
            sim = BedsidePatientSimulator(
                patient_id=p["patientId"],
                device_id=p["deviceId"],
                patient_name=p["name"],
                bed_number=p["bed"],
                scenario=p["defaultScenario"],
            )
            self.simulators[p["patientId"]] = sim
            self.latest_readings[p["patientId"]] = sim.next_reading()

    def sync_with_cloud_patients(self) -> None:
        """
        Fetches the live patient census from Cloud Backend (:8000/api/patients) so that
        admitting, editing, or discharging a patient on the Doctor Dashboard immediately
        updates the Bedside ICU Multiparameter Monitor (:3001).
        """
        try:
            req = urllib.request.Request(f"{CLOUD_BACKEND_URL}/api/patients", method="GET")
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status != 200:
                    return
                data = json.loads(resp.read().decode("utf-8"))
                cloud_patients = data.get("patients", [])
        except Exception:
            return

        with self.lock:
            cloud_ids = set()
            for cp in cloud_patients:
                pid = cp.get("patientId")
                if not pid:
                    continue
                cloud_ids.add(pid)
                pname = cp.get("patientName", "ICU Patient")
                bed = cp.get("bedNumber", "ICU-01")
                dev_id = cp.get("monitoringDeviceId", "ICU-PI-001")
                if pid not in self.simulators:
                    sim = BedsidePatientSimulator(
                        patient_id=pid,
                        device_id=dev_id,
                        patient_name=pname,
                        bed_number=bed,
                        scenario="NORMAL",
                    )
                    self.simulators[pid] = sim
                    self.latest_readings[pid] = sim.next_reading()
                else:
                    sim = self.simulators[pid]
                    sim.patient_name = pname
                    sim.bed_number = bed
                    sim.device_id = dev_id

            # Remove discharged patients
            for existing_id in list(self.simulators.keys()):
                if existing_id not in cloud_ids:
                    del self.simulators[existing_id]
                    self.latest_readings.pop(existing_id, None)

            if self.simulators:
                if self.active_patient_id not in self.simulators:
                    self.active_patient_id = next(iter(self.simulators.keys()))
            else:
                self.active_patient_id = ""

    def list_patient_Roster(self):
        return [
            {
                "patientId": sim.patient_id,
                "patientName": sim.patient_name,
                "bedNumber": sim.bed_number,
                "deviceId": sim.device_id,
                "scenario": sim.scenario,
            }
            for sim in sorted(self.simulators.values(), key=lambda s: s.bed_number)
        ]

    def evaluate_status(self, vitals: dict) -> str:
        hr = vitals["heartRate"]
        spo2 = vitals["spo2"]
        temp = vitals["temperature"]
        rr = vitals["respiratoryRate"]
        if spo2 < 90 or hr > 120 or hr < 45 or temp >= 39.0 or rr > 28 or rr < 8:
            return "CRITICAL"
        if spo2 < 94 or hr > 100 or hr < 60 or temp > 38.0 or rr > 20 or rr < 12:
            return "WARNING"
        return "NORMAL"

    def step_all(self):
        self.sync_with_cloud_patients()
        with self.lock:
            if not self.running or not self.simulators:
                return
            readings_to_send = []
            for pid, sim in self.simulators.items():
                reading = sim.next_reading()
                self.latest_readings[pid] = reading
                readings_to_send.append((sim, reading))

        for sim, reading in readings_to_send:
            try:
                resp = sim.transmit_to_gateway(GATEWAY_URL, reading, timeout=1.5)
                with self.lock:
                    self.packets_sent += 1
                    self.gateway_status = "CONNECTED"
                    self.cloud_connected = bool(resp.get("cloudConnected", True))
                    self.offline_queue_size = int(resp.get("offlineQueueSize", 0))
            except Exception:
                with self.lock:
                    self.gateway_status = "STANDALONE (Gateway Unreachable)"


RUNTIME = SimulatorRuntime()


def background_loop():
    while True:
        try:
            RUNTIME.step_all()
        except Exception:
            pass
        time.sleep(1.5)


class MonitorHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html = FRONTEND_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if parsed.path == "/api/simulator/state":
            RUNTIME.sync_with_cloud_patients()
            qs = parse_qs(parsed.query)
            requested_pid = qs.get("patientId", [""])[0]
            with RUNTIME.lock:
                roster = RUNTIME.list_patient_Roster()
                if not RUNTIME.simulators:
                    payload = {
                        "empty": True,
                        "patients": [],
                        "patientId": "NONE",
                        "patientName": "No Admitted Patient",
                        "bedNumber": "STANDBY",
                        "deviceId": "ICU-PI-001",
                        "scenario": "NORMAL",
                        "running": False,
                        "monitoringStatus": "STANDBY",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "vitals": {
                            "heartRate": 0,
                            "spo2": 0,
                            "temperature": 0.0,
                            "respiratoryRate": 0,
                            "bloodPressure": {"systolic": 0, "diastolic": 0},
                            "ecg": [],
                        },
                        "packetsSent": RUNTIME.packets_sent,
                        "gatewayStatus": RUNTIME.gateway_status,
                        "cloudConnected": RUNTIME.cloud_connected,
                        "offlineQueueSize": RUNTIME.offline_queue_size,
                    }
                else:
                    sim = (
                        RUNTIME.simulators.get(requested_pid)
                        or RUNTIME.simulators.get(RUNTIME.active_patient_id)
                        or next(iter(RUNTIME.simulators.values()))
                    )
                    RUNTIME.active_patient_id = sim.patient_id
                    reading = RUNTIME.latest_readings.get(sim.patient_id) or sim.next_reading()
                    RUNTIME.latest_readings[sim.patient_id] = reading
                    status = RUNTIME.evaluate_status(reading["vitals"])
                    payload = {
                        "empty": False,
                        "patients": roster,
                        "patientId": sim.patient_id,
                        "patientName": sim.patient_name,
                        "bedNumber": sim.bed_number,
                        "deviceId": sim.device_id,
                        "scenario": sim.scenario,
                        "running": RUNTIME.running,
                        "monitoringStatus": status,
                        "timestamp": reading["timestamp"],
                        "vitals": reading["vitals"],
                        "packetsSent": RUNTIME.packets_sent,
                        "gatewayStatus": RUNTIME.gateway_status,
                        "cloudConnected": RUNTIME.cloud_connected,
                        "offlineQueueSize": RUNTIME.offline_queue_size,
                    }
            self._send_json(200, payload)
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        body = json.loads(raw.decode("utf-8"))

        if parsed.path == "/api/simulator/scenario":
            pid = body.get("patientId", RUNTIME.active_patient_id)
            scenario = body.get("scenario", "NORMAL")
            with RUNTIME.lock:
                sim = RUNTIME.simulators.get(pid)
                if not sim or scenario not in SCENARIOS:
                    self._send_json(400, {"error": "Invalid patientId or scenario"})
                    return
                sim.set_scenario(scenario)
                # Step 3 times immediately so change is visible on next frame
                for _ in range(3):
                    reading = sim.next_reading()
                RUNTIME.latest_readings[pid] = reading
            try:
                sim.transmit_to_gateway(GATEWAY_URL, reading, timeout=1.5)
            except Exception:
                pass
            self._send_json(200, {"ok": True, "patientId": pid, "scenario": scenario, "reading": reading})
            return

        if parsed.path == "/api/simulator/patient":
            pid = body.get("patientId", "PATIENT-001")
            with RUNTIME.lock:
                if pid in RUNTIME.simulators:
                    RUNTIME.active_patient_id = pid
            self._send_json(200, {"ok": True, "activePatientId": RUNTIME.active_patient_id})
            return

        if parsed.path == "/api/simulator/toggle":
            with RUNTIME.lock:
                RUNTIME.running = bool(body.get("running", True))
            self._send_json(200, {"ok": True, "running": RUNTIME.running})
            return

        self._send_json(404, {"error": "Not found"})


if __name__ == "__main__":
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    print(f"[Bedside ICU Patient Monitor] Running on http://localhost:{PORT}")
    print(f"[Bedside ICU Patient Monitor] Forwarding telemetry to Raspberry Pi Gateway at {GATEWAY_URL}")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), MonitorHTTPHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Bedside Patient Monitor...")
