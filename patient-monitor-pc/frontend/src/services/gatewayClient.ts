import { TelemetryMessage } from '../types/vitals';

const DEFAULT_GATEWAY_URL =
  (import.meta as any).env?.VITE_GATEWAY_URL || 'http://localhost:5050/gateway/telemetry';

export interface GatewayTransmissionResult {
  ok: boolean;
  status: 'FORWARDED_TO_AWS' | 'BUFFERED_OFFLINE' | 'GATEWAY_UNREACHABLE';
  offlineQueueSize: number;
  latencyMs: number;
  error?: string;
}

export async function sendTelemetryToRaspberryPi(
  payload: TelemetryMessage,
  gatewayUrl: string = DEFAULT_GATEWAY_URL
): Promise<GatewayTransmissionResult> {
  const start = performance.now();
  try {
    const res = await fetch(gatewayUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const latencyMs = Math.round(performance.now() - start);
    if (!res.ok) {
      return {
        ok: false,
        status: 'GATEWAY_UNREACHABLE',
        offlineQueueSize: 0,
        latencyMs,
        error: `HTTP ${res.status}`,
      };
    }
    const data = await res.json();
    return {
      ok: true,
      status: data.cloudConnected ? 'FORWARDED_TO_AWS' : 'BUFFERED_OFFLINE',
      offlineQueueSize: data.offlineQueueSize ?? 0,
      latencyMs,
    };
  } catch (err: any) {
    return {
      ok: false,
      status: 'GATEWAY_UNREACHABLE',
      offlineQueueSize: 0,
      latencyMs: Math.round(performance.now() - start),
      error: err?.message || 'Connection refused',
    };
  }
}
