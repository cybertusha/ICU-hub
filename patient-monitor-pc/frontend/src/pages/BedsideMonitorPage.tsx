import React, { useEffect, useState } from 'react';
import { ScenarioKey, TelemetryMessage } from '../types/vitals';
import { SCENARIO_CONFIGS, synthesizeEcgSamples } from '../simulator/ecgGenerator';
import { sendTelemetryToRaspberryPi } from '../services/gatewayClient';
import { EcgCanvas } from '../components/EcgCanvas';

const DEMO_PATIENTS = [
  { id: 'PATIENT-001', name: 'Emily Johnson', bed: 'ICU-01', deviceId: 'ICU-PI-001', age: 45, gender: 'F' },
  { id: 'PATIENT-002', name: 'Michael Chen', bed: 'ICU-02', deviceId: 'ICU-PI-002', age: 62, gender: 'M' },
  { id: 'PATIENT-003', name: 'Sarah Davis', bed: 'ICU-03', deviceId: 'ICU-PI-003', age: 58, gender: 'F' },
  { id: 'PATIENT-004', name: 'James Thompson', bed: 'ICU-04', deviceId: 'ICU-PI-004', age: 71, gender: 'M' },
  { id: 'PATIENT-005', name: 'Maria Rodriguez', bed: 'ICU-05', deviceId: 'ICU-PI-005', age: 39, gender: 'F' },
  { id: 'PATIENT-006', name: 'Robert Kim', bed: 'ICU-06', deviceId: 'ICU-PI-006', age: 54, gender: 'M' },
];

export const BedsideMonitorPage: React.FC = () => {
  const [selectedPatient, setSelectedPatient] = useState(DEMO_PATIENTS[0]);
  const [scenario, setScenario] = useState<ScenarioKey>('NORMAL');
  const [running, setRunning] = useState(true);
  const [hr, setHr] = useState(73);
  const [spo2, setSpo2] = useState(98);
  const [temp, setTemp] = useState(36.7);
  const [rr, setRr] = useState(16);
  const [sys, setSys] = useState(122);
  const [dia, setDia] = useState(78);
  const [lastTimestamp, setLastTimestamp] = useState(new Date().toISOString());
  const [txStatus, setTxStatus] = useState<string>('FORWARDED_TO_AWS');
  const [queueSize, setQueueSize] = useState(0);
  const [msgCount, setMsgCount] = useState(0);

  const monitoringStatus: 'NORMAL' | 'WARNING' | 'CRITICAL' =
    spo2 < 90 || hr > 120 || hr < 45 || temp >= 39.0 || rr > 28
      ? 'CRITICAL'
      : spo2 < 94 || hr > 100 || hr < 60 || temp > 38.0 || rr > 20 || rr < 12
      ? 'WARNING'
      : 'NORMAL';

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const cfg = SCENARIO_CONFIGS[scenario];
      const rand = (min: number, max: number) => min + Math.random() * (max - min);
      const nextHr = Math.round(hr * 0.55 + rand(cfg.hr[0], cfg.hr[1]) * 0.45);
      const nextSpo2 = Math.round(spo2 * 0.55 + rand(cfg.spo2[0], cfg.spo2[1]) * 0.45);
      const nextTemp = Number((temp * 0.55 + rand(cfg.temp[0], cfg.temp[1]) * 0.45).toFixed(1));
      const nextRr = Math.round(rr * 0.55 + rand(cfg.rr[0], cfg.rr[1]) * 0.45);
      const nextSys = Math.round(sys * 0.55 + rand(cfg.sys[0], cfg.sys[1]) * 0.45);
      const nextDia = Math.round(dia * 0.55 + rand(cfg.dia[0], cfg.dia[1]) * 0.45);

      setHr(nextHr);
      setSpo2(nextSpo2);
      setTemp(nextTemp);
      setRr(nextRr);
      setSys(nextSys);
      setDia(nextDia);

      const now = new Date().toISOString();
      setLastTimestamp(now);

      const payload: TelemetryMessage = {
        messageId: `MSG-${Date.now()}-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
        deviceId: selectedPatient.deviceId,
        patientId: selectedPatient.id,
        timestamp: now,
        mode: 'SIMULATION',
        scenario,
        vitals: {
          heartRate: nextHr,
          spo2: nextSpo2,
          temperature: nextTemp,
          respiratoryRate: nextRr,
          bloodPressure: { systolic: nextSys, diastolic: nextDia },
          ecg: synthesizeEcgSamples(nextHr, 40, cfg.noise),
        },
      };

      const res = await sendTelemetryToRaspberryPi(payload);
      setTxStatus(res.status);
      setQueueSize(res.offlineQueueSize);
      setMsgCount((c) => c + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [running, scenario, selectedPatient, hr, spo2, temp, rr, sys, dia]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 font-sans">
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Top Safety & Demo Banner */}
        <div className="bg-amber-500/15 border border-amber-500/40 text-amber-300 px-4 py-2 rounded-lg flex items-center justify-between text-xs font-medium">
          <span>
            SIMULATION DEMO MODE — Academic Prototype Only. Generated readings are NOT real patient measurements.
          </span>
          <span>Packets Transmitted: {msgCount} | Queue: {queueSize}</span>
        </div>

        {/* Header Bar */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Bedside ICU Patient Monitor</div>
            <div className="text-2xl font-bold text-white flex items-center gap-3">
              <span>{selectedPatient.name}</span>
              <span className="text-sm px-2.5 py-0.5 rounded bg-slate-800 text-sky-400">
                {selectedPatient.bed} ({selectedPatient.id})
              </span>
              <span
                className={`text-xs px-3 py-1 rounded-full font-bold ${
                  monitoringStatus === 'CRITICAL'
                    ? 'bg-red-500/20 text-red-400 border border-red-500/50 animate-pulse'
                    : monitoringStatus === 'WARNING'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                    : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                }`}
              >
                {monitoringStatus}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={selectedPatient.id}
              onChange={(e) => {
                const found = DEMO_PATIENTS.find((p) => p.id === e.target.value);
                if (found) setSelectedPatient(found);
              }}
              className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              {DEMO_PATIENTS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.bed} — {p.name} ({p.deviceId})
                </option>
              ))}
            </select>

            <button
              onClick={() => setRunning(!running)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold ${
                running ? 'bg-red-600 hover:bg-red-500' : 'bg-emerald-600 hover:bg-emerald-500'
              }`}
            >
              {running ? 'Pause Monitor' : 'Resume Monitor'}
            </button>
          </div>
        </div>

        {/* Main Monitor Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left 2 Columns: ECG Waveform + Secondary Vitals */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                  Lead II ECG Waveform (25 mm/s) — Simulated
                </span>
                <span className="text-xs text-slate-400">{lastTimestamp}</span>
              </div>
              <EcgCanvas heartRate={hr} status={monitoringStatus} running={running} />
            </div>

            {/* Scenario Controller Buttons */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                Live Presentation Scenario Switcher
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {(Object.keys(SCENARIO_CONFIGS) as ScenarioKey[]).map((key) => {
                  const active = scenario === key;
                  return (
                    <button
                      key={key}
                      onClick={() => setScenario(key)}
                      className={`p-2.5 rounded-lg border text-left transition ${
                        active
                          ? 'bg-sky-600/25 border-sky-400 text-white shadow'
                          : 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      <div className="text-xs font-bold">{SCENARIO_CONFIGS[key].label}</div>
                      <div className="text-[11px] text-slate-400 truncate">
                        {SCENARIO_CONFIGS[key].description}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right Column: High-Contrast Vital Parameter Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-1 gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-emerald-400 font-bold uppercase">Heart Rate (BPM)</div>
                <div className="text-xs text-slate-400">Limit: 60 - 100</div>
              </div>
              <div className="text-5xl font-black text-emerald-400 font-mono">{hr}</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-cyan-400 font-bold uppercase">SpO2 (%)</div>
                <div className="text-xs text-slate-400">Limit: 94 - 100%</div>
              </div>
              <div className="text-5xl font-black text-cyan-400 font-mono">{spo2}</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-amber-400 font-bold uppercase">Temp (°C)</div>
                <div className="text-xs text-slate-400">Limit: 36.0 - 38.0</div>
              </div>
              <div className="text-5xl font-black text-amber-400 font-mono">{temp.toFixed(1)}</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center">
              <div>
                <div className="text-xs text-sky-400 font-bold uppercase">Resp Rate (RR/min)</div>
                <div className="text-xs text-slate-400">Limit: 12 - 20</div>
              </div>
              <div className="text-5xl font-black text-sky-400 font-mono">{rr}</div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex justify-between items-center col-span-2 lg:col-span-1">
              <div>
                <div className="text-xs text-orange-400 font-bold uppercase">NIBP (mmHg)</div>
                <div className="text-xs text-slate-400">SYS / DIA</div>
              </div>
              <div className="text-4xl font-black text-orange-400 font-mono">
                {sys}/{dia}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
