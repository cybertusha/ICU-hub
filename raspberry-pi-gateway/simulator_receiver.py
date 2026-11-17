"""
Local Network Telemetry Receiver, Local Raspberry Pi 5 Dashboard & Edge Management API.
Listens on port 5050 for incoming patient telemetry from the College ICU Monitor PC over Ethernet (eth0),
displays the exact received readings on a local Raspberry Pi dashboard (http://localhost:5050/),
validates/processes readings, publishes to AWS IoT Core, and buffers in SQLite WAL when offline.
"""

import json
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from config import GATEWAY_HOST, GATEWAY_PORT, DEVICE_ID, ASSIGNED_PATIENT_ID, OPERATING_MODE, SYNC_BATCH_SIZE
from data_processor import DataProcessor
from offline_queue import OfflineQueue
from connectivity_manager import ConnectivityManager
from mqtt_client import AWSIoTMQTTClient
from sensor_manager import SensorManager, get_host_system_metrics
from logger import get_logger, LOG_FILE

log = get_logger("gateway_receiver")


LOCAL_PI_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Raspberry Pi 5 — Edge Telemetry Gateway Console</title>
  <style>
    :root {
      --bg: #050911;
      --surface: #0b1220;
      --border: #1a263b;
      --green: #10b981;
      --cyan: #38bdf8;
      --amber: #fbbf24;
      --orange: #f97316;
      --purple: #a78bfa;
      --red: #ef4444;
      --mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
      --sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: #f1f5f9;
      font-family: var(--sans);
      padding: 18px 22px;
      font-size: 13px;
    }
    .wrap { max-width: 1320px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
    .topbar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .pill {
      font-family: var(--mono);
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--border);
      background: #131e33;
    }
    .pill-online { background: rgba(16, 185, 129, 0.14); color: #34d399; border-color: rgba(16, 185, 129, 0.4); }
    .pill-offline { background: rgba(239, 68, 68, 0.2); color: #f87171; border-color: rgba(239, 68, 68, 0.5); }

    .readout-strip {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }
    @media (max-width: 860px) { .readout-strip { grid-template-columns: repeat(2, 1fr); } }
    .rcell {
      padding: 14px 18px;
      border-right: 1px solid var(--border);
    }
    .rcell:last-child { border-right: none; }
    .rlabel {
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .rval {
      font-family: var(--mono);
      font-variant-numeric: tabular-nums;
      font-size: 38px;
      font-weight: 800;
      margin-top: 6px;
      line-height: 1;
    }
    .rsub { font-family: var(--mono); font-size: 10.5px; color: #64748b; margin-top: 6px; }

    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }
    .panel-head {
      padding: 9px 16px;
      border-bottom: 1px solid var(--border);
      background: #080e1a;
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #94a3b8;
      display: flex;
      justify-content: space-between;
    }
    .stats-strip {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
    }
    @media (max-width: 900px) { .stats-strip { grid-template-columns: repeat(2, 1fr); } }
    .sbox {
      padding: 12px 16px;
      border-right: 1px solid var(--border);
    }
    .sbox:last-child { border-right: none; }
    .sbox .k { font-size: 11px; color: #64748b; font-family: var(--mono); }
    .sbox .v { font-size: 16px; font-weight: 700; margin-top: 4px; font-family: var(--mono); color: #e2e8f0; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div style="font-family:var(--mono);font-size:10.5px;color:#38bdf8;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;">
          RASPBERRY PI 5 EDGE TELEMETRY GATEWAY CONSOLE
        </div>
        <div style="font-size:17px;font-weight:700;margin-top:2px;">
          Node <span id="gw-id" style="font-family:var(--mono);">ICU-PI-001</span> — Bedside Ethernet Acquisition & Cloud Forwarder
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <span class="pill pill-online" id="lan-badge">ETH0 INGRESS: STANDBY</span>
        <span class="pill pill-online" id="aws-badge">AWS MQTT/TLS: ONLINE</span>
      </div>
    </div>

    <div class="readout-strip">
      <div class="rcell">
        <div class="rlabel" style="color:var(--green);">ECG Heart Rate</div>
        <div class="rval" id="v-hr" style="color:var(--green);">--</div>
        <div class="rsub">bpm • eth0 ingress</div>
      </div>
      <div class="rcell">
        <div class="rlabel" style="color:var(--cyan);">SpO₂ Arterial</div>
        <div class="rval" id="v-spo2" style="color:var(--cyan);">--</div>
        <div class="rsub">% • optical pulse</div>
      </div>
      <div class="rcell">
        <div class="rlabel" style="color:var(--orange);">NIBP Sys / Dia</div>
        <div class="rval" id="v-bp" style="color:var(--orange);font-size:32px;">--/--</div>
        <div class="rsub">mmHg • cuff / arterial</div>
      </div>
      <div class="rcell">
        <div class="rlabel" style="color:var(--amber);">Core Temp (T1)</div>
        <div class="rval" id="v-temp" style="color:var(--amber);">--</div>
        <div class="rsub">°C • probe</div>
      </div>
      <div class="rcell">
        <div class="rlabel" style="color:var(--purple);">Resp Rate</div>
        <div class="rval" id="v-rr" style="color:var(--purple);">--</div>
        <div class="rsub">rpm • impedance</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span>Edge Processing, Host SoC & Store-and-Forward Telemetry</span>
        <span id="host-soc">SoC: --°C</span>
      </div>
      <div class="stats-strip">
        <div class="sbox"><div class="k">PATIENT BINDING</div><div class="v" id="st-pid">--</div></div>
        <div class="sbox"><div class="k">LAST FRAME ID</div><div class="v" id="st-mid" style="font-size:12px;">--</div></div>
        <div class="sbox"><div class="k">EDGE ACUITY STATE</div><div class="v" id="st-eval">--</div></div>
        <div class="sbox"><div class="k">ETH0 RX FRAMES</div><div class="v" id="st-rx">0</div></div>
        <div class="sbox"><div class="k">CLOUD TX FRAMES</div><div class="v" id="st-tx">0</div></div>
        <div class="sbox"><div class="k">SQLITE WAL QUEUE</div><div class="v" id="st-q">0</div></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span>Last Validated MQTT Envelope (Topic: icu/devices/ICU-PI-001/vitals)</span>
        <span>QoS 1 • TLS 1.2</span>
      </div>
      <pre id="raw-json" style="background:#03060c;color:#34d399;padding:14px 16px;font-family:var(--mono);font-size:11.5px;overflow-x:auto;max-height:240px;">Awaiting telemetry frame on eth0 (http://192.168.50.1:5050/gateway/telemetry)...</pre>
    </div>
  </div>

  <script>
    async function pollGateway() {
      try {
        const res = await fetch('/gateway/status');
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('gw-id').textContent = data.deviceId;
        document.getElementById('st-rx').textContent = data.receivedCount;
        document.getElementById('st-tx').textContent = data.publishedCount;
        document.getElementById('st-q').textContent = data.offlineQueueSize + ' frames';
        document.getElementById('host-soc').textContent = `SoC: ${data.cpuTempC ?? '--'}°C | CPU: ${data.cpuUsagePct ?? '--'}% | RTT: ${data.latencyMs ?? '--'} ms`;

        const awsBadge = document.getElementById('aws-badge');
        awsBadge.textContent = data.cloudConnected ? 'AWS MQTT/TLS: ONLINE' : 'AWS MQTT/TLS: OFFLINE (SQLITE BUFFERING)';
        awsBadge.className = 'pill ' + (data.cloudConnected ? 'pill-online' : 'pill-offline');

        if (data.latestReading) {
          const r = data.latestReading;
          const v = r.vitals || {};
          const bp = v.bloodPressure || { systolic: '--', diastolic: '--' };
          document.getElementById('lan-badge').textContent = 'ETH0 INGRESS: ' + new Date(r.timestamp).toLocaleTimeString();
          document.getElementById('v-hr').textContent = v.heartRate;
          document.getElementById('v-spo2').textContent = v.spo2 + '%';
          document.getElementById('v-bp').textContent = bp.systolic + '/' + bp.diastolic;
          document.getElementById('v-temp').textContent = Number(v.temperature).toFixed(1);
          document.getElementById('v-rr').textContent = v.respiratoryRate;
          document.getElementById('st-pid').textContent = r.patientId;
          document.getElementById('st-mid').textContent = r.messageId;
          document.getElementById('st-eval').textContent = data.latestEvaluation || 'NORMAL';
          document.getElementById('raw-json').textContent = JSON.stringify(r, null, 2);
        }
      } catch (e) {}
    }
    setInterval(pollGateway, 1000);
    pollGateway();
  </script>
</body>
</html>
"""


class GatewayService:
    def __init__(self):
        self.processor = DataProcessor()
        self.queue = OfflineQueue()
        self.connectivity = ConnectivityManager()
        self.mqtt = AWSIoTMQTTClient()
        self.sensors = SensorManager(device_id=DEVICE_ID, patient_id=ASSIGNED_PATIENT_ID)
        self.sensor_bus_status = self.sensors.initialize_sensors()
        self.received_count = 0
        self.rejected_count = 0
        self.synced_from_buffer_count = 0
        self.latest_reading: Optional[Dict[str, Any]] = None
        self.latest_evaluation: str = "NORMAL"

    def handle_incoming_reading(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        is_valid, cleaned, error_reason = self.processor.validate_and_enrich(raw_payload)
        if not is_valid:
            self.rejected_count += 1
            log.warning(f"Rejected invalid reading: {error_reason}")
            return {"ok": False, "error": error_reason}

        self.received_count += 1
        local_status, breaches = self.processor.detect_local_abnormalities(cleaned)
        self.latest_reading = cleaned
        self.latest_evaluation = local_status
        dev_id = cleaned["deviceId"]

        if self.connectivity.is_online():
            t0 = time.perf_counter()
            published = self.mqtt.publish_vitals(cleaned)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.connectivity.report_transmission_result(published, latency_ms=latency_ms)
            if published:
                self.drain_offline_queue()
                return {
                    "ok": True,
                    "action": "PUBLISHED_TO_AWS",
                    "messageId": cleaned["messageId"],
                    "localEvaluation": local_status,
                    "breaches": len(breaches),
                    "cloudConnected": True,
                    "latencyMs": round(latency_ms, 2),
                    "offlineQueueSize": self.queue.size(),
                }

        self.queue.enqueue(cleaned)
        self.mqtt.publish_device_status(
            device_status="OFFLINE",
            offline_queue_size=self.queue.size(),
            device_id=dev_id,
        )
        return {
            "ok": True,
            "action": "BUFFERED_OFFLINE",
            "messageId": cleaned["messageId"],
            "localEvaluation": local_status,
            "breaches": len(breaches),
            "cloudConnected": False,
            "offlineQueueSize": self.queue.size(),
        }

    def drain_offline_queue(self) -> int:
        if not self.connectivity.is_online():
            return 0
        batch = self.queue.peek_batch(limit=SYNC_BATCH_SIZE)
        if not batch:
            return 0

        synced_ids = []
        for item in batch:
            item["bufferedOffline"] = True
            if self.mqtt.publish_vitals(item):
                synced_ids.append(item["messageId"])
            else:
                break

        if synced_ids:
            removed = self.queue.mark_synchronized(synced_ids)
            self.synced_from_buffer_count += removed
            log.info(
                f"Synchronized {removed} queued readings to AWS Cloud (remaining queue={self.queue.size()})"
            )
            self.mqtt.publish_device_status(
                device_status="ONLINE",
                offline_queue_size=self.queue.size(),
            )
            return removed
        return 0

    def run_diagnostics(self) -> Dict[str, Any]:
        host_metrics = get_host_system_metrics()
        self.sensor_bus_status = self.sensors.initialize_sensors()
        conn_summary = self.connectivity.status_summary()
        rtt_ms = conn_summary.get("latencyMs", 4.2)
        queue_depth = self.queue.size()

        recent_logs = []
        try:
            if LOG_FILE.exists():
                lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
                recent_logs = lines[-20:]
        except Exception:
            pass

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deviceId": DEVICE_ID,
            "operatingMode": OPERATING_MODE,
            "hostMetrics": host_metrics,
            "sensorBusStatus": self.sensor_bus_status,
            "network": {
                "cloudReachable": rtt_ms >= 0 and self.connectivity.is_online(),
                "rttLatencyMs": rtt_ms if rtt_ms >= 0 else None,
                "tlsConfigured": self.mqtt.tls_configured,
                "messagesPublished": self.mqtt.messages_published,
                "receivedCount": self.received_count,
                "rejectedCount": self.rejected_count,
                "syncedFromBufferCount": self.synced_from_buffer_count,
            },
            "storage": {
                "sqliteQueueDepth": queue_depth,
                "sqliteDbPath": str(self.queue.db_path),
                "walMode": "ENABLED",
            },
            "recentLogs": recent_logs,
        }


GATEWAY_SERVICE = GatewayService()


class GatewayRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status: int, data: dict):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/dashboard"):
            html_bytes = LOCAL_PI_DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
            return

        if parsed.path in ("/gateway/status", "/health"):
            conn_info = GATEWAY_SERVICE.connectivity.status_summary()
            host_metrics = get_host_system_metrics()
            self._send_json(
                200,
                {
                    "deviceId": DEVICE_ID,
                    "operatingMode": OPERATING_MODE,
                    "receivedCount": GATEWAY_SERVICE.received_count,
                    "rejectedCount": GATEWAY_SERVICE.rejected_count,
                    "publishedCount": GATEWAY_SERVICE.mqtt.messages_published,
                    "syncedFromBufferCount": GATEWAY_SERVICE.synced_from_buffer_count,
                    "offlineQueueSize": GATEWAY_SERVICE.queue.size(),
                    "latestReading": GATEWAY_SERVICE.latest_reading,
                    "latestEvaluation": GATEWAY_SERVICE.latest_evaluation,
                    "sensorBusStatus": GATEWAY_SERVICE.sensor_bus_status,
                    **host_metrics,
                    **conn_info,
                },
            )
            return

        if parsed.path == "/gateway/diagnostics":
            self._send_json(200, GATEWAY_SERVICE.run_diagnostics())
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON body"})
            return

        if parsed.path == "/gateway/telemetry":
            result = GATEWAY_SERVICE.handle_incoming_reading(body)
            self._send_json(200 if result.get("ok") else 400, result)
            return

        if parsed.path == "/gateway/diagnostics":
            self._send_json(200, GATEWAY_SERVICE.run_diagnostics())
            return

        if parsed.path == "/gateway/flush-queue":
            synced = GATEWAY_SERVICE.drain_offline_queue()
            self._send_json(
                200,
                {
                    "ok": True,
                    "syncedMessages": synced,
                    "offlineQueueSize": GATEWAY_SERVICE.queue.size(),
                },
            )
            return

        if parsed.path in ("/gateway/maintenance", "/gateway/simulate-disconnect"):
            offline = bool(body.get("offline", True))
            target_device = body.get("deviceId", DEVICE_ID)
            now_online = GATEWAY_SERVICE.connectivity.set_offline_mode(offline)
            if not now_online:
                GATEWAY_SERVICE.mqtt.publish_device_status(
                    device_status="OFFLINE",
                    offline_queue_size=GATEWAY_SERVICE.queue.size(),
                    device_id=target_device,
                )
            else:
                GATEWAY_SERVICE.mqtt.publish_device_status(
                    device_status="ONLINE",
                    offline_queue_size=GATEWAY_SERVICE.queue.size(),
                    device_id=target_device,
                )
                synced = GATEWAY_SERVICE.drain_offline_queue()
                return self._send_json(
                    200,
                    {
                        "ok": True,
                        "cloudConnected": True,
                        "maintenanceOffline": False,
                        "syncedMessages": synced,
                        "offlineQueueSize": GATEWAY_SERVICE.queue.size(),
                    },
                )
            self._send_json(
                200,
                {
                    "ok": True,
                    "cloudConnected": now_online,
                    "maintenanceOffline": offline,
                    "offlineQueueSize": GATEWAY_SERVICE.queue.size(),
                },
            )
            return

        self._send_json(404, {"error": "Endpoint not found"})


def run_receiver_server():
    server = ThreadingHTTPServer((GATEWAY_HOST, GATEWAY_PORT), GatewayRequestHandler)
    log.info(f"Raspberry Pi 5 Gateway & Local Dashboard listening on http://{GATEWAY_HOST}:{GATEWAY_PORT}")
    server.serve_forever()
