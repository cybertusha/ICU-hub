# Bedside ICU Patient Monitor (`patient-monitor-pc`)

This module implements the **Bedside ICU Patient Monitor & Vital Sign Simulator** running on the demonstration PC.

## Features
- **Real-Time Vital Sign Display:** Heart Rate (BPM), SpO2 (%), Body Temperature (°C), Respiratory Rate (breaths/min), Blood Pressure (SYS/DIA mmHg), and a sweeping Lead II PQRST ECG Waveform oscilloscope.
- **7 Presentation Scenarios:**
  1. `NORMAL` — Normal sinus rhythm
  2. `HIGH_HR` — Tachycardia (>120 BPM)
  3. `LOW_SPO2` — Hypoxemia (<90% SpO2)
  4. `HIGH_TEMP` — Hyperpyrexia (>38.8°C)
  5. `ABNORMAL_RR` — Tachypnea (>28 breaths/min)
  6. `CRITICAL` — Multi-parameter ICU crisis
  7. `RECOVERY` — Smooth recovery to normal physiological range
- **Local Network Transmission:** Continuously posts JSON telemetry packets to the Raspberry Pi IoT Gateway (`http://<raspberry-pi-ip>:5050/gateway/telemetry`).

## Running the Bedside Monitor
```bash
python3 server.py
```
Then open `http://localhost:3001` in your browser.
