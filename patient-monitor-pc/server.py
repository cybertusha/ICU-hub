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
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "simulator"))
from patient_simulator import BedsidePatientSimulator, SCENARIOS

PORT = int(os.environ.get("MONITOR_PORT", "3001"))
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:5050/gateway/telemetry")
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
        with self.lock:
            if not self.running:
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
            qs = parse_qs(parsed.query)
            pid = qs.get("patientId", [RUNTIME.active_patient_id])[0]
            with RUNTIME.lock:
                sim = RUNTIME.simulators.get(pid) or RUNTIME.simulators["PATIENT-001"]
                reading = RUNTIME.latest_readings[sim.patient_id]
                status = RUNTIME.evaluate_status(reading["vitals"])
                payload = {
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
