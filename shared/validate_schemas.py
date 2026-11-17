#!/usr/bin/env python3
"""
Production Schema & Data Contract Validator
Validates all JSON schemas in shared/data-schema/ and tests entity payloads.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_DIR = Path(__file__).parent / "data-schema"

REQUIRED_SCHEMAS = [
    "patient.schema.json",
    "vitals.schema.json",
    "alert.schema.json",
    "device.schema.json",
    "threshold.schema.json",
]


def validate_schema_file(schema_path: Path) -> dict:
    if not schema_path.exists():
        raise FileNotFoundError(f"Missing schema file: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert "$schema" in schema, f"Missing $schema in {schema_path.name}"
    assert "title" in schema, f"Missing title in {schema_path.name}"
    assert "properties" in schema, f"Missing properties in {schema_path.name}"
    assert "required" in schema, f"Missing required fields in {schema_path.name}"
    return schema


def validate_payload_against_schema(payload: dict, schema: dict, name: str) -> None:
    for req_field in schema.get("required", []):
        if req_field not in payload:
            raise ValueError(f"[{name}] Missing required field: '{req_field}'")

    if schema.get("additionalProperties") is False:
        allowed = set(schema.get("properties", {}).keys())
        extra = set(payload.keys()) - allowed
        if extra:
            raise ValueError(f"[{name}] Unexpected extra fields: {extra}")


def main() -> int:
    print("=" * 65)
    print("Validating ICUGuardian Production JSON Schemas")
    print("=" * 65)

    loaded_schemas = {}
    for filename in REQUIRED_SCHEMAS:
        path = SCHEMA_DIR / filename
        schema = validate_schema_file(path)
        loaded_schemas[filename] = schema
        print(f"  [OK] Verified {filename} (title={schema['title']})")

    now_iso = datetime.now(timezone.utc).isoformat()

    sample_patient = {
        "patientId": "PATIENT-001",
        "mrn": "MRN-849201",
        "patientName": "Emily Johnson",
        "age": 45,
        "gender": "F",
        "bedNumber": "ICU-01",
        "monitoringDeviceId": "ICU-PI-001",
        "monitoringStatus": "NORMAL",
        "condition": "Post-operative cardiac monitoring",
        "attendingPhysician": "Dr. Sarah Smith",
        "primaryNurse": "Nurse Michael Jones",
        "allergies": ["Penicillin", "Iodine"],
        "currentMedications": ["Morphine 2mg/hr", "Propofol 50mcg/kg/min"],
        "careNotes": [
            {
                "noteId": "NOTE-001",
                "author": "Dr. Sarah Smith",
                "role": "Doctor",
                "note": "Patient hemodynamically stable post-op.",
                "createdAt": now_iso,
            }
        ],
        "alertsEnabled": True,
        "admittedAt": now_iso,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    validate_payload_against_schema(
        sample_patient, loaded_schemas["patient.schema.json"], "Patient"
    )
    print("  [OK] Patient entity conforms to patient.schema.json")

    sample_vitals = {
        "messageId": "MSG-000001",
        "deviceId": "ICU-PI-001",
        "patientId": "PATIENT-001",
        "timestamp": now_iso,
        "mode": "BEDSIDE_MONITOR",
        "signalProfile": "NORMAL_SINUS",
        "bufferedOffline": False,
        "vitals": {
            "heartRate": 73,
            "spo2": 97,
            "temperature": 36.6,
            "respiratoryRate": 17,
            "bloodPressure": {"systolic": 126, "diastolic": 84},
            "ecg": [0.01, 0.05, 0.12, -0.08, 0.95, -0.22, 0.04, 0.18, 0.0],
        },
    }
    validate_payload_against_schema(
        sample_vitals, loaded_schemas["vitals.schema.json"], "VitalReading"
    )
    print("  [OK] VitalReading payload conforms to vitals.schema.json")

    sample_device = {
        "deviceId": "ICU-PI-001",
        "deviceName": "ICU-01 Monitor Hub",
        "deviceType": "raspberry-pi",
        "location": "ICU Ward A",
        "ipAddress": "192.168.1.101",
        "macAddress": "DC:A6:32:4F:11:01",
        "deviceStatus": "ONLINE",
        "uptime": "10d 16h",
        "lastSeen": now_iso,
        "firmwareVersion": "1.4.2",
        "operatingMode": "BEDSIDE_MONITOR",
        "assignedPatientId": "PATIENT-001",
        "bedNumber": "ICU-01",
        "offlineQueueSize": 0,
        "cpuTempC": 44.2,
        "cpuUsagePct": 14.5,
        "memoryUsagePct": 32.0,
        "latencyMs": 12.4,
        "sensorBusStatus": {
            "MAX30102_I2C": "STANDBY",
            "DS18B20_1WIRE": "STANDBY",
            "AD8232_SPI": "STANDBY",
        },
        "createdAt": now_iso,
    }
    validate_payload_against_schema(
        sample_device, loaded_schemas["device.schema.json"], "Device"
    )
    print("  [OK] Device entity conforms to device.schema.json")

    print("=" * 65)
    print("ALL PRODUCTION SCHEMAS VALIDATED SUCCESSFULLY!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
