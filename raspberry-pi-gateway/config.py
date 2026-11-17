"""
Production Configuration for the Raspberry Pi Bedside IoT Gateway.
Loads settings from environment variables for bedside deployment and AWS IoT Core connectivity.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
CERTS_DIR = Path(os.environ.get("IOT_CERTS_DIR", str(BASE_DIR / "certs")))

# Gateway Identity & Operating Mode
DEVICE_ID = os.environ.get("DEVICE_ID", "ICU-PI-001")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "ICU-01 Bedside Gateway")
OPERATING_MODE = os.environ.get("OPERATING_MODE", "BEDSIDE_MONITOR")  # HARDWARE or BEDSIDE_MONITOR
ASSIGNED_PATIENT_ID = os.environ.get("ASSIGNED_PATIENT_ID", "PATIENT-001")
FIRMWARE_VERSION = os.environ.get("FIRMWARE_VERSION", "2.1.0-prod")

# Local Network Receiver (Bedside Monitor / Local Sensor Daemon -> Raspberry Pi)
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "5050"))

# AWS IoT Core MQTT over TLS Configuration
AWS_IOT_ENDPOINT = os.environ.get(
    "AWS_IOT_ENDPOINT", "iot.us-east-1.amazonaws.com"
)
AWS_IOT_PORT = int(os.environ.get("AWS_IOT_PORT", "8883"))
AWS_IOT_ROOT_CA = os.environ.get("AWS_IOT_ROOT_CA", str(CERTS_DIR / "AmazonRootCA1.pem"))
AWS_IOT_CERT = os.environ.get("AWS_IOT_CERT", str(CERTS_DIR / "device.pem.crt"))
AWS_IOT_PRIVATE_KEY = os.environ.get("AWS_IOT_PRIVATE_KEY", str(CERTS_DIR / "private.pem.key"))

# MQTT Topic Templates
TOPIC_VITALS = "icu/devices/{deviceId}/vitals"
TOPIC_STATUS = "icu/devices/{deviceId}/status"
TOPIC_ALERTS = "icu/patients/{patientId}/alerts"
TOPIC_COMMANDS = "icu/devices/{deviceId}/commands"

# Cloud Backend Ingestion URL
CLOUD_BACKEND_URL = os.environ.get("CLOUD_BACKEND_URL", "http://127.0.0.1:8000")

# Persistent Offline Queue (SQLite WAL)
OFFLINE_DB_PATH = Path(os.environ.get("OFFLINE_DB_PATH", str(BASE_DIR / "offline_queue.db")))
MAX_OFFLINE_QUEUE_SIZE = int(os.environ.get("MAX_OFFLINE_QUEUE_SIZE", "25000"))
SYNC_BATCH_SIZE = int(os.environ.get("SYNC_BATCH_SIZE", "50"))

# Default Clinical Alarm Thresholds (Configurable from Hospital Central Station)
DEFAULT_THRESHOLDS = {
    "heartRate": {"minNormal": 60, "maxNormal": 100, "criticalLow": 45, "criticalHigh": 120},
    "spo2": {"minNormal": 94, "criticalLow": 90},
    "temperature": {"minNormal": 36.0, "maxNormal": 38.0, "criticalHigh": 39.0},
    "respiratoryRate": {"minNormal": 12, "maxNormal": 20, "criticalLow": 8, "criticalHigh": 28},
    "bloodPressure": {"systolicMin": 90, "systolicMax": 140, "diastolicMin": 60, "diastolicMax": 90},
}
