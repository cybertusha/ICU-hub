# ICUGuardian — Doctor Web Application (`doctor-dashboard`)

Centralized hospital ICU monitoring web application for Doctors, Nurses, and System Administrators.

## Screens & Features (Matching `Design/` UI Specifications & PRD)
1. **Role-Based Sign In:** Supports Doctor, Nurse, and Admin authentication + one-click Quick Demo Access.
2. **ICU Live Dashboard:** Real-time KPI summary cards, search/filter/sort by bed, Patient Overview table + Card Grid view, and Presentation Demo Scenario quick controls.
3. **Individual Patient Monitoring Page:** 5 Live Vital-Sign Cards (HR, SpO2, BP, Temp, RR), Real-Time Lead II ECG Waveform visualization, Interactive Trend Charts (`1h`, `6h`, `24h`), Clinical Info sidebar (Condition, Physician, Nurse, Allergies, Medications), and JSON/Report Export.
4. **Alert Management System:** Automated threshold alerts, Web Audio API Critical Alarm sound synthesizer, Acknowledge, Acknowledge All, and Resolve actions, plus severity/category/status filtering.
5. **Report Generator:** Configurable HIPAA-style patient report builder with live preview and export.
6. **User Management (Admin):** Hospital staff directory, role badges, active status switches, and Add User modal.
7. **Device Management (Admin/Doctor):** Raspberry Pi IoT Gateway fleet monitor with one-click **Simulate Offline / Restore Online** for Live Demo 5.
8. **Settings:** Live Alert Thresholds synced with the Cloud Backend, Sound Alert Volume controls, and Light/Dark Hospital Console theme switcher.
9. **Help & Support:** FAQ accordions, Emergency Contact Info, Submit Support Ticket form, My Tickets tracker, and Documentation Resources.

## Running the Doctor Dashboard
```bash
python3 server.py
```
Then open `http://localhost:3000` in your browser.
