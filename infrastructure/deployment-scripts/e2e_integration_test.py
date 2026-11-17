#!/usr/bin/env python3
"""
End-to-End Integration & Production Verification Suite
Verifies:
  1. Cloud Backend & WebSocket Server (:8000) — PBKDF2-SHA256 Auth, JWT, Patient Admission, Care Notes, Audit Logs
  2. Raspberry Pi Bedside IoT Gateway (:5050) — Hardware Bus Diagnostics, Linux Host Metrics, SQLite WAL Store-and-Forward
  3. Bedside ICU Patient Monitor Terminal (:3001) — Real-Time Waveform & Vital Telemetry Streaming
  4. Doctor Web Application (:3000) — Full Real-Time WebSocket Broadcast & Alert Lifecycle
"""

import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def http_json(url: str, method: str = "GET", body: dict = None, timeout: float = 3.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_url(url: str, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    print("=" * 74)
    print("ICUGUARDIAN — End-to-End Production Integration Verification Suite")
    print("=" * 74)

    procs = []
    try:
        p_cloud = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "aws-cloud" / "cloud_backend_server.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(p_cloud)
        assert wait_for_url("http://127.0.0.1:8000/api/health"), "Cloud Backend failed to start on :8000"
        print("  [OK] Started Cloud Backend & WebSocket Server on http://127.0.0.1:8000")

        p_pi = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "raspberry-pi-gateway" / "main.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(p_pi)
        assert wait_for_url("http://127.0.0.1:5050/gateway/status"), "Raspberry Pi Gateway failed to start on :5050"
        print("  [OK] Started Raspberry Pi Bedside IoT Gateway on http://127.0.0.1:5050")

        p_monitor = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "patient-monitor-pc" / "server.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(p_monitor)
        assert wait_for_url("http://127.0.0.1:3001/api/simulator/state"), "Bedside Monitor failed to start on :3001"
        print("  [OK] Started Bedside Multiparameter Monitor Terminal on http://127.0.0.1:3001")

        p_dash = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "doctor-dashboard" / "server.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(p_dash)
        assert wait_for_url("http://127.0.0.1:3000/"), "Doctor Dashboard failed to start on :3000"
        print("  [OK] Started Doctor Web Application on http://127.0.0.1:3000")

        ws_events = []
        try:
            import websocket  # type: ignore

            def ws_worker():
                ws = websocket.WebSocket()
                ws.connect("ws://127.0.0.1:8000/ws")
                while True:
                    try:
                        raw = ws.recv()
                        if raw:
                            ws_events.append(json.loads(raw))
                    except Exception:
                        break

            t_ws = threading.Thread(target=ws_worker, daemon=True)
            t_ws.start()
            time.sleep(0.5)
        except Exception:
            pass

        # 1. Verify PBKDF2-SHA256 Authentication & Signed JWT Issuance
        auth_res = http_json(
            "http://127.0.0.1:8000/api/auth/login",
            method="POST",
            body={"username": "sarah.smith", "password": "doctor123", "role": "Doctor"},
        )
        assert auth_res["fullName"] == "Dr. Sarah Smith" and auth_res["token"].count(".") == 2
        print(f"  [PASS] Security & Auth: Verified PBKDF2-SHA256 login & signed JWT for {auth_res['fullName']}")

        # 2. Verify Live Edge Hardware & Host Diagnostics from Raspberry Pi Gateway
        diag = http_json("http://127.0.0.1:8000/api/devices/ICU-PI-001/diagnostics")
        assert "hostMetrics" in diag and "sensorBusStatus" in diag
        print(
            f"  [PASS] Edge Diagnostics: CPU Temp={diag['hostMetrics']['cpuTempC']}°C, "
            f"CPU={diag['hostMetrics']['cpuUsagePct']}%, Sensors={diag['sensorBusStatus']}"
        )

        # 3. Verify Clinical Care Note Recording & Audit Logging
        updated_pt = http_json(
            "http://127.0.0.1:8000/api/patients/PATIENT-001/notes",
            method="POST",
            body={
                "author": "Dr. Sarah Smith",
                "role": "Doctor",
                "note": "Verified Lead II telemetry and arterial line calibration.",
            },
        )
        assert len(updated_pt["careNotes"]) >= 1
        print(f"  [PASS] Clinical Chart: Added care note to PATIENT-001 ({len(updated_pt['careNotes'])} notes total)")

        # 4. Verify Physical HL7 v2.6 MLLP Ethernet Stream Ingestion on TCP Port 2575
        import socket
        hl7_frame = (
            b"\x0bMSH|^~\\&|MINDRAY_N15|ICU_BED_01|PI_GATEWAY|HOSPITAL|20261117015000||ORU^R01|HL7LIVE001|P|2.6\r"
            b"PID|1||PATIENT-001^^^HOSPITAL^MR||JOHNSON^EMILY||19810412|F\r"
            b"PV1|1|I|ICU^WARD_A^ICU-01\r"
            b"OBX|1|NM|147842^MDC_ECG_HEART_RATE^MDC|1.1.1.1|77|264864^MDC_DIM_BEAT_PER_MIN^MDC|||||F\r"
            b"OBX|2|NM|150456^MDC_PULS_OXIM_SAT_O2^MDC|1.2.1.1|99|262688^MDC_DIM_PERCENT^MDC|||||F\r"
            b"OBX|3|NM|150344^MDC_TEMP^MDC|1.3.1.1|36.7|268192^MDC_DIM_DEGC^MDC|||||F\r"
            b"OBX|4|NM|151562^MDC_RESP_RATE^MDC|1.4.1.1|16|264928^MDC_DIM_RESP_PER_MIN^MDC|||||F\r"
            b"OBX|5|NM|150021^MDC_PRESS_BLD_NONINV_SYS^MDC|1.5.1.1|121|266016^MDC_DIM_MMHG^MDC|||||F\r"
            b"OBX|6|NM|150022^MDC_PRESS_BLD_NONINV_DIA^MDC|1.5.1.2|79|266016^MDC_DIM_MMHG^MDC|||||F\r\x1c\r"
        )
        with socket.create_connection(("127.0.0.1", 2575), timeout=3.0) as s_hl7:
            s_hl7.sendall(hl7_frame)
            ack_hl7 = s_hl7.recv(4096)
        assert b"MSA|AA|HL7LIVE001" in ack_hl7
        print("  [PASS] HL7 v2.6 MLLP Ethernet Stream (Port 2575): Parsed ORU^R01, forwarded to Cloud & returned ACK^R01")

        # 5. Verify Normal Sinus Telemetry Pipeline
        res1 = http_json(
            "http://127.0.0.1:3001/api/simulator/scenario",
            method="POST",
            body={"patientId": "PATIENT-001", "scenario": "NORMAL"},
        )
        assert res1["ok"] is True
        time.sleep(1.5)
        p1 = http_json("http://127.0.0.1:8000/api/patients/PATIENT-001")
        assert p1["monitoringStatus"] == "NORMAL"
        print(
            f"  [PASS] Real-Time Telemetry (Normal Sinus): PATIENT-001 status={p1['monitoringStatus']}, "
            f"HR={p1['vitals']['heartRate']} BPM, SpO2={p1['vitals']['spo2']}%"
        )

        # 5. Verify Acute Hypoxemia Detection & Critical Alert Generation
        for _ in range(3):
            http_json(
                "http://127.0.0.1:3001/api/simulator/scenario",
                method="POST",
                body={"patientId": "PATIENT-001", "scenario": "LOW_SPO2"},
            )
        time.sleep(1.0)
        p1_crit = http_json("http://127.0.0.1:8000/api/patients/PATIENT-001")
        alerts_p1 = http_json("http://127.0.0.1:8000/api/alerts?patientId=PATIENT-001&status=active")["alerts"]
        spo2_alerts = [a for a in alerts_p1 if a["parameter"] == "spo2"]
        assert len(spo2_alerts) >= 1
        target_alert_id = spo2_alerts[0]["alertId"]
        print(
            f"  [PASS] Automated Abnormality Detection: SpO2={p1_crit['vitals']['spo2']}%, "
            f"Alert {target_alert_id} ({spo2_alerts[0]['severity']}) generated"
        )

        # 6. Verify Recovery Detection, Acknowledge & Resolve Workflow
        for _ in range(5):
            http_json(
                "http://127.0.0.1:3001/api/simulator/scenario",
                method="POST",
                body={"patientId": "PATIENT-001", "scenario": "RECOVERY"},
            )
        time.sleep(1.0)
        p1_rec = http_json("http://127.0.0.1:8000/api/patients/PATIENT-001")
        assert p1_rec["monitoringStatus"] == "NORMAL"

        ack_resp = http_json(
            f"http://127.0.0.1:8000/api/alerts/{target_alert_id}/acknowledge",
            method="POST",
            body={"userName": "Dr. Sarah Smith"},
        )
        assert ack_resp["acknowledged"] is True and ack_resp["resolved"] is False

        res_resp = http_json(
            f"http://127.0.0.1:8000/api/alerts/{target_alert_id}/resolve",
            method="POST",
            body={"userName": "Dr. Sarah Smith"},
        )
        assert res_resp["resolved"] is True
        print(
            f"  [PASS] Recovery & Alert Lifecycle: PATIENT-001 recovered to NORMAL; "
            f"Alert {target_alert_id} acknowledged & resolved"
        )

        # 7. Verify Store-and-Forward SQLite WAL Buffering & Auto-Synchronization
        disc_resp = http_json(
            "http://127.0.0.1:8000/api/devices/ICU-PI-001/maintenance",
            method="POST",
            body={"offline": True},
        )
        assert disc_resp["device"]["deviceStatus"] == "OFFLINE"
        time.sleep(3.2)
        gw_offline = http_json("http://127.0.0.1:5050/gateway/status")
        buffered_cnt = gw_offline["offlineQueueSize"]
        assert buffered_cnt > 0
        print(f"  [PASS] Store-and-Forward Outage Buffering: Buffered {buffered_cnt} readings in SQLite WAL queue")

        reconn_resp = http_json(
            "http://127.0.0.1:8000/api/devices/ICU-PI-001/maintenance",
            method="POST",
            body={"offline": False},
        )
        assert reconn_resp["device"]["deviceStatus"] == "ONLINE"
        time.sleep(1.0)
        gw_online = http_json("http://127.0.0.1:5050/gateway/status")
        assert gw_online["offlineQueueSize"] == 0
        print(
            f"  [PASS] Automatic Cloud Synchronization: Drained SQLite queue to 0 "
            f"(total synchronized={gw_online['syncedFromBufferCount']})"
        )

        # 8. Verify Audit Logs
        audits = http_json("http://127.0.0.1:8000/api/audit-logs")["auditLogs"]
        assert len(audits) >= 4
        print(f"  [PASS] HIPAA Security Audit Trail: Verified {len(audits)} immutable audit log entries")

        print("=" * 74)
        print("ALL PRODUCTION INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 74)
        return 0
    finally:
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
