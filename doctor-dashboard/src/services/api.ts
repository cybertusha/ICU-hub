import { PatientRecord, AlertItem, DeviceRecord, UserProfile } from '../types/icu';

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000/api';
export const WS_URL = (import.meta as any).env?.VITE_WS_URL || 'ws://localhost:8000/ws';

export async function loginDoctor(
  username: string,
  password: string,
  role: string
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  });
  if (!res.ok) throw new Error('Invalid credentials');
  return res.json();
}

export async function fetchPatients(): Promise<PatientRecord[]> {
  const res = await fetch(`${API_BASE}/patients`);
  const data = await res.json();
  return data.patients || [];
}

export async function fetchPatientHistory(patientId: string, hours = 1): Promise<any[]> {
  const res = await fetch(`${API_BASE}/patients/${patientId}/history?hours=${hours}`);
  const data = await res.json();
  return data.readings || [];
}

export async function fetchAlerts(params?: Record<string, string>): Promise<AlertItem[]> {
  const q = params ? '?' + new URLSearchParams(params).toString() : '';
  const res = await fetch(`${API_BASE}/alerts${q}`);
  const data = await res.json();
  return data.alerts || [];
}

export async function acknowledgeAlert(alertId: string, userName: string): Promise<AlertItem> {
  const res = await fetch(`${API_BASE}/alerts/${alertId}/acknowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userName }),
  });
  return res.json();
}

export async function resolveAlert(alertId: string, userName: string): Promise<AlertItem> {
  const res = await fetch(`${API_BASE}/alerts/${alertId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userName }),
  });
  return res.json();
}

export async function fetchDevices(): Promise<DeviceRecord[]> {
  const res = await fetch(`${API_BASE}/devices`);
  const data = await res.json();
  return data.devices || [];
}

export async function simulateDeviceDisconnect(
  deviceId: string,
  offline: boolean
): Promise<any> {
  const res = await fetch(`${API_BASE}/devices/${deviceId}/simulate-disconnect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ offline }),
  });
  return res.json();
}
