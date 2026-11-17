export type ScenarioKey =
  | 'NORMAL'
  | 'HIGH_HR'
  | 'LOW_SPO2'
  | 'HIGH_TEMP'
  | 'ABNORMAL_RR'
  | 'CRITICAL'
  | 'RECOVERY';

export interface BloodPressure {
  systolic: number;
  diastolic: number;
}

export interface VitalSigns {
  heartRate: number;
  spo2: number;
  temperature: number;
  respiratoryRate: number;
  bloodPressure: BloodPressure;
  ecg: number[];
}

export interface TelemetryMessage {
  messageId: string;
  deviceId: string;
  patientId: string;
  timestamp: string;
  mode: 'SIMULATION' | 'HARDWARE';
  scenario: ScenarioKey;
  bufferedOffline?: boolean;
  vitals: VitalSigns;
}

export interface ScenarioMetadata {
  key: ScenarioKey;
  label: string;
  badgeColor: string;
  description: string;
}
