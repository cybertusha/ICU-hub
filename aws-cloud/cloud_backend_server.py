#!/usr/bin/env python3
"""
ICUGuardian — Production Cloud Backend & Real-Time WebSocket Server (`aws-cloud/cloud_backend_server.py`)
Implements the AWS IoT Rules -> Lambda (`process_vitals`, `process_alerts`, `device_status`)
-> DynamoDB/SQLite Storage -> API Gateway REST + WebSocket pipeline.
Features:
  - PBKDF2-HMAC-SHA256 password hashing & HMAC-SHA256 signed JWT session tokens
  - Full Patient Admission, Clinical Profile Editing, Care Notes & Medication Administration Record (MAR)
  - Real-time Vital Ingestion, Configurable Threshold Alert Engine, Cooldown Deduplication & Recovery Detection
  - Live Raspberry Pi Gateway Telemetry, Hardware Bus Diagnostics, Queue Flushing & Device Registration
  - Immutable HIPAA-style Security Audit Log (`audit_logs`)
"""

import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import random
import sqlite3
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from queue import Queue, Empty
from typing import Dict, Any, List, Optional, Set
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "lambda" / "process_alerts"))
from lambda_function import evaluate_vital_thresholds, DEFAULT_THRESHOLDS
from aws_sigv4 import dynamodb_put_item

DB_FILE = Path(__file__).parent / "icu_cloud_state.db"
GATEWAY_CONTROL_URL = os.environ.get("GATEWAY_CONTROL_URL", "http://127.0.0.1:5050")
SIMULATOR_CONTROL_URL = os.environ.get("SIMULATOR_CONTROL_URL", "http://127.0.0.1:3001")
JWT_SECRET = os.environ.get("ICU_JWT_SECRET", "icu-monitor-pro-clinical-hmac-secret-key-2026")
PASSWORD_SALT = b"icu-monitor-pro-pbkdf2-salt-v1"


class DynamoDBMirrorWorker:
    """
    Zero-dependency asynchronous background writer that mirrors real-time vitals,
    alerts, patients, and Raspberry Pi gateway status to Amazon DynamoDB via AWS SigV4
    when AWS_DYNAMODB_ENABLED=true.
    """
    def __init__(self) -> None:
        self.enabled = os.environ.get("AWS_DYNAMODB_ENABLED", "").lower() == "true"
        self.region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "ap-south-1"
        self.queue: Queue = Queue(maxsize=5000)
        if self.enabled and os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            t = threading.Thread(target=self._run_loop, daemon=True)
            t.start()
            print(f"[AWS DynamoDB] Live cloud mirroring ENABLED in region {self.region} (Zero-Dependency AWS SigV4)")
        else:
            self.enabled = False

    def enqueue_telemetry(
        self,
        message_id: str,
        patient_id: str,
        patient_name: str,
        bed_number: str,
        device_id: str,
        timestamp: str,
        status: str,
        vitals: Dict[str, Any],
        new_alerts: List[Dict[str, Any]],
    ) -> None:
        if not self.enabled:
            return
        try:
            self.queue.put_nowait(
                {
                    "messageId": message_id,
                    "patientId": patient_id,
                    "patientName": patient_name,
                    "bedNumber": bed_number,
                    "deviceId": device_id,
                    "timestamp": timestamp,
                    "status": status,
                    "vitals": vitals,
                    "newAlerts": new_alerts,
                    "isoNow": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception:
            pass

    def _run_loop(self) -> None:
        while True:
            try:
                item = self.queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                bp = item["vitals"].get("bloodPressure", {})
                sbp = round(float(bp.get("systolic", 120)), 1)
                dbp = round(float(bp.get("diastolic", 80)), 1)
                map_val = round(dbp + (sbp - dbp) / 3.0, 1)
                hr = round(float(item["vitals"].get("heartRate", 75)), 1)
                spo2 = round(float(item["vitals"].get("spo2", 98)), 1)
                temp = round(float(item["vitals"].get("temperature", 36.8)), 1)
                rr = round(float(item["vitals"].get("respiratoryRate", 16)), 1)
                ttl_val = int(time.time()) + (90 * 86400)

                dynamodb_put_item(
                    "ICU_VitalReadings",
                    {
                        "patientId": item["patientId"],
                        "timestamp": item["timestamp"],
                        "messageId": item["messageId"],
                        "deviceId": item["deviceId"],
                        "heartRate": hr,
                        "spo2": spo2,
                        "systolicBP": sbp,
                        "diastolicBP": dbp,
                        "meanArterialPressure": map_val,
                        "temperature": temp,
                        "respiratoryRate": rr,
                        "status": item["status"],
                        "ttl": ttl_val,
                    },
                    self.region,
                )
                dynamodb_put_item(
                    "ICU_Patients",
                    {
                        "patientId": item["patientId"],
                        "name": item["patientName"],
                        "bedNumber": item["bedNumber"],
                        "assignedDeviceId": item["deviceId"],
                        "status": item["status"],
                        "heartRate": hr,
                        "spo2": spo2,
                        "systolicBP": sbp,
                        "diastolicBP": dbp,
                        "temperature": temp,
                        "respiratoryRate": rr,
                        "updatedAt": item["timestamp"],
                    },
                    self.region,
                )
                for alert in item["newAlerts"]:
                    dynamodb_put_item(
                        "ICU_Alerts",
                        {
                            "patientId": item["patientId"],
                            "createdAt": alert.get("createdAt") or item["isoNow"],
                            "alertId": alert["alertId"],
                            "patientName": item["patientName"],
                            "bedNumber": item["bedNumber"],
                            "deviceId": item["deviceId"],
                            "parameter": alert["parameter"],
                            "severity": alert["severity"],
                            "detectedValue": str(alert["detectedValue"]),
                            "threshold": str(alert["threshold"]),
                            "description": alert["description"],
                            "acknowledgedStatus": "UNACKNOWLEDGED",
                        },
                        self.region,
                    )
            except Exception:
                pass


DDB_MIRROR = DynamoDBMirrorWorker()


def hash_password(plain: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), PASSWORD_SALT, 100_000)
    return base64.b64encode(dk).decode("ascii")


def verify_password(plain: str, stored_hash: str) -> bool:
    computed = hash_password(plain)
    return hmac.compare_digest(computed, stored_hash)


def issue_jwt(payload: Dict[str, Any], expires_in_sec: int = 43200) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = {
        **payload,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_sec,
    }
    b64_h = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=").decode("ascii")
    b64_b = base64.urlsafe_b64encode(json.dumps(body).encode("utf-8")).rstrip(b"=").decode("ascii")
    signing_input = f"{b64_h}.{b64_b}".encode("ascii")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    b64_s = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{b64_h}.{b64_b}.{b64_s}"


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(parts[2], expected_b64):
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


class CloudDatabaseManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.seen_message_ids: Set[str] = set()
        self.alert_cooldown_tracker: Dict[str, float] = {}
        self._init_schema()
        self._seed_initial_data()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self.lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS patients (
                        patientId TEXT PRIMARY KEY,
                        mrn TEXT NOT NULL,
                        patientName TEXT NOT NULL,
                        age INTEGER NOT NULL,
                        gender TEXT NOT NULL,
                        bedNumber TEXT NOT NULL,
                        monitoringDeviceId TEXT NOT NULL,
                        monitoringStatus TEXT NOT NULL,
                        condition TEXT,
                        attendingPhysician TEXT,
                        primaryNurse TEXT,
                        allergies TEXT,
                        currentMedications TEXT,
                        careNotes TEXT,
                        alertsEnabled INTEGER DEFAULT 1,
                        admittedAt TEXT,
                        latestVitals TEXT,
                        updatedAt TEXT,
                        createdAt TEXT
                    );

                    CREATE TABLE IF NOT EXISTS vital_readings (
                        messageId TEXT PRIMARY KEY,
                        patientId TEXT NOT NULL,
                        deviceId TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        operatingMode TEXT NOT NULL,
                        signalProfile TEXT,
                        bufferedOffline INTEGER DEFAULT 0,
                        heartRate REAL NOT NULL,
                        spo2 REAL NOT NULL,
                        temperature REAL NOT NULL,
                        respiratoryRate REAL NOT NULL,
                        systolic REAL NOT NULL,
                        diastolic REAL NOT NULL,
                        ecg TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_readings_patient_time
                    ON vital_readings(patientId, timestamp);

                    CREATE TABLE IF NOT EXISTS alerts (
                        alertId TEXT PRIMARY KEY,
                        patientId TEXT NOT NULL,
                        patientName TEXT NOT NULL,
                        bedNumber TEXT NOT NULL,
                        deviceId TEXT,
                        parameter TEXT NOT NULL,
                        category TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        detectedValue TEXT NOT NULL,
                        threshold TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        description TEXT NOT NULL,
                        createdAt TEXT NOT NULL,
                        acknowledged INTEGER DEFAULT 0,
                        acknowledgedBy TEXT,
                        acknowledgedAt TEXT,
                        resolved INTEGER DEFAULT 0,
                        resolvedBy TEXT,
                        resolvedAt TEXT,
                        recoveredAt TEXT
                    );

                    CREATE TABLE IF NOT EXISTS devices (
                        deviceId TEXT PRIMARY KEY,
                        deviceName TEXT NOT NULL,
                        deviceType TEXT NOT NULL,
                        location TEXT NOT NULL,
                        ipAddress TEXT NOT NULL,
                        macAddress TEXT,
                        deviceStatus TEXT NOT NULL,
                        uptime TEXT NOT NULL,
                        lastSeen TEXT NOT NULL,
                        firmwareVersion TEXT NOT NULL,
                        operatingMode TEXT NOT NULL,
                        assignedPatientId TEXT NOT NULL,
                        bedNumber TEXT NOT NULL,
                        offlineQueueSize INTEGER DEFAULT 0,
                        cpuTempC REAL DEFAULT 43.2,
                        cpuUsagePct REAL DEFAULT 14.0,
                        memoryUsagePct REAL DEFAULT 34.0,
                        latencyMs REAL DEFAULT 4.5,
                        createdAt TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS thresholds (
                        configurationId TEXT PRIMARY KEY,
                        configJson TEXT NOT NULL,
                        updatedAt TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS users (
                        userId TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        passwordHash TEXT NOT NULL,
                        fullName TEXT NOT NULL,
                        initials TEXT NOT NULL,
                        role TEXT NOT NULL,
                        department TEXT NOT NULL,
                        email TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        active INTEGER DEFAULT 1,
                        lastLogin TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS tickets (
                        ticketId TEXT PRIMARY KEY,
                        subject TEXT NOT NULL,
                        description TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        category TEXT NOT NULL,
                        status TEXT NOT NULL,
                        createdBy TEXT NOT NULL,
                        createdAt TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS reports (
                        reportId TEXT PRIMARY KEY,
                        patientId TEXT NOT NULL,
                        patientName TEXT NOT NULL,
                        reportType TEXT NOT NULL,
                        dateRange TEXT NOT NULL,
                        sections TEXT NOT NULL,
                        generatedBy TEXT NOT NULL,
                        createdAt TEXT NOT NULL,
                        summaryJson TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS audit_logs (
                        auditId TEXT PRIMARY KEY,
                        actor TEXT NOT NULL,
                        role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        targetId TEXT,
                        details TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def record_audit(self, actor: str, role: str, action: str, target_id: str, details: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        audit_id = f"AUD-{int(time.time() * 1000) % 1000000:06d}-{uuid.uuid4().hex[:4].upper()}"
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO audit_logs (auditId, actor, role, action, targetId, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (audit_id, actor, role, action, target_id, details, now_iso),
                )
                conn.commit()
            finally:
                conn.close()

    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def _seed_initial_data(self) -> None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.lock:
            conn = self._connect()
            try:
                # 1. Seed Thresholds
                if conn.execute("SELECT COUNT(*) FROM thresholds").fetchone()[0] == 0:
                    conn.execute(
                        "INSERT INTO thresholds (configurationId, configJson, updatedAt) VALUES (?, ?, ?)",
                        ("DEFAULT_DEMO_THRESHOLDS", json.dumps(DEFAULT_THRESHOLDS), now_iso),
                    )

                # 2. Seed Hospital Staff Users (with PBKDF2-SHA256 Password Hashes)
                if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
                    seed_users = [
                        (
                            "USR-001",
                            "sarah.smith",
                            hash_password("doctor123"),
                            "Dr. Sarah Smith",
                            "DSS",
                            "Doctor",
                            "Cardiology ICU",
                            "sarah.smith@hospital.com",
                            "+1 (555) 123-4567",
                            1,
                            now_iso,
                        ),
                        (
                            "USR-002",
                            "michael.jones",
                            hash_password("nurse123"),
                            "Nurse Michael Jones",
                            "NMJ",
                            "Nurse",
                            "Critical Care Unit",
                            "michael.jones@hospital.com",
                            "+1 (555) 234-5678",
                            1,
                            now_iso,
                        ),
                        (
                            "USR-003",
                            "lisa.wilson",
                            hash_password("admin123"),
                            "Admin Lisa Wilson",
                            "ALW",
                            "Admin",
                            "Clinical Engineering & IT",
                            "lisa.wilson@hospital.com",
                            "+1 (555) 345-6789",
                            1,
                            now_iso,
                        ),
                        (
                            "USR-004",
                            "james.wilson",
                            hash_password("doctor123"),
                            "Dr. James Wilson",
                            "DJW",
                            "Doctor",
                            "Pulmonary Critical Care",
                            "james.wilson@hospital.com",
                            "+1 (555) 456-7890",
                            1,
                            (now - timedelta(hours=6)).isoformat(),
                        ),
                    ]
                    conn.executemany(
                        """
                        INSERT INTO users
                        (userId, username, passwordHash, fullName, initials, role, department, email, phone, active, lastLogin)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        seed_users,
                    )

                # 3. Seed 6 Active ICU Patients
                if conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0:
                    seed_patients = [
                        {
                            "patientId": "PATIENT-001",
                            "mrn": "MRN-482910",
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
                            "currentMedications": ["Morphine 2mg/hr IV", "Propofol 50mcg/kg/min"],
                            "careNotes": [
                                {
                                    "noteId": "NOTE-101",
                                    "author": "Dr. Sarah Smith",
                                    "role": "Doctor",
                                    "note": "Patient extubated smoothly; maintaining SpO2 >96% on 2L nasal cannula. Continue Lead II telemetry.",
                                    "createdAt": (now - timedelta(hours=2)).isoformat(),
                                }
                            ],
                            "admittedAt": "2026-11-14T08:30:00Z",
                            "vitals": {
                                "heartRate": 73,
                                "spo2": 97,
                                "temperature": 36.6,
                                "respiratoryRate": 17,
                                "bloodPressure": {"systolic": 120, "diastolic": 80},
                                "ecg": [0.02, 0.08, 0.14, -0.1, 0.96, -0.22, 0.04, 0.2, 0.01],
                            },
                        },
                        {
                            "patientId": "PATIENT-002",
                            "mrn": "MRN-482911",
                            "patientName": "Michael Chen",
                            "age": 62,
                            "gender": "M",
                            "bedNumber": "ICU-02",
                            "monitoringDeviceId": "ICU-PI-002",
                            "monitoringStatus": "WARNING",
                            "condition": "Acute coronary syndrome observation",
                            "attendingPhysician": "Dr. Sarah Smith",
                            "primaryNurse": "Nurse Michael Jones",
                            "allergies": ["Sulfa Drugs"],
                            "currentMedications": ["Heparin 1000u/hr IV", "Metoprolol 25mg PO"],
                            "careNotes": [
                                {
                                    "noteId": "NOTE-102",
                                    "author": "Nurse Michael Jones",
                                    "role": "Nurse",
                                    "note": "Borderline sinus tachycardia noted during shift rounds; serial troponins pending.",
                                    "createdAt": (now - timedelta(hours=1)).isoformat(),
                                }
                            ],
                            "admittedAt": "2026-11-15T11:15:00Z",
                            "vitals": {
                                "heartRate": 102,
                                "spo2": 93,
                                "temperature": 37.3,
                                "respiratoryRate": 22,
                                "bloodPressure": {"systolic": 145, "diastolic": 92},
                                "ecg": [0.03, 0.1, 0.15, -0.12, 1.02, -0.25, 0.06, 0.22, 0.02],
                            },
                        },
                        {
                            "patientId": "PATIENT-003",
                            "mrn": "MRN-482912",
                            "patientName": "Sarah Davis",
                            "age": 58,
                            "gender": "F",
                            "bedNumber": "ICU-03",
                            "monitoringDeviceId": "ICU-PI-003",
                            "monitoringStatus": "CRITICAL",
                            "condition": "Severe acute respiratory distress syndrome (ARDS)",
                            "attendingPhysician": "Dr. James Wilson",
                            "primaryNurse": "Nurse Michael Jones",
                            "allergies": ["Latex"],
                            "currentMedications": ["Norepinephrine 8mcg/min", "Fentanyl 50mcg/hr"],
                            "careNotes": [
                                {
                                    "noteId": "NOTE-103",
                                    "author": "Dr. James Wilson",
                                    "role": "Doctor",
                                    "note": "FiO2 titrated to 60% due to persistent hypoxemia. Arterial blood gas scheduled in 30m.",
                                    "createdAt": (now - timedelta(minutes=35)).isoformat(),
                                }
                            ],
                            "admittedAt": "2026-11-13T19:40:00Z",
                            "vitals": {
                                "heartRate": 119,
                                "spo2": 88,
                                "temperature": 38.9,
                                "respiratoryRate": 27,
                                "bloodPressure": {"systolic": 90, "diastolic": 60},
                                "ecg": [0.05, 0.12, -0.15, 1.15, -0.32, 0.08, 0.26, -0.02, 0.04],
                            },
                        },
                        {
                            "patientId": "PATIENT-004",
                            "mrn": "MRN-482913",
                            "patientName": "James Thompson",
                            "age": 71,
                            "gender": "M",
                            "bedNumber": "ICU-04",
                            "monitoringDeviceId": "ICU-PI-004",
                            "monitoringStatus": "WARNING",
                            "condition": "Post-cardiac catheterization recovery",
                            "attendingPhysician": "Dr. Sarah Smith",
                            "primaryNurse": "Nurse Michael Jones",
                            "allergies": ["None Known"],
                            "currentMedications": ["Aspirin 81mg", "Atorvastatin 40mg"],
                            "careNotes": [],
                            "admittedAt": "2026-11-15T14:20:00Z",
                            "vitals": {
                                "heartRate": 84,
                                "spo2": 95,
                                "temperature": 37.1,
                                "respiratoryRate": 19,
                                "bloodPressure": {"systolic": 136, "diastolic": 86},
                                "ecg": [0.01, 0.07, 0.12, -0.08, 0.92, -0.2, 0.03, 0.18, 0.01],
                            },
                        },
                        {
                            "patientId": "PATIENT-005",
                            "mrn": "MRN-482914",
                            "patientName": "Maria Rodriguez",
                            "age": 39,
                            "gender": "F",
                            "bedNumber": "ICU-05",
                            "monitoringDeviceId": "ICU-PI-005",
                            "monitoringStatus": "NORMAL",
                            "condition": "Sepsis stabilization & hemodynamic monitoring",
                            "attendingPhysician": "Dr. James Wilson",
                            "primaryNurse": "Nurse Michael Jones",
                            "allergies": ["Codeine"],
                            "currentMedications": ["Vancomycin 1g IV q12h", "Lactated Ringers 100mL/hr"],
                            "careNotes": [],
                            "admittedAt": "2026-11-16T06:00:00Z",
                            "vitals": {
                                "heartRate": 76,
                                "spo2": 98,
                                "temperature": 36.8,
                                "respiratoryRate": 16,
                                "bloodPressure": {"systolic": 118, "diastolic": 76},
                                "ecg": [0.02, 0.06, 0.13, -0.09, 0.94, -0.21, 0.03, 0.19, 0.0],
                            },
                        },
                        {
                            "patientId": "PATIENT-006",
                            "mrn": "MRN-482915",
                            "patientName": "Robert Kim",
                            "age": 54,
                            "gender": "M",
                            "bedNumber": "ICU-06",
                            "monitoringDeviceId": "ICU-PI-006",
                            "monitoringStatus": "NORMAL",
                            "condition": "Neurological post-craniotomy observation",
                            "attendingPhysician": "Dr. Sarah Smith",
                            "primaryNurse": "Nurse Michael Jones",
                            "allergies": ["None Known"],
                            "currentMedications": ["Levetiracetam 500mg IV", "Acetaminophen 650mg"],
                            "careNotes": [],
                            "admittedAt": "2026-11-16T09:45:00Z",
                            "vitals": {
                                "heartRate": 69,
                                "spo2": 99,
                                "temperature": 36.5,
                                "respiratoryRate": 15,
                                "bloodPressure": {"systolic": 122, "diastolic": 78},
                                "ecg": [0.01, 0.05, 0.12, -0.08, 0.91, -0.19, 0.02, 0.17, 0.0],
                            },
                        },
                    ]

                    for p in seed_patients:
                        conn.execute(
                            """
                            INSERT INTO patients
                            (patientId, mrn, patientName, age, gender, bedNumber, monitoringDeviceId,
                             monitoringStatus, condition, attendingPhysician, primaryNurse,
                             allergies, currentMedications, careNotes, alertsEnabled, admittedAt,
                             latestVitals, updatedAt, createdAt)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                            """,
                            (
                                p["patientId"],
                                p["mrn"],
                                p["patientName"],
                                p["age"],
                                p["gender"],
                                p["bedNumber"],
                                p["monitoringDeviceId"],
                                p["monitoringStatus"],
                                p["condition"],
                                p["attendingPhysician"],
                                p["primaryNurse"],
                                json.dumps(p["allergies"]),
                                json.dumps(p["currentMedications"]),
                                json.dumps(p["careNotes"]),
                                p["admittedAt"],
                                json.dumps(p["vitals"]),
                                now_iso,
                                now_iso,
                            ),
                        )

                        # Seed 24 hours of historical telemetry (48 intervals)
                        base_v = p["vitals"]
                        for idx in range(48):
                            ts = (now - timedelta(minutes=(48 - idx) * 30)).isoformat()
                            wave = math.sin(idx * 0.35)
                            hr_val = max(55, min(145, round(base_v["heartRate"] + wave * 6 + random.uniform(-2, 2))))
                            spo2_val = max(84, min(100, round(base_v["spo2"] + math.cos(idx * 0.25) * 1.5)))
                            temp_val = round(base_v["temperature"] + math.sin(idx * 0.2) * 0.3, 1)
                            rr_val = max(10, min(34, round(base_v["respiratoryRate"] + wave * 2)))
                            sys_val = round(base_v["bloodPressure"]["systolic"] + wave * 5)
                            dia_val = round(base_v["bloodPressure"]["diastolic"] + wave * 3)
                            conn.execute(
                                """
                                INSERT INTO vital_readings
                                (messageId, patientId, deviceId, timestamp, operatingMode, signalProfile,
                                 bufferedOffline, heartRate, spo2, temperature, respiratoryRate,
                                 systolic, diastolic, ecg)
                                VALUES (?, ?, ?, ?, 'BEDSIDE_MONITOR', 'CONTINUOUS_TELEMETRY', 0, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    f"HIST-{p['patientId']}-{idx:03d}",
                                    p["patientId"],
                                    p["monitoringDeviceId"],
                                    ts,
                                    hr_val,
                                    spo2_val,
                                    temp_val,
                                    rr_val,
                                    sys_val,
                                    dia_val,
                                    json.dumps(base_v["ecg"]),
                                ),
                            )

                # 4. Seed 7 Raspberry Pi Bedside Gateways
                if conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 0:
                    seed_devices = [
                        ("ICU-PI-001", "ICU-01 Monitor Hub", "raspberry-pi", "ICU Ward A", "192.168.1.101", "DC:A6:32:4F:11:01", "ONLINE", "10d 16h", "2.1.0-prod", "BEDSIDE_MONITOR", "PATIENT-001", "ICU-01", 43.8, 14.2, 33.5, 4.1),
                        ("ICU-PI-002", "ICU-02 Monitor Hub", "raspberry-pi", "ICU Ward A", "192.168.1.102", "DC:A6:32:4F:11:02", "ONLINE", "6d 5h", "2.1.0-prod", "BEDSIDE_MONITOR", "PATIENT-002", "ICU-02", 44.5, 16.8, 36.0, 5.3),
                        ("ICU-PI-003", "ICU-03 Monitor Hub", "raspberry-pi", "ICU Ward A", "192.168.1.103", "DC:A6:32:4F:11:03", "ONLINE", "14d 2h", "2.1.0-prod", "BEDSIDE_MONITOR", "PATIENT-003", "ICU-03", 46.1, 21.4, 38.2, 4.8),
                        ("ICU-PI-004", "ICU-04 Monitor Hub", "raspberry-pi", "ICU Ward B", "192.168.1.104", "DC:A6:32:4F:11:04", "OFFLINE", "0d 0h", "2.0.8-prod", "BEDSIDE_MONITOR", "PATIENT-004", "ICU-04", 0.0, 0.0, 0.0, -1.0),
                        ("ICU-PI-005", "ICU-05 Monitor Hub", "raspberry-pi", "ICU Ward B", "192.168.1.105", "DC:A6:32:4F:11:05", "ONLINE", "8d 19h", "2.1.0-prod", "BEDSIDE_MONITOR", "PATIENT-005", "ICU-05", 42.9, 12.1, 31.0, 4.4),
                        ("ICU-PI-006", "ICU-06 Monitor Hub", "raspberry-pi", "ICU Ward B", "192.168.1.106", "DC:A6:32:4F:11:06", "MAINTENANCE", "2d 4h", "2.0.9-prod", "HARDWARE", "PATIENT-006", "ICU-06", 41.2, 8.5, 29.4, 6.2),
                        ("ICU-PI-007", "Telemetry Failover Hub", "raspberry-pi", "Biomed Server Room", "192.168.1.110", "DC:A6:32:4F:11:07", "ERROR", "1d 1h", "2.1.0-prod", "HARDWARE", "PATIENT-003", "ICU-03", 58.4, 78.0, 64.0, 48.0),
                    ]
                    for d in seed_devices:
                        conn.execute(
                            """
                            INSERT INTO devices
                            (deviceId, deviceName, deviceType, location, ipAddress, macAddress, deviceStatus,
                             uptime, lastSeen, firmwareVersion, operatingMode, assignedPatientId,
                             bedNumber, offlineQueueSize, cpuTempC, cpuUsagePct, memoryUsagePct, latencyMs, createdAt)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                            """,
                            (
                                d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], now_iso,
                                d[8], d[9], d[10], d[11], d[12], d[13], d[14], d[15], now_iso
                            ),
                        )

                # 5. Seed Initial Clinical & Equipment Alerts
                if conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0:
                    seed_alerts = [
                        (
                            "ALT-1001",
                            "PATIENT-003",
                            "Sarah Davis",
                            "ICU-03",
                            "ICU-PI-003",
                            "spo2",
                            "vitals",
                            1,
                            "88",
                            "94-100%",
                            "CRITICAL",
                            "Oxygen saturation critically low (88%)",
                            (now - timedelta(minutes=2)).isoformat(),
                            0,
                            None,
                            None,
                            0,
                        ),
                        (
                            "ALT-1002",
                            "PATIENT-002",
                            "Michael Chen",
                            "ICU-02",
                            "ICU-PI-002",
                            "heartRate",
                            "vitals",
                            2,
                            "105",
                            "60-100 bpm",
                            "WARNING",
                            "Heart rate elevated (105 bpm)",
                            (now - timedelta(minutes=5)).isoformat(),
                            1,
                            "Nurse Michael Jones",
                            (now - timedelta(minutes=3)).isoformat(),
                            0,
                        ),
                        (
                            "ALT-1003",
                            "PATIENT-004",
                            "James Thompson",
                            "ICU-04",
                            "ICU-PI-004",
                            "deviceConnectivity",
                            "equipment",
                            2,
                            "OFFLINE",
                            "ONLINE",
                            "WARNING",
                            "Bedside gateway ICU-PI-004 heartbeat timeout — check LAN link",
                            (now - timedelta(minutes=18)).isoformat(),
                            0,
                            None,
                            None,
                            0,
                        ),
                        (
                            "ALT-1004",
                            "PATIENT-003",
                            "Sarah Davis",
                            "ICU-03",
                            "ICU-PI-003",
                            "temperature",
                            "vitals",
                            2,
                            "38.9",
                            "36.0-38.0 °C",
                            "WARNING",
                            "Core body temperature elevated (38.9°C)",
                            (now - timedelta(minutes=12)).isoformat(),
                            0,
                            None,
                            None,
                            0,
                        ),
                        (
                            "ALT-1005",
                            "PATIENT-002",
                            "Michael Chen",
                            "ICU-02",
                            "ICU-PI-002",
                            "spo2",
                            "vitals",
                            2,
                            "93",
                            "94-100%",
                            "WARNING",
                            "Oxygen saturation below threshold (93%)",
                            (now - timedelta(minutes=9)).isoformat(),
                            0,
                            None,
                            None,
                            0,
                        ),
                        (
                            "ALT-1006",
                            "PATIENT-003",
                            "Sarah Davis",
                            "ICU-03",
                            "ICU-PI-003",
                            "respiratoryRate",
                            "vitals",
                            2,
                            "27",
                            "12-20 /min",
                            "WARNING",
                            "Respiratory rate elevated — Tachypnea (27/min)",
                            (now - timedelta(minutes=7)).isoformat(),
                            1,
                            "Dr. Sarah Smith",
                            (now - timedelta(minutes=4)).isoformat(),
                            0,
                        ),
                    ]
                    conn.executemany(
                        """
                        INSERT INTO alerts
                        (alertId, patientId, patientName, bedNumber, deviceId, parameter,
                         category, priority, detectedValue, threshold, severity, description,
                         createdAt, acknowledged, acknowledgedBy, acknowledgedAt, resolved)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        seed_alerts,
                    )

                # 6. Seed Biomedical Support Tickets
                if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
                    seed_tickets = [
                        (
                            "T-001",
                            "Device connection issues in ICU-04",
                            "Raspberry Pi gateway ICU-PI-004 is not responding to MQTT keepalive pings on Ward B switch.",
                            "HIGH",
                            "technical",
                            "IN PROGRESS",
                            "Dr. Sarah Smith",
                            (now - timedelta(hours=3)).isoformat(),
                        ),
                        (
                            "T-002",
                            "MAX30102 SpO2 sensor calibration check for ICU-02",
                            "Requesting biomedical engineering optical probe verification during next shift change.",
                            "MEDIUM",
                            "hardware",
                            "OPEN",
                            "Nurse Michael Jones",
                            (now - timedelta(days=1)).isoformat(),
                        ),
                    ]
                    conn.executemany(
                        """
                        INSERT INTO tickets
                        (ticketId, subject, description, priority, category, status, createdBy, createdAt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        seed_tickets,
                    )

                # 7. Seed Initial Audit Log
                if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0:
                    conn.execute(
                        """
                        INSERT INTO audit_logs (auditId, actor, role, action, targetId, details, timestamp)
                        VALUES (?, 'System', 'System', 'SYSTEM_BOOT', 'AWS-IOT-CORE', 'ICUGuardian Cloud Backend & Alert Engine initialized', ?)
                        """,
                        (f"AUD-{int(time.time())}", now_iso),
                    )

                conn.commit()
            finally:
                conn.close()

    def get_thresholds(self) -> Dict[str, Any]:
        with self.lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT configJson, updatedAt FROM thresholds WHERE configurationId = 'DEFAULT_DEMO_THRESHOLDS'"
                ).fetchone()
                if not row:
                    return DEFAULT_THRESHOLDS
                cfg = json.loads(row["configJson"])
                cfg["updatedAt"] = row["updatedAt"]
                return cfg
            finally:
                conn.close()

    def update_thresholds(self, new_cfg: Dict[str, Any], actor: str = "Clinical Admin") -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        merged = dict(DEFAULT_THRESHOLDS)
        for k in ("heartRate", "spo2", "temperature", "respiratoryRate", "bloodPressure"):
            if k in new_cfg and isinstance(new_cfg[k], dict):
                merged[k] = {**merged[k], **new_cfg[k]}
        if "cooldownSeconds" in new_cfg:
            merged["cooldownSeconds"] = int(new_cfg["cooldownSeconds"])
        merged["updatedAt"] = now_iso

        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE thresholds SET configJson = ?, updatedAt = ? WHERE configurationId = 'DEFAULT_DEMO_THRESHOLDS'",
                    (json.dumps(merged), now_iso),
                )
                conn.commit()
            finally:
                conn.close()
        self.record_audit(actor, "Admin", "UPDATE_THRESHOLDS", "DEFAULT_DEMO_THRESHOLDS", "Updated clinical alarm threshold parameters")
        return merged

    def reset_thresholds(self) -> Dict[str, Any]:
        return self.update_thresholds(DEFAULT_THRESHOLDS, actor="System Default Reset")

    def ingest_vital_reading(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        msg_id = payload.get("messageId") or f"MSG-{uuid.uuid4().hex[:8].upper()}"
        if msg_id in self.seen_message_ids:
            return {"duplicate": True, "messageId": msg_id}
        self.seen_message_ids.add(msg_id)

        patient_id = payload["patientId"]
        device_id = payload.get("deviceId", "ICU-PI-001")
        timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
        mode = payload.get("mode", "BEDSIDE_MONITOR")
        profile = payload.get("signalProfile") or payload.get("scenario") or "CONTINUOUS_TELEMETRY"
        buffered = 1 if payload.get("bufferedOffline") else 0
        vitals = payload["vitals"]
        bp = vitals.get("bloodPressure") or {"systolic": 120, "diastolic": 80}

        thresholds = self.get_thresholds()
        overall_status, breaches = evaluate_vital_thresholds(vitals, thresholds)
        cooldown_sec = int(thresholds.get("cooldownSeconds", 30))

        new_alerts: List[Dict[str, Any]] = []
        recovered_alerts: List[Dict[str, Any]] = []
        now_epoch = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.lock:
            conn = self._connect()
            try:
                patient_row = conn.execute(
                    "SELECT * FROM patients WHERE patientId = ?", (patient_id,)
                ).fetchone()
                if not patient_row:
                    return {"error": f"Unknown patientId {patient_id}"}

                patient_name = patient_row["patientName"]
                bed_number = patient_row["bedNumber"]
                alerts_enabled = bool(patient_row["alertsEnabled"])

                conn.execute(
                    """
                    INSERT OR IGNORE INTO vital_readings
                    (messageId, patientId, deviceId, timestamp, operatingMode, signalProfile,
                     bufferedOffline, heartRate, spo2, temperature, respiratoryRate,
                     systolic, diastolic, ecg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg_id,
                        patient_id,
                        device_id,
                        timestamp,
                        mode,
                        profile,
                        buffered,
                        float(vitals["heartRate"]),
                        float(vitals["spo2"]),
                        float(vitals["temperature"]),
                        float(vitals["respiratoryRate"]),
                        float(bp["systolic"]),
                        float(bp["diastolic"]),
                        json.dumps(vitals.get("ecg", [])),
                    ),
                )

                conn.execute(
                    "UPDATE patients SET monitoringStatus = ?, latestVitals = ?, updatedAt = ? WHERE patientId = ?",
                    (overall_status, json.dumps(vitals), timestamp, patient_id),
                )

                conn.execute(
                    "UPDATE devices SET deviceStatus = 'ONLINE', lastSeen = ?, operatingMode = ? WHERE deviceId = ?",
                    (now_iso, mode, device_id),
                )

                breached_params = {b["parameter"] for b in breaches}

                if alerts_enabled:
                    for b in breaches:
                        param = b["parameter"]
                        cooldown_key = f"{patient_id}:{param}:{b['severity']}"
                        last_fired = self.alert_cooldown_tracker.get(cooldown_key, 0.0)

                        existing_active = conn.execute(
                            """
                            SELECT alertId FROM alerts
                            WHERE patientId = ? AND parameter = ? AND severity = ? AND resolved = 0
                            """,
                            (patient_id, param, b["severity"]),
                        ).fetchone()

                        if not existing_active and (now_epoch - last_fired >= cooldown_sec):
                            alert_id = f"ALT-{int(now_epoch * 1000) % 100000:05d}-{uuid.uuid4().hex[:4].upper()}"
                            alert_obj = {
                                "alertId": alert_id,
                                "patientId": patient_id,
                                "patientName": patient_name,
                                "bedNumber": bed_number,
                                "deviceId": device_id,
                                "parameter": param,
                                "category": b["category"],
                                "priority": b["priority"],
                                "detectedValue": str(b["detectedValue"]),
                                "threshold": b["threshold"],
                                "severity": b["severity"],
                                "description": b["description"],
                                "createdAt": now_iso,
                                "acknowledged": False,
                                "acknowledgedBy": None,
                                "acknowledgedAt": None,
                                "resolved": False,
                                "resolvedBy": None,
                                "resolvedAt": None,
                                "recoveredAt": None,
                            }
                            conn.execute(
                                """
                                INSERT INTO alerts
                                (alertId, patientId, patientName, bedNumber, deviceId, parameter,
                                 category, priority, detectedValue, threshold, severity, description,
                                 createdAt, acknowledged, resolved)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                                """,
                                (
                                    alert_id,
                                    patient_id,
                                    patient_name,
                                    bed_number,
                                    device_id,
                                    param,
                                    b["category"],
                                    b["priority"],
                                    str(b["detectedValue"]),
                                    b["threshold"],
                                    b["severity"],
                                    b["description"],
                                    now_iso,
                                ),
                            )
                            self.alert_cooldown_tracker[cooldown_key] = now_epoch
                            new_alerts.append(alert_obj)

                active_rows = conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE patientId = ? AND category = 'vitals' AND resolved = 0 AND recoveredAt IS NULL
                    """,
                    (patient_id,),
                ).fetchall()
                for arow in active_rows:
                    if arow["parameter"] not in breached_params:
                        conn.execute(
                            "UPDATE alerts SET recoveredAt = ? WHERE alertId = ?",
                            (now_iso, arow["alertId"]),
                        )
                        recovered_alerts.append(dict(arow) | {"recoveredAt": now_iso})

                conn.commit()
            finally:
                conn.close()

        DDB_MIRROR.enqueue_telemetry(
            message_id=msg_id,
            patient_id=patient_id,
            patient_name=patient_name,
            bed_number=bed_number,
            device_id=device_id,
            timestamp=timestamp,
            status=overall_status,
            vitals=vitals,
            new_alerts=new_alerts,
        )

        return {
            "duplicate": False,
            "messageId": msg_id,
            "patientId": patient_id,
            "deviceId": device_id,
            "timestamp": timestamp,
            "mode": mode,
            "signalProfile": profile,
            "bufferedOffline": bool(buffered),
            "monitoringStatus": overall_status,
            "vitals": vitals,
            "newAlerts": new_alerts,
            "recoveredAlerts": recovered_alerts,
        }

    def list_patients(self) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM patients WHERE monitoringStatus != 'DISCHARGED' ORDER BY bedNumber ASC"
                ).fetchall()
                devices = {
                    r["deviceId"]: dict(r)
                    for r in conn.execute("SELECT * FROM devices").fetchall()
                }
                alert_counts = {}
                for r in conn.execute(
                    "SELECT patientId, COUNT(*) as cnt FROM alerts WHERE resolved = 0 GROUP BY patientId"
                ).fetchall():
                    alert_counts[r["patientId"]] = r["cnt"]

                result = []
                for r in rows:
                    dev = devices.get(r["monitoringDeviceId"], {})
                    result.append(
                        {
                            "patientId": r["patientId"],
                            "mrn": r["mrn"],
                            "patientName": r["patientName"],
                            "age": r["age"],
                            "gender": r["gender"],
                            "bedNumber": r["bedNumber"],
                            "monitoringDeviceId": r["monitoringDeviceId"],
                            "monitoringStatus": r["monitoringStatus"],
                            "condition": r["condition"],
                            "attendingPhysician": r["attendingPhysician"],
                            "primaryNurse": r["primaryNurse"],
                            "allergies": json.loads(r["allergies"] or "[]"),
                            "currentMedications": json.loads(r["currentMedications"] or "[]"),
                            "careNotes": json.loads(r["careNotes"] or "[]"),
                            "alertsEnabled": bool(r["alertsEnabled"]),
                            "admittedAt": r["admittedAt"],
                            "vitals": json.loads(r["latestVitals"] or "{}"),
                            "activeAlertsCount": alert_counts.get(r["patientId"], 0),
                            "deviceStatus": dev.get("deviceStatus", "ONLINE"),
                            "deviceIp": dev.get("ipAddress", "192.168.1.101"),
                            "updatedAt": r["updatedAt"],
                        }
                    )
                return result
            finally:
                conn.close()

    def admit_patient(self, data: Dict[str, Any], actor: str = "Dr. Sarah Smith") -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                pid = data.get("patientId") or f"PATIENT-{cnt + 1:03d}"
                mrn = data.get("mrn") or f"MRN-{482910 + cnt + 1}"
                name = data.get("patientName", "New ICU Patient").strip()
                age = int(data.get("age", 50))
                gender = data.get("gender", "M")
                bed = data.get("bedNumber") or f"ICU-{cnt + 1:02d}"
                dev_id = data.get("monitoringDeviceId") or f"ICU-PI-{cnt + 1:03d}"
                cond = data.get("condition", "ICU hemodynamic observation")
                doc = data.get("attendingPhysician", "Dr. Sarah Smith")
                nurse = data.get("primaryNurse", "Nurse Michael Jones")
                allergies = data.get("allergies", [])
                if isinstance(allergies, str):
                    allergies = [x.strip() for x in allergies.split(",") if x.strip()]
                meds = data.get("currentMedications", [])
                if isinstance(meds, str):
                    meds = [x.strip() for x in meds.split(",") if x.strip()]

                initial_vitals = {
                    "heartRate": 75,
                    "spo2": 98,
                    "temperature": 36.7,
                    "respiratoryRate": 16,
                    "bloodPressure": {"systolic": 120, "diastolic": 80},
                    "ecg": [0.02, 0.08, 0.14, -0.1, 0.96, -0.22, 0.04, 0.2, 0.01],
                }

                conn.execute(
                    """
                    INSERT INTO patients
                    (patientId, mrn, patientName, age, gender, bedNumber, monitoringDeviceId,
                     monitoringStatus, condition, attendingPhysician, primaryNurse,
                     allergies, currentMedications, careNotes, alertsEnabled, admittedAt,
                     latestVitals, updatedAt, createdAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'NORMAL', ?, ?, ?, ?, ?, '[]', 1, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        mrn,
                        name,
                        age,
                        gender,
                        bed,
                        dev_id,
                        cond,
                        doc,
                        nurse,
                        json.dumps(allergies),
                        json.dumps(meds),
                        now_iso,
                        json.dumps(initial_vitals),
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        self.record_audit(actor, "Doctor", "ADMIT_PATIENT", pid, f"Admitted {name} to {bed}")
        return self.get_patient_detail(pid)

    def update_patient(self, patient_id: str, data: Dict[str, Any], actor: str = "Dr. Sarah Smith") -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM patients WHERE patientId = ?", (patient_id,)).fetchone()
                if not row:
                    return None
                cond = data.get("condition", row["condition"])
                doc = data.get("attendingPhysician", row["attendingPhysician"])
                nurse = data.get("primaryNurse", row["primaryNurse"])
                bed = data.get("bedNumber", row["bedNumber"])
                alerts_en = 1 if data.get("alertsEnabled", bool(row["alertsEnabled"])) else 0

                allergies = data.get("allergies")
                if allergies is None:
                    allergies_json = row["allergies"]
                elif isinstance(allergies, str):
                    allergies_json = json.dumps([x.strip() for x in allergies.split(",") if x.strip()])
                else:
                    allergies_json = json.dumps(allergies)

                meds = data.get("currentMedications")
                if meds is None:
                    meds_json = row["currentMedications"]
                elif isinstance(meds, str):
                    meds_json = json.dumps([x.strip() for x in meds.split(",") if x.strip()])
                else:
                    meds_json = json.dumps(meds)

                conn.execute(
                    """
                    UPDATE patients
                    SET condition = ?, attendingPhysician = ?, primaryNurse = ?, bedNumber = ?,
                        alertsEnabled = ?, allergies = ?, currentMedications = ?, updatedAt = ?
                    WHERE patientId = ?
                    """,
                    (cond, doc, nurse, bed, alerts_en, allergies_json, meds_json, now_iso, patient_id),
                )
                conn.commit()
            finally:
                conn.close()
        self.record_audit(actor, "Doctor", "UPDATE_PATIENT", patient_id, f"Updated clinical record for {patient_id}")
        return self.get_patient_detail(patient_id)

    def add_care_note(self, patient_id: str, author: str, role: str, note_text: str) -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT careNotes FROM patients WHERE patientId = ?", (patient_id,)).fetchone()
                if not row:
                    return None
                notes = json.loads(row["careNotes"] or "[]")
                new_note = {
                    "noteId": f"NOTE-{int(time.time() * 1000) % 100000:05d}",
                    "author": author,
                    "role": role,
                    "note": note_text.strip(),
                    "createdAt": now_iso,
                }
                notes.insert(0, new_note)
                conn.execute(
                    "UPDATE patients SET careNotes = ?, updatedAt = ? WHERE patientId = ?",
                    (json.dumps(notes), now_iso, patient_id),
                )
                conn.commit()
            finally:
                conn.close()
        self.record_audit(author, role, "ADD_CLINICAL_NOTE", patient_id, note_text[:80])
        return self.get_patient_detail(patient_id)

    def get_patient_detail(self, patient_id: str) -> Optional[Dict[str, Any]]:
        patients = self.list_patients()
        for p in patients:
            if p["patientId"] == patient_id:
                p["alerts"] = self.list_alerts(patient_id=patient_id)
                return p
        return None

    def get_patient_history(
        self,
        patient_id: str,
        hours: float = 1.0,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        limit: int = 120,
    ) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        cutoff = start_iso or (now - timedelta(hours=hours)).isoformat()
        upper = end_iso or (now + timedelta(minutes=5)).isoformat()

        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM vital_readings
                    WHERE patientId = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (patient_id, cutoff, upper, limit),
                ).fetchall()
                if len(rows) < 5:
                    rows = conn.execute(
                        """
                        SELECT * FROM vital_readings
                        WHERE patientId = ?
                        ORDER BY timestamp DESC LIMIT 35
                        """,
                        (patient_id,),
                    ).fetchall()

                history = []
                for r in reversed(rows):
                    history.append(
                        {
                            "messageId": r["messageId"],
                            "patientId": r["patientId"],
                            "deviceId": r["deviceId"],
                            "timestamp": r["timestamp"],
                            "mode": r["operatingMode"],
                            "bufferedOffline": bool(r["bufferedOffline"]),
                            "heartRate": r["heartRate"],
                            "spo2": r["spo2"],
                            "temperature": r["temperature"],
                            "respiratoryRate": r["respiratoryRate"],
                            "systolic": r["systolic"],
                            "diastolic": r["diastolic"],
                        }
                    )
                return history
            finally:
                conn.close()

    def list_alerts(
        self,
        patient_id: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                query = "SELECT * FROM alerts WHERE 1=1"
                params: list = []
                if patient_id:
                    query += " AND patientId = ?"
                    params.append(patient_id)
                if severity and severity.upper() != "ALL":
                    query += " AND severity = ?"
                    params.append(severity.upper())
                if category and category.lower() != "all":
                    query += " AND category = ?"
                    params.append(category.lower())
                if status:
                    st = status.lower()
                    if st == "active":
                        query += " AND resolved = 0"
                    elif st == "unacknowledged":
                        query += " AND acknowledged = 0 AND resolved = 0"
                    elif st == "acknowledged":
                        query += " AND acknowledged = 1 AND resolved = 0"
                    elif st == "resolved":
                        query += " AND resolved = 1"

                query += " ORDER BY resolved ASC, priority ASC, createdAt DESC"
                rows = conn.execute(query, params).fetchall()
                return [
                    {
                        "alertId": r["alertId"],
                        "patientId": r["patientId"],
                        "patientName": r["patientName"],
                        "bedNumber": r["bedNumber"],
                        "deviceId": r["deviceId"],
                        "parameter": r["parameter"],
                        "category": r["category"],
                        "priority": r["priority"],
                        "detectedValue": r["detectedValue"],
                        "threshold": r["threshold"],
                        "severity": r["severity"],
                        "description": r["description"],
                        "createdAt": r["createdAt"],
                        "acknowledged": bool(r["acknowledged"]),
                        "acknowledgedBy": r["acknowledgedBy"],
                        "acknowledgedAt": r["acknowledgedAt"],
                        "resolved": bool(r["resolved"]),
                        "resolvedBy": r["resolvedBy"],
                        "resolvedAt": r["resolvedAt"],
                        "recoveredAt": r["recoveredAt"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    def acknowledge_alert(self, alert_id: str, user_name: str = "Dr. Sarah Smith") -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE alerts SET acknowledged = 1, acknowledgedBy = ?, acknowledgedAt = ? WHERE alertId = ?",
                    (user_name, now_iso, alert_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM alerts WHERE alertId = ?", (alert_id,)).fetchone()
                if not row:
                    return None
                res = dict(row) | {"acknowledged": True, "resolved": bool(row["resolved"])}
            finally:
                conn.close()
        self.record_audit(user_name, "Clinician", "ACKNOWLEDGE_ALERT", alert_id, f"Acknowledged alert {alert_id}")
        return res

    def acknowledge_all_alerts(self, user_name: str = "Dr. Sarah Smith") -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE alerts SET acknowledged = 1, acknowledgedBy = ?, acknowledgedAt = ? WHERE acknowledged = 0 AND resolved = 0",
                    (user_name, now_iso),
                )
                conn.commit()
                cnt = cur.rowcount
            finally:
                conn.close()
        self.record_audit(user_name, "Clinician", "ACKNOWLEDGE_ALL_ALERTS", "ALL", f"Bulk acknowledged {cnt} alerts")
        return cnt

    def resolve_alert(self, alert_id: str, user_name: str = "Dr. Sarah Smith") -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE alerts
                    SET resolved = 1, resolvedBy = ?, resolvedAt = ?,
                        acknowledged = 1, acknowledgedBy = COALESCE(acknowledgedBy, ?),
                        acknowledgedAt = COALESCE(acknowledgedAt, ?)
                    WHERE alertId = ?
                    """,
                    (user_name, now_iso, user_name, now_iso, alert_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM alerts WHERE alertId = ?", (alert_id,)).fetchone()
                if not row:
                    return None
                res = dict(row) | {"acknowledged": True, "resolved": True}
            finally:
                conn.close()
        self.record_audit(user_name, "Clinician", "RESOLVE_ALERT", alert_id, f"Resolved alert {alert_id}")
        return res

    def list_devices(self) -> List[Dict[str, Any]]:
        # Merge live telemetry from local Raspberry Pi gateway if reachable
        live_gw = None
        try:
            with urllib.request.urlopen(f"{GATEWAY_CONTROL_URL}/gateway/status", timeout=0.6) as resp:
                if resp.status == 200:
                    live_gw = json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass

        with self.lock:
            conn = self._connect()
            try:
                if live_gw and live_gw.get("deviceId"):
                    conn.execute(
                        """
                        UPDATE devices
                        SET offlineQueueSize = ?, cpuTempC = ?, cpuUsagePct = ?,
                            memoryUsagePct = ?, latencyMs = ?, uptime = ?
                        WHERE deviceId = ?
                        """,
                        (
                            int(live_gw.get("offlineQueueSize", 0)),
                            float(live_gw.get("cpuTempC", 43.0)),
                            float(live_gw.get("cpuUsagePct", 14.0)),
                            float(live_gw.get("memoryUsagePct", 34.0)),
                            float(live_gw.get("latencyMs", 4.2)),
                            str(live_gw.get("uptime", "10d 16h")),
                            live_gw["deviceId"],
                        ),
                    )
                    conn.commit()
                rows = conn.execute("SELECT * FROM devices ORDER BY deviceId ASC").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def register_device(self, data: Dict[str, Any], actor: str = "Admin Lisa Wilson") -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
                dev_id = data.get("deviceId") or f"ICU-PI-{cnt + 1:03d}"
                name = data.get("deviceName") or f"ICU-{cnt + 1:02d} Monitor Hub"
                loc = data.get("location", "ICU Ward A")
                ip = data.get("ipAddress", f"192.168.1.{101 + cnt}")
                mac = data.get("macAddress", f"DC:A6:32:4F:11:{cnt + 1:02X}")
                mode = data.get("operatingMode", "BEDSIDE_MONITOR")
                pid = data.get("assignedPatientId", "PATIENT-001")
                bed = data.get("bedNumber", f"ICU-{cnt + 1:02d}")

                conn.execute(
                    """
                    INSERT OR REPLACE INTO devices
                    (deviceId, deviceName, deviceType, location, ipAddress, macAddress, deviceStatus,
                     uptime, lastSeen, firmwareVersion, operatingMode, assignedPatientId,
                     bedNumber, offlineQueueSize, cpuTempC, cpuUsagePct, memoryUsagePct, latencyMs, createdAt)
                    VALUES (?, ?, 'raspberry-pi', ?, ?, ?, 'ONLINE', '0d 1h', ?, '2.1.0-prod', ?, ?, ?, 0, 42.5, 11.2, 31.0, 4.0, ?)
                    """,
                    (dev_id, name, loc, ip, mac, now_iso, mode, pid, bed, now_iso),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM devices WHERE deviceId = ?", (dev_id,)).fetchone()
                res = dict(row)
            finally:
                conn.close()
        self.record_audit(actor, "Admin", "REGISTER_DEVICE", dev_id, f"Registered gateway {dev_id} ({ip})")
        return res

    def update_device_status(
        self, device_id: str, status: str, offline_queue_size: int = 0
    ) -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE devices SET deviceStatus = ?, lastSeen = ?, offlineQueueSize = ? WHERE deviceId = ?",
                    (status, now_iso, offline_queue_size, device_id),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM devices WHERE deviceId = ?", (device_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def authenticate_user(self, username: str, password: str, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        alias_map = {
            "doctor": "sarah.smith",
            "nurse": "michael.jones",
            "admin": "lisa.wilson",
        }
        lookup = alias_map.get(username.strip().lower(), username.strip().lower())

        with self.lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
                    (lookup, lookup),
                ).fetchone()
                if not row:
                    return None
                if not bool(row["active"]):
                    return None
                if not verify_password(password, row["passwordHash"]):
                    return None

                conn.execute("UPDATE users SET lastLogin = ? WHERE userId = ?", (now_iso, row["userId"]))
                conn.commit()
                token = issue_jwt(
                    {
                        "userId": row["userId"],
                        "username": row["username"],
                        "fullName": row["fullName"],
                        "role": row["role"],
                    }
                )
                user_dict = {
                    "userId": row["userId"],
                    "username": row["username"],
                    "fullName": row["fullName"],
                    "initials": row["initials"],
                    "role": row["role"],
                    "department": row["department"],
                    "email": row["email"],
                    "phone": row["phone"],
                    "active": bool(row["active"]),
                    "lastLogin": now_iso,
                    "token": token,
                }
            finally:
                conn.close()
        self.record_audit(user_dict["fullName"], user_dict["role"], "USER_LOGIN", user_dict["userId"], "Authenticated via PBKDF2-SHA256 & issued JWT")
        return user_dict

    def change_user_password(self, user_id: str, new_password: str) -> bool:
        with self.lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE users SET passwordHash = ? WHERE userId = ?",
                    (hash_password(new_password), user_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_users(self) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM users ORDER BY userId ASC").fetchall()
                return [
                    {
                        "userId": r["userId"],
                        "username": r["username"],
                        "fullName": r["fullName"],
                        "initials": r["initials"],
                        "role": r["role"],
                        "department": r["department"],
                        "email": r["email"],
                        "phone": r["phone"],
                        "active": bool(r["active"]),
                        "lastLogin": r["lastLogin"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    def add_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        full_name = data.get("fullName", "New Staff Member").strip()
        parts = [p[0].upper() for p in full_name.split() if p]
        initials = "".join(parts[:3]) or "USR"
        user_id = f"USR-{int(time.time() * 1000) % 10000:04d}"
        username = data.get("username") or full_name.lower().replace("dr. ", "").replace(" ", ".")
        password = data.get("password") or "hospital123"
        role = data.get("role", "Doctor")
        dept = data.get("department", "ICU")
        email = data.get("email", f"{username}@hospital.com")
        phone = data.get("phone", "+1 (555) 999-0000")

        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO users
                    (userId, username, passwordHash, fullName, initials, role, department, email, phone, active, lastLogin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (user_id, username, hash_password(password), full_name, initials, role, dept, email, phone, now_iso),
                )
                conn.commit()
            finally:
                conn.close()
        self.record_audit("Admin", "Admin", "CREATE_USER", user_id, f"Created staff account {full_name} ({role})")
        return {
            "userId": user_id,
            "username": username,
            "fullName": full_name,
            "initials": initials,
            "role": role,
            "department": dept,
            "email": email,
            "phone": phone,
            "active": True,
            "lastLogin": now_iso,
        }

    def toggle_user_status(self, user_id: str, active: bool) -> Optional[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                conn.execute("UPDATE users SET active = ? WHERE userId = ?", (1 if active else 0, user_id))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE userId = ?", (user_id,)).fetchone()
                return dict(row) | {"active": bool(row["active"])} if row else None
            finally:
                conn.close()

    def list_tickets(self) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM tickets ORDER BY createdAt DESC").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def create_ticket(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            conn = self._connect()
            try:
                cnt = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
                ticket_id = f"T-{cnt + 1:03d}"
                ticket = {
                    "ticketId": ticket_id,
                    "subject": data.get("subject", "Support Request"),
                    "description": data.get("description", ""),
                    "priority": data.get("priority", "MEDIUM").upper(),
                    "category": data.get("category", "technical").lower(),
                    "status": "OPEN",
                    "createdBy": data.get("createdBy", "Dr. Sarah Smith"),
                    "createdAt": now_iso,
                }
                conn.execute(
                    """
                    INSERT INTO tickets
                    (ticketId, subject, description, priority, category, status, createdBy, createdAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket["ticketId"],
                        ticket["subject"],
                        ticket["description"],
                        ticket["priority"],
                        ticket["category"],
                        ticket["status"],
                        ticket["createdBy"],
                        ticket["createdAt"],
                    ),
                )
                conn.commit()
                return ticket
            finally:
                conn.close()

    def update_ticket_status(self, ticket_id: str, status: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                conn.execute("UPDATE tickets SET status = ? WHERE ticketId = ?", (status, ticket_id))
                conn.commit()
                row = conn.execute("SELECT * FROM tickets WHERE ticketId = ?", (ticket_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def generate_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        pid = data.get("patientId", "PATIENT-001")
        patient = self.get_patient_detail(pid) or self.list_patients()[0]
        history = self.get_patient_history(pid, hours=24.0)
        alerts = self.list_alerts(patient_id=pid)

        hr_vals = [h["heartRate"] for h in history] or [75]
        spo2_vals = [h["spo2"] for h in history] or [98]
        temp_vals = [h["temperature"] for h in history] or [36.7]

        summary = {
            "mrn": patient.get("mrn", "MRN-482910"),
            "avgHeartRate": round(sum(hr_vals) / len(hr_vals), 1),
            "minSpo2": round(min(spo2_vals), 1),
            "maxTemp": round(max(temp_vals), 1),
            "totalReadings": len(history),
            "totalAlerts": len(alerts),
            "criticalAlerts": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
            "currentStatus": patient["monitoringStatus"],
            "attendingPhysician": patient["attendingPhysician"],
            "primaryNurse": patient["primaryNurse"],
            "condition": patient["condition"],
            "medications": patient["currentMedications"],
            "careNotes": patient.get("careNotes", []),
        }

        report_id = f"RPT-{int(time.time() * 1000) % 100000:05d}"
        report_obj = {
            "reportId": report_id,
            "patientId": patient["patientId"],
            "patientName": patient["patientName"],
            "bedNumber": patient["bedNumber"],
            "reportType": data.get("reportType", "Clinical Summary Report"),
            "dateRange": data.get("dateRange", "Nov 10, 2026 to Nov 17, 2026"),
            "sections": data.get(
                "sections",
                ["Vital Signs Data", "Alert History", "Care Notes", "Medication History", "Trend Charts"],
            ),
            "generatedBy": data.get("generatedBy", "Dr. Sarah Smith"),
            "createdAt": now_iso,
            "summary": summary,
        }

        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO reports
                    (reportId, patientId, patientName, reportType, dateRange, sections, generatedBy, createdAt, summaryJson)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        report_obj["patientId"],
                        report_obj["patientName"],
                        report_obj["reportType"],
                        report_obj["dateRange"],
                        json.dumps(report_obj["sections"]),
                        report_obj["generatedBy"],
                        now_iso,
                        json.dumps(summary),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return report_obj

    def list_reports(self) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM reports ORDER BY createdAt DESC LIMIT 20").fetchall()
                return [
                    {
                        "reportId": r["reportId"],
                        "patientId": r["patientId"],
                        "patientName": r["patientName"],
                        "reportType": r["reportType"],
                        "dateRange": r["dateRange"],
                        "sections": json.loads(r["sections"]),
                        "generatedBy": r["generatedBy"],
                        "createdAt": r["createdAt"],
                        "summary": json.loads(r["summaryJson"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()


DB = CloudDatabaseManager()
ACTIVE_WEBSOCKETS: Set[asyncio.Queue] = set()


async def broadcast_ws_event(event_type: str, data: Any) -> None:
    if not ACTIVE_WEBSOCKETS:
        return
    message = json.dumps({"event": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
    stale = []
    for q in list(ACTIVE_WEBSOCKETS):
        try:
            q.put_nowait(message)
        except Exception:
            stale.append(q)
    for q in stale:
        ACTIVE_WEBSOCKETS.discard(q)


async def read_json_body(receive) -> Dict[str, Any]:
    chunks = []
    while True:
        msg = await receive()
        if msg["type"] == "http.request":
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body", False):
                break
        elif msg["type"] == "http.disconnect":
            break
    raw = b"".join(chunks)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


async def send_json_response(send, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
                (b"access-control-allow-headers", b"Content-Type, Authorization"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "websocket":
        msg = await receive()
        if msg["type"] != "websocket.connect":
            return
        await send({"type": "websocket.accept"})

        queue: asyncio.Queue = asyncio.Queue()
        ACTIVE_WEBSOCKETS.add(queue)

        snapshot = json.dumps(
            {
                "event": "INITIAL_SNAPSHOT",
                "data": {
                    "patients": DB.list_patients(),
                    "alerts": DB.list_alerts(),
                    "devices": DB.list_devices(),
                    "thresholds": DB.get_thresholds(),
                },
            }
        )
        await send({"type": "websocket.send", "text": snapshot})

        async def receiver_task():
            while True:
                m = await receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m["type"] == "websocket.receive" and m.get("text") == "ping":
                    await queue.put(json.dumps({"event": "PONG"}))

        async def sender_task():
            while True:
                out_msg = await queue.get()
                await send({"type": "websocket.send", "text": out_msg})

        done, pending = await asyncio.wait(
            [asyncio.create_task(receiver_task()), asyncio.create_task(sender_task())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        ACTIVE_WEBSOCKETS.discard(queue)
        return

    if scope["type"] != "http":
        return

    method = scope["method"].upper()
    path = scope["path"]
    query_string = scope.get("query_string", b"").decode("utf-8")
    qs = parse_qs(query_string)

    if method == "OPTIONS":
        await send_json_response(send, 200, {"ok": True})
        return

    try:
        if path in ("/", "/index.html") and method == "GET":
            html_path = Path(__file__).resolve().parent.parent / "doctor-dashboard" / "public" / "index.html"
            if html_path.exists():
                body = html_path.read_bytes()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"text/html; charset=utf-8"),
                            (b"cache-control", b"no-cache"),
                            (b"content-length", str(len(body)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

        if path == "/manifest.json" and method == "GET":
            manifest_path = Path(__file__).resolve().parent.parent / "doctor-dashboard" / "public" / "manifest.json"
            if manifest_path.exists():
                body = manifest_path.read_bytes()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"application/manifest+json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

        if path in ("/health", "/api/health"):
            await send_json_response(
                send,
                200,
                {
                    "status": "ONLINE",
                    "service": "ICUGuardian Cloud Backend",
                    "connectedWebSockets": len(ACTIVE_WEBSOCKETS),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        # 1. Authentication & Security Endpoints
        if path == "/api/auth/login" and method == "POST":
            body = await read_json_body(receive)
            user = DB.authenticate_user(
                username=body.get("username", ""),
                password=body.get("password", ""),
                role=body.get("role"),
            )
            if not user:
                await send_json_response(send, 401, {"error": "Invalid username or password"})
                return
            await send_json_response(send, 200, user)
            return

        if path == "/api/auth/change-password" and method == "POST":
            body = await read_json_body(receive)
            ok = DB.change_user_password(body.get("userId", "USR-001"), body.get("newPassword", ""))
            await send_json_response(send, 200 if ok else 400, {"ok": ok})
            return

        if path == "/api/audit-logs" and method == "GET":
            await send_json_response(send, 200, {"auditLogs": DB.list_audit_logs()})
            return

        # 2. IoT Gateway Vital Telemetry Ingestion
        if path == "/api/iot/ingest-vitals" and method == "POST":
            envelope = await read_json_body(receive)
            payload = envelope.get("payload") if "payload" in envelope else envelope
            result = DB.ingest_vital_reading(payload)
            if "error" in result:
                await send_json_response(send, 400, result)
                return

            if not result.get("duplicate"):
                await broadcast_ws_event("VITAL_UPDATE", result)
                for alert in result.get("newAlerts", []):
                    await broadcast_ws_event("ALERT_NEW", alert)
                for rec in result.get("recoveredAlerts", []):
                    await broadcast_ws_event("PATIENT_RECOVERED", rec)

            await send_json_response(send, 200, result)
            return

        # 3. IoT Device Status Heartbeat / LWT
        if path == "/api/iot/device-status" and method == "POST":
            envelope = await read_json_body(receive)
            payload = envelope.get("payload") if "payload" in envelope else envelope
            dev_id = payload.get("deviceId", "ICU-PI-001")
            status = payload.get("deviceStatus", "ONLINE")
            q_size = int(payload.get("offlineQueueSize", 0))
            updated = DB.update_device_status(dev_id, status, q_size)
            await broadcast_ws_event("DEVICE_STATUS", updated or payload)
            await send_json_response(send, 200, {"ok": True, "device": updated})
            return

        # 4. Patients & Clinical Chart API
        if path == "/api/patients" and method == "GET":
            await send_json_response(send, 200, {"patients": DB.list_patients()})
            return

        if path == "/api/patients" and method == "POST":
            body = await read_json_body(receive)
            created = DB.admit_patient(body, actor=body.get("actor", "Dr. Sarah Smith"))
            await broadcast_ws_event("PATIENT_UPDATED", created)
            await send_json_response(send, 201, created)
            return

        if path.startswith("/api/patients/") and path.endswith("/history") and method == "GET":
            patient_id = path.strip("/").split("/")[2]
            hours = float(qs.get("hours", ["1"])[0])
            start_iso = qs.get("start", [None])[0]
            end_iso = qs.get("end", [None])[0]
            history = DB.get_patient_history(patient_id, hours=hours, start_iso=start_iso, end_iso=end_iso)
            await send_json_response(send, 200, {"patientId": patient_id, "readings": history})
            return

        if path.startswith("/api/patients/") and path.endswith("/notes") and method == "POST":
            patient_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            updated = DB.add_care_note(
                patient_id,
                author=body.get("author", "Dr. Sarah Smith"),
                role=body.get("role", "Doctor"),
                note_text=body.get("note", ""),
            )
            if not updated:
                await send_json_response(send, 404, {"error": "Patient not found"})
                return
            await broadcast_ws_event("PATIENT_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        if path.startswith("/api/patients/") and method == "PATCH":
            patient_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            updated = DB.update_patient(patient_id, body, actor=body.get("actor", "Dr. Sarah Smith"))
            if not updated:
                await send_json_response(send, 404, {"error": "Patient not found"})
                return
            await broadcast_ws_event("PATIENT_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        if path.startswith("/api/patients/") and method == "GET":
            patient_id = path.strip("/").split("/")[2]
            detail = DB.get_patient_detail(patient_id)
            if not detail:
                await send_json_response(send, 404, {"error": "Patient not found"})
                return
            await send_json_response(send, 200, detail)
            return

        # 5. Bedside Acquisition Signal Profile Control
        if path in ("/api/bedside/profile", "/api/demo/scenario") and method == "POST":
            body = await read_json_body(receive)
            req = urllib.request.Request(
                f"{SIMULATOR_CONTROL_URL}/api/simulator/scenario",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    sim_data = json.loads(resp.read().decode("utf-8"))
                await send_json_response(send, 200, sim_data)
            except Exception as exc:
                await send_json_response(send, 502, {"error": f"Bedside monitor unreachable: {exc}"})
            return

        # 6. Alerts API
        if path == "/api/alerts" and method == "GET":
            patient_id = qs.get("patientId", [None])[0]
            severity = qs.get("severity", [None])[0]
            category = qs.get("category", [None])[0]
            status = qs.get("status", [None])[0]
            alerts = DB.list_alerts(
                patient_id=patient_id, severity=severity, category=category, status=status
            )
            await send_json_response(send, 200, {"alerts": alerts})
            return

        if path == "/api/alerts/acknowledge-all" and method == "POST":
            body = await read_json_body(receive)
            user_name = body.get("userName", "Dr. Sarah Smith")
            count = DB.acknowledge_all_alerts(user_name=user_name)
            await broadcast_ws_event("ALERTS_BULK_ACKNOWLEDGED", {"count": count, "by": user_name})
            await send_json_response(send, 200, {"ok": True, "acknowledgedCount": count})
            return

        if path.startswith("/api/alerts/") and path.endswith("/acknowledge") and method == "POST":
            alert_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            user_name = body.get("userName", "Dr. Sarah Smith")
            updated = DB.acknowledge_alert(alert_id, user_name=user_name)
            if not updated:
                await send_json_response(send, 404, {"error": "Alert not found"})
                return
            await broadcast_ws_event("ALERT_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        if path.startswith("/api/alerts/") and path.endswith("/resolve") and method == "POST":
            alert_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            user_name = body.get("userName", "Dr. Sarah Smith")
            updated = DB.resolve_alert(alert_id, user_name=user_name)
            if not updated:
                await send_json_response(send, 404, {"error": "Alert not found"})
                return
            await broadcast_ws_event("ALERT_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        # 7. Devices & Edge Gateway Management API
        if path == "/api/devices" and method == "GET":
            await send_json_response(send, 200, {"devices": DB.list_devices()})
            return

        if path == "/api/devices" and method == "POST":
            body = await read_json_body(receive)
            dev = DB.register_device(body, actor=body.get("actor", "Admin Lisa Wilson"))
            await broadcast_ws_event("DEVICE_STATUS", dev)
            await send_json_response(send, 201, dev)
            return

        if path.startswith("/api/devices/") and path.endswith("/diagnostics") and method in ("GET", "POST"):
            device_id = path.strip("/").split("/")[2]
            try:
                with urllib.request.urlopen(f"{GATEWAY_CONTROL_URL}/gateway/diagnostics", timeout=2.0) as resp:
                    diag = json.loads(resp.read().decode("utf-8"))
                diag["requestedDeviceId"] = device_id
                await send_json_response(send, 200, diag)
            except Exception as exc:
                await send_json_response(send, 502, {"error": f"Gateway diagnostics unreachable: {exc}"})
            return

        if path.startswith("/api/devices/") and path.endswith("/flush-queue") and method == "POST":
            device_id = path.strip("/").split("/")[2]
            try:
                req = urllib.request.Request(
                    f"{GATEWAY_CONTROL_URL}/gateway/flush-queue",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                await send_json_response(send, 200, res_data)
            except Exception as exc:
                await send_json_response(send, 502, {"error": str(exc)})
            return

        if (
            path.startswith("/api/devices/")
            and (path.endswith("/maintenance") or path.endswith("/simulate-disconnect"))
            and method == "POST"
        ):
            device_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            offline = bool(body.get("offline", True))
            req = urllib.request.Request(
                f"{GATEWAY_CONTROL_URL}/gateway/maintenance",
                data=json.dumps({"deviceId": device_id, "offline": offline}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            gw_resp = {}
            try:
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    gw_resp = json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass
            updated = DB.update_device_status(
                device_id,
                "OFFLINE" if offline else "ONLINE",
                int(gw_resp.get("offlineQueueSize", 0)),
            )
            await broadcast_ws_event("DEVICE_STATUS", updated)
            await send_json_response(
                send, 200, {"ok": True, "device": updated, "gatewayResponse": gw_resp}
            )
            return

        # 8. Threshold Settings API
        if path == "/api/settings/thresholds" and method == "GET":
            await send_json_response(send, 200, DB.get_thresholds())
            return

        if path == "/api/settings/thresholds" and method in ("PUT", "POST"):
            body = await read_json_body(receive)
            updated = DB.update_thresholds(body, actor=body.get("actor", "Clinical Admin"))
            await broadcast_ws_event("THRESHOLDS_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        if path == "/api/settings/thresholds/reset" and method == "POST":
            updated = DB.reset_thresholds()
            await broadcast_ws_event("THRESHOLDS_UPDATED", updated)
            await send_json_response(send, 200, updated)
            return

        # 9. Users API
        if path == "/api/users" and method == "GET":
            await send_json_response(send, 200, {"users": DB.list_users()})
            return

        if path == "/api/users" and method == "POST":
            body = await read_json_body(receive)
            created = DB.add_user(body)
            await send_json_response(send, 201, created)
            return

        if path.startswith("/api/users/") and method == "PATCH":
            user_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            updated = DB.toggle_user_status(user_id, bool(body.get("active", True)))
            await send_json_response(send, 200 if updated else 404, updated or {"error": "Not found"})
            return

        # 10. Support Tickets & Clinical Reports API
        if path == "/api/tickets" and method == "GET":
            await send_json_response(send, 200, {"tickets": DB.list_tickets()})
            return

        if path == "/api/tickets" and method == "POST":
            body = await read_json_body(receive)
            ticket = DB.create_ticket(body)
            await send_json_response(send, 201, ticket)
            return

        if path.startswith("/api/tickets/") and method == "PATCH":
            ticket_id = path.strip("/").split("/")[2]
            body = await read_json_body(receive)
            updated = DB.update_ticket_status(ticket_id, body.get("status", "RESOLVED"))
            await send_json_response(send, 200 if updated else 404, updated or {"error": "Not found"})
            return

        if path == "/api/reports" and method == "GET":
            await send_json_response(send, 200, {"reports": DB.list_reports()})
            return

        if path == "/api/reports" and method == "POST":
            body = await read_json_body(receive)
            report = DB.generate_report(body)
            await send_json_response(send, 201, report)
            return

        await send_json_response(send, 404, {"error": f"Route {method} {path} not found"})
    except Exception as exc:
        await send_json_response(send, 500, {"error": str(exc)})


if __name__ == "__main__":
    import uvicorn  # type: ignore

    port = int(os.environ.get("CLOUD_PORT", "8000"))
    print(f"[ICUGuardian Cloud Backend] Starting on http://0.0.0.0:{port} (WebSocket: ws://0.0.0.0:{port}/ws)")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
