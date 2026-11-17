"""
Data validation, outlier filtering, and threshold evaluation processor for Raspberry Pi Gateway.
Ensures malformed or physiologically impossible sensor readings are rejected before transmission.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List, Optional
from config import DEVICE_ID, DEFAULT_THRESHOLDS
from logger import get_logger

log = get_logger("data_processor")


class DataProcessor:
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.seen_message_ids: set = set()
        self.max_dedup_cache = 5000

    def validate_and_enrich(self, raw_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        if not isinstance(raw_payload, dict):
            return False, {}, "Payload must be a JSON object"

        patient_id = raw_payload.get("patientId")
        if not patient_id or not isinstance(patient_id, str) or not patient_id.startswith("PATIENT-"):
            return False, {}, f"Invalid or missing patientId: {patient_id}"

        vitals = raw_payload.get("vitals")
        if not isinstance(vitals, dict):
            return False, {}, "Missing or invalid 'vitals' object"

        required_vitals = ["heartRate", "spo2", "temperature", "respiratoryRate"]
        for key in required_vitals:
            if key not in vitals or not isinstance(vitals[key], (int, float)):
                return False, {}, f"Missing or non-numeric vital parameter: '{key}'"

        hr = float(vitals["heartRate"])
        spo2 = float(vitals["spo2"])
        temp = float(vitals["temperature"])
        rr = float(vitals["respiratoryRate"])

        if not (0 <= hr <= 300):
            return False, {}, f"Heart rate out of valid physiological range [0, 300]: {hr}"
        if not (0 <= spo2 <= 100):
            return False, {}, f"SpO2 out of valid percentage range [0, 100]: {spo2}"
        if not (25.0 <= temp <= 45.0):
            return False, {}, f"Temperature out of valid Celsius range [25.0, 45.0]: {temp}"
        if not (0 <= rr <= 100):
            return False, {}, f"Respiratory rate out of valid range [0, 100]: {rr}"

        message_id = raw_payload.get("messageId") or (
            f"MSG-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6].upper()}"
        )
        if message_id in self.seen_message_ids:
            return False, {}, f"Duplicate messageId rejected: {message_id}"

        if len(self.seen_message_ids) >= self.max_dedup_cache:
            self.seen_message_ids.clear()
        self.seen_message_ids.add(message_id)

        bp = vitals.get("bloodPressure") or {"systolic": 120, "diastolic": 80}
        ecg = vitals.get("ecg") if isinstance(vitals.get("ecg"), list) else []
        cleaned_ecg = [round(float(x), 4) for x in ecg[:250] if isinstance(x, (int, float))]

        raw_mode = raw_payload.get("mode", "BEDSIDE_MONITOR")
        mode = raw_mode if raw_mode in ("HARDWARE", "BEDSIDE_MONITOR", "SIMULATION") else "BEDSIDE_MONITOR"
        profile = str(raw_payload.get("signalProfile") or raw_payload.get("scenario") or "NORMAL_SINUS")

        cleaned = {
            "messageId": str(message_id),
            "deviceId": str(raw_payload.get("deviceId") or DEVICE_ID),
            "patientId": patient_id,
            "timestamp": str(raw_payload.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            "mode": mode,
            "signalProfile": profile,
            "bufferedOffline": bool(raw_payload.get("bufferedOffline", False)),
            "vitals": {
                "heartRate": int(round(hr)),
                "spo2": int(round(spo2)),
                "temperature": round(temp, 1),
                "respiratoryRate": int(round(rr)),
                "bloodPressure": {
                    "systolic": int(round(float(bp.get("systolic", 120)))),
                    "diastolic": int(round(float(bp.get("diastolic", 80)))),
                },
                "ecg": cleaned_ecg,
            },
        }
        return True, cleaned, ""

    def detect_local_abnormalities(self, cleaned_payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        v = cleaned_payload["vitals"]
        hr = v["heartRate"]
        spo2 = v["spo2"]
        temp = v["temperature"]
        rr = v["respiratoryRate"]
        t = self.thresholds

        breaches: List[Dict[str, Any]] = []
        if spo2 < t["spo2"]["criticalLow"]:
            breaches.append({"parameter": "spo2", "value": spo2, "severity": "CRITICAL", "desc": "Oxygen saturation critically low"})
        elif spo2 < t["spo2"]["minNormal"]:
            breaches.append({"parameter": "spo2", "value": spo2, "severity": "WARNING", "desc": "Oxygen saturation below normal range"})

        if hr > t["heartRate"]["criticalHigh"] or hr < t["heartRate"]["criticalLow"]:
            breaches.append({"parameter": "heartRate", "value": hr, "severity": "CRITICAL", "desc": "Heart rate in critical range"})
        elif hr > t["heartRate"]["maxNormal"] or hr < t["heartRate"]["minNormal"]:
            breaches.append({"parameter": "heartRate", "value": hr, "severity": "WARNING", "desc": "Heart rate outside normal range"})

        if temp >= t["temperature"]["criticalHigh"]:
            breaches.append({"parameter": "temperature", "value": temp, "severity": "CRITICAL", "desc": "Body temperature critically elevated"})
        elif temp > t["temperature"]["maxNormal"] or temp < t["temperature"]["minNormal"]:
            breaches.append({"parameter": "temperature", "value": temp, "severity": "WARNING", "desc": "Body temperature abnormal"})

        if rr > t["respiratoryRate"]["criticalHigh"] or rr < t["respiratoryRate"]["criticalLow"]:
            breaches.append({"parameter": "respiratoryRate", "value": rr, "severity": "CRITICAL", "desc": "Respiratory rate critically abnormal"})
        elif rr > t["respiratoryRate"]["maxNormal"] or rr < t["respiratoryRate"]["minNormal"]:
            breaches.append({"parameter": "respiratoryRate", "value": rr, "severity": "WARNING", "desc": "Respiratory rate outside normal range"})

        if any(b["severity"] == "CRITICAL" for b in breaches):
            return "CRITICAL", breaches
        if any(b["severity"] == "WARNING" for b in breaches):
            return "WARNING", breaches
        return "NORMAL", []
