import React, { useEffect, useState } from 'react';
import { PatientRecord, AlertItem, DeviceRecord, UserProfile } from './types/icu';
import { fetchPatients, fetchAlerts, fetchDevices, WS_URL } from './services/api';
import { LoginPage } from './pages/LoginPage';

export const App: React.FC = () => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);

  useEffect(() => {
    fetchPatients().then(setPatients).catch(() => {});
    fetchAlerts().then(setAlerts).catch(() => {});
    fetchDevices().then(setDevices).catch(() => {});

    const ws = new WebSocket(WS_URL);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.event === 'INITIAL_SNAPSHOT') {
        setPatients(msg.data.patients || []);
        setAlerts(msg.data.alerts || []);
        setDevices(msg.data.devices || []);
      }
    };
    return () => ws.close();
  }, []);

  if (!user) {
    return <LoginPage onSuccess={setUser} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <h1 className="text-2xl font-bold">ICU Live Dashboard ({patients.length} Patients)</h1>
    </div>
  );
};

export default App;
