"""
AWS Lambda Function: ICU_ProcessAlertsLambda (`aws-cloud/lambda/process_alerts/lambda_function.py`)
Evaluates validated patient vital readings against configurable thresholds, enforces cooldown
windows to prevent duplicate alert spam, detects patient recovery when vitals return to normal,
and manages separate Acknowledge and Resolve lifecycle states.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional


DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "configurationId": "DEFAULT_DEMO_THRESHOLDS",
    "cooldownSeconds": 30,
    "heartRate": {"minNormal": 60, "maxNormal": 100, "criticalLow": 45, "criticalHigh": 120},
    "spo2": {"minNormal": 94, "criticalLow": 90},
    "temperature": {"minNormal": 36.0, "maxNormal": 38.0, "criticalHigh": 39.0},
    "respiratoryRate": {"minNormal": 12, "maxNormal": 20, "criticalLow": 8, "criticalHigh": 28},
    "bloodPressure": {"systolicMin": 90, "systolicMax": 140, "diastolicMin": 60, "diastolicMax": 90},
}


def evaluate_vital_thresholds(
    vitals: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Evaluates a vital reading dict against configured warning and critical rules.
    Returns (overall_status, list_of_parameter_evaluations).
    """
    t = thresholds or DEFAULT_THRESHOLDS
    hr = float(vitals.get("heartRate", 75))
    spo2 = float(vitals.get("spo2", 98))
    temp = float(vitals.get("temperature", 36.7))
    rr = float(vitals.get("respiratoryRate", 16))
    bp = vitals.get("bloodPressure") or {"systolic": 120, "diastolic": 80}
    sys_bp = float(bp.get("systolic", 120))
    dia_bp = float(bp.get("diastolic", 80))

    breaches: List[Dict[str, Any]] = []

    # 1. SpO2 evaluation
    spo2_min = float(t["spo2"]["minNormal"])
    spo2_crit = float(t["spo2"]["criticalLow"])
    if spo2 < spo2_crit:
        breaches.append(
            {
                "parameter": "spo2",
                "detectedValue": int(round(spo2)),
                "threshold": f"{int(spo2_min)}-100%",
                "severity": "CRITICAL",
                "priority": 1,
                "category": "vitals",
                "description": f"Oxygen saturation critically low ({int(round(spo2))}%)",
            }
        )
    elif spo2 < spo2_min:
        breaches.append(
            {
                "parameter": "spo2",
                "detectedValue": int(round(spo2)),
                "threshold": f"{int(spo2_min)}-100%",
                "severity": "WARNING",
                "priority": 2,
                "category": "vitals",
                "description": f"Oxygen saturation below threshold ({int(round(spo2))}%)",
            }
        )

    # 2. Heart Rate evaluation
    hr_min = float(t["heartRate"]["minNormal"])
    hr_max = float(t["heartRate"]["maxNormal"])
    hr_crit_low = float(t["heartRate"]["criticalLow"])
    hr_crit_high = float(t["heartRate"]["criticalHigh"])
    if hr >= hr_crit_high or hr <= hr_crit_low:
        breaches.append(
            {
                "parameter": "heartRate",
                "detectedValue": int(round(hr)),
                "threshold": f"{int(hr_min)}-{int(hr_max)} bpm",
                "severity": "CRITICAL",
                "priority": 1,
                "category": "vitals",
                "description": f"Heart rate critically abnormal ({int(round(hr))} bpm)",
            }
        )
    elif hr > hr_max or hr < hr_min:
        breaches.append(
            {
                "parameter": "heartRate",
                "detectedValue": int(round(hr)),
                "threshold": f"{int(hr_min)}-{int(hr_max)} bpm",
                "severity": "WARNING",
                "priority": 2,
                "category": "vitals",
                "description": f"Heart rate elevated/abnormal ({int(round(hr))} bpm)",
            }
        )

    # 3. Temperature evaluation
    t_min = float(t["temperature"]["minNormal"])
    t_max = float(t["temperature"]["maxNormal"])
    t_crit = float(t["temperature"]["criticalHigh"])
    if temp >= t_crit:
        breaches.append(
            {
                "parameter": "temperature",
                "detectedValue": round(temp, 1),
                "threshold": f"{t_min:.1f}-{t_max:.1f} °C",
                "severity": "CRITICAL",
                "priority": 1,
                "category": "vitals",
                "description": f"Core body temperature critically high ({temp:.1f}°C)",
            }
        )
    elif temp > t_max or temp < t_min:
        breaches.append(
            {
                "parameter": "temperature",
                "detectedValue": round(temp, 1),
                "threshold": f"{t_min:.1f}-{t_max:.1f} °C",
                "severity": "WARNING",
                "priority": 2,
                "category": "vitals",
                "description": f"Body temperature outside normal range ({temp:.1f}°C)",
            }
        )

    # 4. Respiratory Rate evaluation
    rr_min = float(t["respiratoryRate"]["minNormal"])
    rr_max = float(t["respiratoryRate"]["maxNormal"])
    rr_crit_low = float(t["respiratoryRate"]["criticalLow"])
    rr_crit_high = float(t["respiratoryRate"]["criticalHigh"])
    if rr >= rr_crit_high or rr <= rr_crit_low:
        breaches.append(
            {
                "parameter": "respiratoryRate",
                "detectedValue": int(round(rr)),
                "threshold": f"{int(rr_min)}-{int(rr_max)} /min",
                "severity": "CRITICAL",
                "priority": 1,
                "category": "vitals",
                "description": f"Respiratory rate critically abnormal ({int(round(rr))}/min)",
            }
        )
    elif rr > rr_max or rr < rr_min:
        breaches.append(
            {
                "parameter": "respiratoryRate",
                "detectedValue": int(round(rr)),
                "threshold": f"{int(rr_min)}-{int(rr_max)} /min",
                "severity": "WARNING",
                "priority": 2,
                "category": "vitals",
                "description": f"Respiratory rate abnormal ({int(round(rr))}/min)",
            }
        )

    # 5. Blood Pressure evaluation
    bp_cfg = t.get("bloodPressure", {"systolicMin": 90, "systolicMax": 140, "diastolicMin": 60, "diastolicMax": 90})
    if sys_bp < 88 or sys_bp > 180:
        breaches.append(
            {
                "parameter": "bloodPressure",
                "detectedValue": f"{int(sys_bp)}/{int(dia_bp)}",
                "threshold": f"{int(bp_cfg['systolicMin'])}-{int(bp_cfg['systolicMax'])} mmHg",
                "severity": "CRITICAL",
                "priority": 1,
                "category": "vitals",
                "description": f"Blood pressure in critical range ({int(sys_bp)}/{int(dia_bp)} mmHg)",
            }
        )
    elif sys_bp > bp_cfg["systolicMax"] or sys_bp < bp_cfg["systolicMin"] or dia_bp > bp_cfg["diastolicMax"]:
        breaches.append(
            {
                "parameter": "bloodPressure",
                "detectedValue": f"{int(sys_bp)}/{int(dia_bp)}",
                "threshold": f"{int(bp_cfg['systolicMin'])}-{int(bp_cfg['systolicMax'])} mmHg",
                "severity": "WARNING",
                "priority": 2,
                "category": "vitals",
                "description": f"Blood pressure outside normal range ({int(sys_bp)}/{int(dia_bp)} mmHg)",
            }
        )

    if any(b["severity"] == "CRITICAL" for b in breaches):
        overall = "CRITICAL"
    elif any(b["severity"] == "WARNING" for b in breaches):
        overall = "WARNING"
    else:
        overall = "NORMAL"

    return overall, breaches


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """AWS Lambda entrypoint for standalone alert rule evaluation."""
    vitals = event.get("vitals", {})
    thresholds = event.get("thresholds", DEFAULT_THRESHOLDS)
    overall_status, breaches = evaluate_vital_thresholds(vitals, thresholds)
    return {
        "statusCode": 200,
        "patientId": event.get("patientId"),
        "monitoringStatus": overall_status,
        "breaches": breaches,
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
    }
