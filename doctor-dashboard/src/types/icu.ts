export type UserRole = 'Doctor' | 'Nurse' | 'Admin';

export interface UserProfile {
  userId: string;
  username: string;
  fullName: string;
  initials: string;
  role: UserRole;
  department: string;
  email: string;
  phone: string;
  active: boolean;
  lastLogin: string;
  token?: string;
}

export interface PatientVitals {
  heartRate: number;
  spo2: number;
  temperature: number;
  respiratoryRate: number;
  bloodPressure: {
    systolic: number;
    diastolic: number;
  };
  ecg: number[];
}

export interface PatientRecord {
  patientId: string;
  patientName: string;
  age: number;
  gender: 'M' | 'F' | 'Other';
  bedNumber: string;
  monitoringDeviceId: string;
  monitoringStatus: 'NORMAL' | 'WARNING' | 'CRITICAL' | 'OFFLINE';
  condition: string;
  attendingPhysician: string;
  primaryNurse: string;
  allergies: string[];
  currentMedications: string[];
  alertsEnabled: boolean;
  admittedAt: string;
  vitals: PatientVitals;
  activeAlertsCount: number;
  deviceStatus: 'ONLINE' | 'OFFLINE' | 'MAINTENANCE' | 'ERROR';
  deviceIp: string;
  updatedAt: string;
}

export interface AlertItem {
  alertId: string;
  patientId: string;
  patientName: string;
  bedNumber: string;
  deviceId: string;
  parameter: string;
  category: 'vitals' | 'equipment' | 'system';
  priority: number;
  detectedValue: string | number;
  threshold: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  description: string;
  createdAt: string;
  acknowledged: boolean;
  acknowledgedBy: string | null;
  acknowledgedAt: string | null;
  resolved: boolean;
  resolvedBy: string | null;
  resolvedAt: string | null;
  recoveredAt: string | null;
}

export interface DeviceRecord {
  deviceId: string;
  deviceName: string;
  deviceType: string;
  location: string;
  ipAddress: string;
  deviceStatus: 'ONLINE' | 'OFFLINE' | 'MAINTENANCE' | 'ERROR';
  uptime: string;
  lastSeen: string;
  firmwareVersion: string;
  operatingMode: 'SIMULATION' | 'HARDWARE';
  assignedPatientId: string;
  bedNumber: string;
  offlineQueueSize: number;
  createdAt: string;
}
