<<<<<<< HEAD
# ICUGuardian — Real-Time IoT-Based ICU Patient Monitoring System

End-to-end hospital ICU patient monitoring platform integrating bedside multiparameter sensor acquisition, Raspberry Pi edge IoT gateways, AWS Cloud serverless processing, and a centralized real-time clinician web station.

---

## 1. Launch the System

Start all four production tiers with a single script:

```bash
chmod +x start_demo.sh
./start_demo.sh
```

| Tier | Service | Local Endpoint | Credentials / Details |
|---|---|---|---|
| **1. Central Station (`ICUGuardian`)** | [doctor-dashboard/server.py](file:///home/tushar/Documents/ICU/doctor-dashboard/server.py) | `http://localhost:3000` | Physician: `sarah.smith` / `doctor123`<br>Nurse: `michael.jones` / `nurse123`<br>Admin/Engineering: `lisa.wilson` / `admin123` |
| **2. Bedside Multiparameter Monitor** | [patient-monitor-pc/server.py](file:///home/tushar/Documents/ICU/patient-monitor-pc/server.py) | `http://localhost:3001` | Real-time Lead II ECG & SpO₂ Plethysmograph oscilloscopes, NIBP/MAP calculation & signal calibration profiles |
| **3. Raspberry Pi Bedside Gateway** | [raspberry-pi-gateway/main.py](file:///home/tushar/Documents/ICU/raspberry-pi-gateway/main.py) | `http://localhost:5050/gateway/status` | Hardware I2C/1-Wire/SPI sensor drivers, Linux SoC telemetry, MQTT/TLS client & SQLite WAL store-and-forward queue |
| **4. Cloud Backend & WebSocket API** | [aws-cloud/cloud_backend_server.py](file:///home/tushar/Documents/ICU/aws-cloud/cloud_backend_server.py) | `http://localhost:8000/api/health` (`ws://localhost:8000/ws`) | PBKDF2-SHA256 + JWT auth, vital ingestion, threshold alert engine, clinical chart notes & immutable audit log |

---

## 2. Production Capabilities

- **PBKDF2-HMAC-SHA256 & JWT Authentication:** Salted password hashing (`100,000` iterations) with HMAC-SHA256 signed JWT session tokens, role-based access (`Doctor`, `Nurse`, `Admin`), live password rotation, and an immutable security/clinical audit trail (`/api/audit-logs`).
- **Complete Patient Clinical Workflow:** Admit new ICU patients (`POST /api/patients`), assign bedside Raspberry Pi gateways, edit diagnoses/allergies/medications (`PATCH /api/patients/{id}`), record timestamped clinical progress notes (`POST /api/patients/{id}/notes`), toggle per-patient alarm muting, and query historical vitals across `1h`, `6h`, `24h`, or custom ISO date-time windows.
- **Physical Sensor & Host Telemetry Integration:**
  - `raspberry-pi-gateway/sensor_manager.py` interfaces with **MAX30102** (`I2C 0x57`), **DS18B20** (`1-Wire /sys/bus/w1/devices/28-*`), and **AD8232 + MCP3008** (`SPI0 /dev/spidev0.0`).
  - Reads live Linux kernel metrics (`/sys/class/thermal/thermal_zone0/temp`, `/proc/loadavg`, `/proc/meminfo`, `/proc/uptime`) and exposes real-time edge diagnostics via `/gateway/diagnostics` and `/api/devices/{id}/diagnostics`.
- **Store-and-Forward Edge Resilience:** Persistent SQLite WAL queue (`offline_queue.db`) buffers patient readings during network interruptions and automatically synchronizes queued frames in FIFO order upon upstream restoration.

---

## 3. Automated Verification

```bash
# Validate JSON data contracts
python3 shared/validate_schemas.py

# Run Raspberry Pi Gateway validation & SQLite WAL queue self-test
python3 raspberry-pi-gateway/main.py --self-test

# Run full End-to-End Production Integration Test Suite
python3 infrastructure/deployment-scripts/e2e_integration_test.py
```
=======
# ICU
>>>>>>> 87ef45b649c3dcd27bf14d7ea1175eb3880d7250
