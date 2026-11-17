# Testing & Quality Assurance Guide
## Real-Time IoT-Based ICU Patient Monitoring System

---

## 1. Automated Verification Commands

Every phase of the project includes an automated verification script:

### Phase 1: JSON Schema & Data Contract Validation
```bash
python3 shared/validate_schemas.py
```

### Phase 2: Bedside ICU Patient Simulator Self-Test (All 7 Scenarios)
```bash
python3 patient-monitor-pc/simulator/patient_simulator.py
```

### Phase 3: Raspberry Pi Gateway Validation & Offline SQLite Queue Self-Test
```bash
python3 raspberry-pi-gateway/main.py --self-test
```

### Phase 4: DynamoDB Table Schema Verification
```bash
python3 aws-cloud/dynamodb/provision_dynamodb.py
```

### Phase 6: Complete End-to-End Integration & Live Demo 1–5 Test Suite
```bash
python3 infrastructure/deployment-scripts/e2e_integration_test.py
```

---

## 2. End-to-End Acceptance Checklist (PRD Section 19.6)

- [x] PC patient simulator starts successfully (`http://localhost:3001`).
- [x] All seven abnormal, normal, and recovery scenarios work (`NORMAL`, `HIGH_HR`, `LOW_SPO2`, `HIGH_TEMP`, `ABNORMAL_RR`, `CRITICAL`, `RECOVERY`).
- [x] Patient readings update continuously in real time.
- [x] Raspberry Pi receives simulator data over local network (`http://localhost:5050/gateway/telemetry`).
- [x] Raspberry Pi validates incoming readings and rejects out-of-range spikes.
- [x] AWS IoT Core / Cloud Backend receives MQTT telemetry envelopes.
- [x] Lambda processor (`process_vitals` & `process_alerts`) evaluates incoming messages.
- [x] Database stores 24-hour historical readings and deduplicates by `messageId`.
- [x] Doctor Dashboard (`http://localhost:3000`) displays live readings via WebSocket (`/ws`).
- [x] Trend graphs and sweeping ECG waveform update automatically.
- [x] Alerts are generated automatically with cooldown deduplication.
- [x] Web Audio API critical alarm sound plays for critical demonstration events.
- [x] Doctors and Nurses can acknowledge alerts (`Acknowledge` & `Acknowledge All`).
- [x] Doctors can resolve alerts (`Resolve`), retaining resolved alerts in historical records.
- [x] Patient recovery is automatically detected (`recoveredAt` badge).
- [x] Device connectivity status (`ONLINE` / `OFFLINE`) updates in real time.
- [x] Offline persistent SQLite buffering (`offline_queue.db`) works during internet outages.
- [x] Automatic reconnection and FIFO queue synchronization work when internet is restored.
