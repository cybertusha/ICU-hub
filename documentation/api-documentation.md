# API & Communication Protocol Documentation
## Real-Time IoT-Based ICU Patient Monitoring System

---

## 1. Local Network Protocol (PC Bedside Simulator ↔ Raspberry Pi Gateway)

The Bedside PC Monitor communicates with the Raspberry Pi Gateway over the local network via HTTP REST or MQTT:

### `POST /gateway/telemetry` (or Backend `/api/telemetry`)
Transfers a real-time vital reading from the Bedside PC Simulator to the Raspberry Pi Gateway.

**Request Payload:**
```json
{
  "messageId": "MSG-1763356800-001",
  "deviceId": "ICU-PI-001",
  "patientId": "PATIENT-001",
  "timestamp": "2026-11-17T05:15:00.000Z",
  "mode": "SIMULATION",
  "scenario": "NORMAL",
  "vitals": {
    "heartRate": 73,
    "spo2": 97,
    "temperature": 36.6,
    "respiratoryRate": 17,
    "bloodPressure": {
      "systolic": 126,
      "diastolic": 84
    },
    "ecg": [0.02, 0.05, 0.12, -0.08, 0.95, -0.22, 0.04, 0.18, 0.01]
  }
}
```

---

## 2. Cloud REST API Endpoints (API Gateway / FastAPI Backend)

Base URL: `http://localhost:8000/api` (Local/Hybrid Mode) or `https://{api-id}.execute-api.{region}.amazonaws.com/prod/api` (AWS Mode)

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Authenticate Doctor, Nurse, or Admin; returns JWT session token & user profile |
| `GET` | `/api/auth/me` | Validate current session token and return active user |

### Patients & Historical Vitals
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/patients` | List all registered ICU patients with latest vitals, status, active alert counts, and device status |
| `GET` | `/api/patients/{patientId}` | Get detailed patient profile, latest vitals, and active alerts |
| `GET` | `/api/patients/{patientId}/history?hours=1` | Get historical vital-sign readings (`1h`, `6h`, `24h`, or custom `start` & `end` ISO timestamps) |
| `PATCH` | `/api/patients/{patientId}` | Update patient monitoring preferences (e.g., toggle `alertsEnabled`) |

### Automated Alerts Management
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/alerts` | List alerts with optional query filters: `severity`, `category`, `status` (`active`, `acknowledged`, `resolved`), `patientId` |
| `POST` | `/api/alerts/{alertId}/acknowledge` | Acknowledge an alert (records `acknowledgedBy` and `acknowledgedAt`) |
| `POST` | `/api/alerts/acknowledge-all` | Acknowledge all currently unacknowledged alerts |
| `POST` | `/api/alerts/{alertId}/resolve` | Resolve an alert (separate operation from acknowledgment; retains alert in history) |

### Raspberry Pi Gateway & Device Fleet Management
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/devices` | Retrieve all registered Raspberry Pi gateways, IP addresses, uptime, status, and offline queue counts |
| `POST` | `/api/devices/{deviceId}/status` | Update device connectivity status (`ONLINE`, `OFFLINE`, `MAINTENANCE`) |
| `POST` | `/api/devices/{deviceId}/simulate-disconnect` | Toggle simulated internet disconnection on the Raspberry Pi gateway for Live Demo 5 |

### System Settings, Users & Support Tickets
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings/thresholds` | Retrieve active vital-sign alert thresholds |
| `PUT` | `/api/settings/thresholds` | Update configurable warning/critical thresholds and cooldown period |
| `POST` | `/api/settings/thresholds/reset` | Reset thresholds to default demonstration values |
| `GET` | `/api/users` | List hospital staff accounts (Admin role) |
| `POST` | `/api/users` | Create a new staff user account (Admin role) |
| `PATCH` | `/api/users/{userId}` | Toggle user active status or update role |
| `GET` | `/api/tickets` | List technical support tickets |
| `POST` | `/api/tickets` | Submit a new technical support ticket |

---

## 3. Real-Time WebSocket Protocol (`/ws`)

WebSocket Endpoint: `ws://localhost:8000/ws` or `wss://{ws-api-id}.execute-api.{region}.amazonaws.com/prod`

### Server → Client Broadcast Events

1. **`VITAL_UPDATE`** — Sent immediately when a new validated reading arrives from Raspberry Pi / Simulator:
```json
{
  "event": "VITAL_UPDATE",
  "data": {
    "patientId": "PATIENT-001",
    "deviceId": "ICU-PI-001",
    "timestamp": "2026-11-17T05:15:01.000Z",
    "mode": "SIMULATION",
    "scenario": "NORMAL",
    "monitoringStatus": "NORMAL",
    "vitals": {
      "heartRate": 73,
      "spo2": 97,
      "temperature": 36.6,
      "respiratoryRate": 17,
      "bloodPressure": { "systolic": 126, "diastolic": 84 },
      "ecg": [0.02, 0.08, 0.11, -0.09, 0.94, -0.21, 0.03, 0.16, 0.0]
    }
  }
}
```

2. **`ALERT_NEW` / `ALERT_UPDATED`** — Sent when an abnormal condition triggers an alert or when an alert is acknowledged/resolved/recovered:
```json
{
  "event": "ALERT_NEW",
  "data": {
    "alertId": "ALT-1008",
    "patientId": "PATIENT-003",
    "patientName": "Sarah Davis",
    "bedNumber": "ICU-03",
    "parameter": "spo2",
    "category": "vitals",
    "priority": 1,
    "detectedValue": 88,
    "threshold": "94-100%",
    "severity": "CRITICAL",
    "description": "Oxygen saturation critically low",
    "createdAt": "2026-11-17T05:15:02.000Z",
    "acknowledged": false,
    "resolved": false
  }
}
```

3. **`DEVICE_STATUS`** — Sent when a Raspberry Pi connects, disconnects, buffers offline data, or synchronizes its queue:
```json
{
  "event": "DEVICE_STATUS",
  "data": {
    "deviceId": "ICU-PI-001",
    "deviceStatus": "OFFLINE",
    "offlineQueueSize": 14,
    "lastSeen": "2026-11-17T05:15:05.000Z"
  }
}
```
