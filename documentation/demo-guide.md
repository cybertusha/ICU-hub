# Live College Presentation & Demonstration Script
## Real-Time IoT-Based ICU Patient Monitoring System (`ICUGuardian`)

---

## Pre-Presentation Setup (2 Minutes Before Stage Demo)

1. Run `./start_demo.sh` in the terminal.
2. Open **Window 1 (Bedside ICU Monitor PC):** [http://localhost:3001](http://localhost:3001)
3. Open **Window 2 (Doctor Web Dashboard — ICUGuardian):** [http://localhost:3000](http://localhost:3000)
4. On the Doctor Dashboard login screen, click **Demo Doctor** (or sign in as `doctor` / `doctor123`).

---

## Step-by-Step Live Demonstration Walkthrough

### DEMO 1: Normal Patient Monitoring
1. **Action:** Point to **Bedside Monitor (`:3001`)** where **Emily Johnson (`ICU-01`, `PATIENT-001`)** is in the **1. Normal Patient** scenario (or click `Demo 1: Normal` on the Doctor Dashboard).
2. **What Happens:**
   - The Bedside PC generates realistic normal vitals (HR ~73 BPM, SpO₂ ~98%, Temp ~36.6°C, RR ~17/min, BP ~120/78) and a sweeping green Lead II ECG waveform.
   - Telemetry is sent to the **Raspberry Pi Gateway (`ICU-PI-001`)**, validated, and published to the Cloud Backend.
   - On the **Doctor Dashboard (`:3000`)**, Emily Johnson's row shows a green `NORMAL` badge and updates automatically via WebSocket.

### DEMO 2: Critical Patient Condition (Low SpO₂ Hypoxemia)
1. **Action:** On the Bedside Monitor (`:3001`), click **3. Low SpO2** (or click `Demo 2: Low SpO₂ (Critical)` on the Doctor Dashboard).
2. **What Happens:**
   - Simulated SpO₂ drops below `90%` (`85–88%`).
   - Raspberry Pi validates and forwards the reading.
   - The Cloud Alert Engine detects that SpO₂ crossed the critical threshold (`<90%`) and generates a `CRITICAL` alert.
   - **Doctor Dashboard (`:3000`)** immediately plays the **ICU Critical Audio Alarm**, displays a red toast notification (`🚨 CRITICAL ALERT — Emily Johnson (ICU-01)`), and changes her status badge to `CRITICAL`.

### DEMO 3: High Heart Rate (Tachycardia) & Live Trend Visualization
1. **Action:** Switch the scenario to **2. High Heart Rate** (or click `Demo 3: High Heart Rate`), then click **Monitor** on Emily Johnson's row to open her **Individual Patient Monitoring Page**.
2. **What Happens:**
   - Heart Rate climbs above `125 BPM`.
   - The **Real-Time ECG Waveform** speeds up and turns red, and the **Heart Rate Trend Chart** plots the spike in real time.

### DEMO 4: Patient Recovery & Alert Lifecycle (Acknowledge vs. Resolve)
1. **Action:** Click **7. Patient Recovery** on the Bedside Monitor (or `Demo 4: Recovery` on the dashboard).
2. **What Happens:**
   - Emily Johnson's vitals smoothly return to normal range (`HR ~74 BPM`, `SpO₂ ~98%`).
   - Her status badge automatically returns to green `NORMAL`, and active alerts are tagged with a green `✓ RECOVERED` badge.
3. **Action:** Navigate to the **Alerts** tab in the left sidebar.
   - Click **Acknowledge** on the pending alert (status changes to `✓ Acknowledged by Dr. Sarah Smith`).
   - Click **Resolve** (status changes to `✓ Resolved`, while the alert remains preserved in the historical audit table when filtering by `Resolved History`).

### DEMO 5: Internet Disconnection, Offline SQLite Buffering & Automatic Recovery
1. **Action:** Click **🔌 Demo 5: Disconnect Pi Internet** on the dashboard bar (or go to **Device Management** and click **Simulate Offline** on `ICU-01 Monitor Hub`).
2. **What Happens:**
   - The sidebar status changes to `⚠️ Connection Issues` and `ICU-PI-001` shows `OFFLINE`.
   - On the **Bedside Monitor (`:3001`)**, the footer shows `Cloud: OFFLINE (Buffering)` and the `Pi Offline Buffer` counter increments (`1, 2, 3...`) as readings are saved into the Raspberry Pi's persistent SQLite WAL database (`offline_queue.db`).
3. **Action:** Click **🌐 Demo 5: Reconnect Pi & Sync Buffer**.
4. **What Happens:**
   - The Raspberry Pi automatically reconnects, drains all buffered readings in chronological FIFO order to the Cloud Backend, and resets its offline buffer count to `0` without losing a single reading!
