#!/usr/bin/env python3
"""
Bedside ICU Patient Vital Sign Simulator Engine
Generates realistic synthetic vital signs and PQRST ECG waveforms for 7 demonstration scenarios.
IMPORTANT: Clearly labeled SIMULATION data for academic demonstration only.
"""

import math
import random
import time
import uuid
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "NORMAL": {
        "label": "Normal Patient",
        "description": "Normal sinus rhythm and stable physiological parameters",
        "hr_range": (68, 78),
        "spo2_range": (96, 99),
        "temp_range": (36.5, 37.0),
        "rr_range": (14, 18),
        "sys_range": (115, 126),
        "dia_range": (74, 82),
        "ecg_noise": 0.02,
    },
    "HIGH_HR": {
        "label": "High Heart Rate (Tachycardia)",
        "description": "Elevated heart rate exceeding upper threshold (>100 BPM / Critical >120 BPM)",
        "hr_range": (124, 138),
        "spo2_range": (95, 97),
        "temp_range": (37.1, 37.5),
        "rr_range": (19, 22),
        "sys_range": (138, 148),
        "dia_range": (88, 94),
        "ecg_noise": 0.04,
    },
    "LOW_SPO2": {
        "label": "Low SpO2 (Hypoxemia)",
        "description": "Critically low blood oxygen saturation (<90%)",
        "hr_range": (104, 115),
        "spo2_range": (85, 89),
        "temp_range": (36.8, 37.2),
        "rr_range": (23, 27),
        "sys_range": (105, 116),
        "dia_range": (68, 76),
        "ecg_noise": 0.03,
    },
    "HIGH_TEMP": {
        "label": "High Temperature (Hyperpyrexia)",
        "description": "Elevated core body temperature above 38.0°C / 39.0°C",
        "hr_range": (96, 108),
        "spo2_range": (95, 97),
        "temp_range": (38.8, 39.5),
        "rr_range": (20, 23),
        "sys_range": (124, 134),
        "dia_range": (78, 86),
        "ecg_noise": 0.03,
    },
    "ABNORMAL_RR": {
        "label": "Abnormal Respiratory Rate",
        "description": "Tachypnea with respiratory rate exceeding 28 breaths/min",
        "hr_range": (94, 106),
        "spo2_range": (92, 94),
        "temp_range": (37.0, 37.4),
        "rr_range": (28, 33),
        "sys_range": (128, 138),
        "dia_range": (82, 88),
        "ecg_noise": 0.03,
    },
    "CRITICAL": {
        "label": "Critical Patient Condition",
        "description": "Multi-parameter critical instability requiring immediate intervention",
        "hr_range": (132, 148),
        "spo2_range": (83, 88),
        "temp_range": (39.1, 39.8),
        "rr_range": (29, 35),
        "sys_range": (84, 92),
        "dia_range": (50, 58),
        "ecg_noise": 0.06,
    },
    "RECOVERY": {
        "label": "Patient Recovery",
        "description": "Parameters stabilizing back into normal demonstration ranges",
        "hr_range": (72, 80),
        "spo2_range": (97, 99),
        "temp_range": (36.6, 36.9),
        "rr_range": (15, 18),
        "sys_range": (118, 124),
        "dia_range": (76, 82),
        "ecg_noise": 0.015,
    },
}


def generate_ecg_waveform(heart_rate: float, num_samples: int = 50, noise_level: float = 0.02, phase_offset: float = 0.0) -> List[float]:
    """
    Synthesizes a realistic P-Q-R-S-T ECG waveform array for demonstration display.
    Uses Gaussian wavelets for P, Q, R, S, and T waves scaled by heart_rate.
    """
    samples: List[float] = []
    beats_per_sec = max(heart_rate, 30.0) / 60.0
    for i in range(num_samples):
        t = (i / float(num_samples)) + phase_offset
        # Cycle position in [0, 1)
        cycle = (t * beats_per_sec * 2.0) % 1.0

        # P wave (atrial depolarization)
        p_wave = 0.15 * math.exp(-((cycle - 0.18) ** 2) / (2 * (0.035 ** 2)))
        # Q wave
        q_wave = -0.15 * math.exp(-((cycle - 0.35) ** 2) / (2 * (0.012 ** 2)))
        # R wave (ventricular depolarization spike)
        r_wave = 1.15 * math.exp(-((cycle - 0.38) ** 2) / (2 * (0.010 ** 2)))
        # S wave
        s_wave = -0.28 * math.exp(-((cycle - 0.41) ** 2) / (2 * (0.014 ** 2)))
        # T wave (ventricular repolarization)
        t_wave = 0.28 * math.exp(-((cycle - 0.65) ** 2) / (2 * (0.048 ** 2)))

        voltage = p_wave + q_wave + r_wave + s_wave + t_wave
        voltage += random.uniform(-noise_level, noise_level)
        samples.append(round(voltage, 4))
    return samples


class BedsidePatientSimulator:
    """
    Stateful simulator for an ICU patient monitor. Smoothly transitions between scenarios
    and emits structured JSON telemetry conforming to shared/data-schema/vitals.schema.json.
    """

    def __init__(
        self,
        patient_id: str = "PATIENT-001",
        device_id: str = "ICU-PI-001",
        patient_name: str = "Emily Johnson",
        bed_number: str = "ICU-01",
        scenario: str = "NORMAL",
    ):
        self.patient_id = patient_id
        self.device_id = device_id
        self.patient_name = patient_name
        self.bed_number = bed_number
        self.scenario = scenario if scenario in SCENARIOS else "NORMAL"
        self.sequence_number = 0
        self._phase = 0.0

        # Current smoothed state
        self.current_hr = 73.0
        self.current_spo2 = 98.0
        self.current_temp = 36.7
        self.current_rr = 16.0
        self.current_sys = 120.0
        self.current_dia = 78.0

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Valid: {list(SCENARIOS.keys())}")
        self.scenario = scenario

    def next_reading(self) -> Dict[str, Any]:
        """Generates the next telemetry frame with smooth physiological drift toward target scenario."""
        self.sequence_number += 1
        cfg = SCENARIOS[self.scenario]

        target_hr = random.uniform(*cfg["hr_range"])
        target_spo2 = random.uniform(*cfg["spo2_range"])
        target_temp = random.uniform(*cfg["temp_range"])
        target_rr = random.uniform(*cfg["rr_range"])
        target_sys = random.uniform(*cfg["sys_range"])
        target_dia = random.uniform(*cfg["dia_range"])

        # Smooth exponential moving average transition (alpha = 0.45 for responsive demos)
        alpha = 0.45
        self.current_hr = self.current_hr * (1 - alpha) + target_hr * alpha
        self.current_spo2 = self.current_spo2 * (1 - alpha) + target_spo2 * alpha
        self.current_temp = self.current_temp * (1 - alpha) + target_temp * alpha
        self.current_rr = self.current_rr * (1 - alpha) + target_rr * alpha
        self.current_sys = self.current_sys * (1 - alpha) + target_sys * alpha
        self.current_dia = self.current_dia * (1 - alpha) + target_dia * alpha

        self._phase = (self._phase + 0.17) % 1.0
        ecg_samples = generate_ecg_waveform(
            heart_rate=self.current_hr,
            num_samples=40,
            noise_level=cfg["ecg_noise"],
            phase_offset=self._phase,
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        message_id = f"MSG-{int(time.time() * 1000)}-{self.sequence_number:04d}-{uuid.uuid4().hex[:6].upper()}"

        return {
            "messageId": message_id,
            "deviceId": self.device_id,
            "patientId": self.patient_id,
            "timestamp": now_iso,
            "mode": "SIMULATION",
            "scenario": self.scenario,
            "bufferedOffline": False,
            "vitals": {
                "heartRate": int(round(self.current_hr)),
                "spo2": int(round(min(100.0, max(50.0, self.current_spo2)))),
                "temperature": round(self.current_temp, 1),
                "respiratoryRate": int(round(self.current_rr)),
                "bloodPressure": {
                    "systolic": int(round(self.current_sys)),
                    "diastolic": int(round(self.current_dia)),
                },
                "ecg": ecg_samples,
            },
        }

    def transmit_to_gateway(self, gateway_url: str, reading: Dict[str, Any], timeout: float = 2.5) -> Dict[str, Any]:
        """Sends the generated reading to the Raspberry Pi Gateway HTTP endpoint."""
        data = json.dumps(reading).encode("utf-8")
        req = urllib.request.Request(
            gateway_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    # Self-test across all 7 scenarios
    sim = BedsidePatientSimulator()
    print("=" * 65)
    print("PHASE 2: Testing Bedside ICU Patient Simulator across 7 Scenarios")
    print("=" * 65)
    for scen_key in SCENARIOS:
        sim.set_scenario(scen_key)
        # Step 4 times to converge EMA
        reading = {}
        for _ in range(4):
            reading = sim.next_reading()
        v = reading["vitals"]
        bp = v["bloodPressure"]
        print(
            f"  [{scen_key:11s}] HR={v['heartRate']:3d} BPM | SpO2={v['spo2']:2d}% | "
            f"Temp={v['temperature']:4.1f}°C | RR={v['respiratoryRate']:2d}/min | "
            f"BP={bp['systolic']}/{bp['diastolic']} | ECG pts={len(v['ecg'])}"
        )
    print("=" * 65)
    print("Bedside Simulator Self-Test Completed Successfully!")
