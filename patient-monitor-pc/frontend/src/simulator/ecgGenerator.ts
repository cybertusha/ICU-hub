import { ScenarioKey, VitalSigns } from '../types/vitals';

export const SCENARIO_CONFIGS: Record<
  ScenarioKey,
  {
    label: string;
    description: string;
    hr: [number, number];
    spo2: [number, number];
    temp: [number, number];
    rr: [number, number];
    sys: [number, number];
    dia: [number, number];
    noise: number;
  }
> = {
  NORMAL: {
    label: '1. Normal Patient',
    description: 'Stable sinus rhythm within normal ranges',
    hr: [68, 78],
    spo2: [96, 99],
    temp: [36.5, 37.0],
    rr: [14, 18],
    sys: [116, 126],
    dia: [74, 82],
    noise: 0.02,
  },
  HIGH_HR: {
    label: '2. High Heart Rate',
    description: 'Tachycardia (>120 BPM)',
    hr: [125, 138],
    spo2: [95, 97],
    temp: [37.1, 37.5],
    rr: [19, 22],
    sys: [138, 148],
    dia: [88, 94],
    noise: 0.04,
  },
  LOW_SPO2: {
    label: '3. Low SpO2',
    description: 'Hypoxemia (<90% SpO2)',
    hr: [104, 114],
    spo2: [85, 89],
    temp: [36.8, 37.2],
    rr: [23, 27],
    sys: [106, 116],
    dia: [68, 76],
    noise: 0.03,
  },
  HIGH_TEMP: {
    label: '4. High Temperature',
    description: 'Hyperpyrexia (>38.8°C)',
    hr: [96, 108],
    spo2: [95, 97],
    temp: [38.8, 39.5],
    rr: [20, 23],
    sys: [124, 134],
    dia: [78, 86],
    noise: 0.03,
  },
  ABNORMAL_RR: {
    label: '5. Abnormal Resp. Rate',
    description: 'Tachypnea (>28 breaths/min)',
    hr: [94, 106],
    spo2: [92, 94],
    temp: [37.0, 37.4],
    rr: [28, 33],
    sys: [128, 138],
    dia: [82, 88],
    noise: 0.03,
  },
  CRITICAL: {
    label: '6. Critical Condition',
    description: 'Multi-vital critical emergency',
    hr: [134, 148],
    spo2: [83, 88],
    temp: [39.1, 39.8],
    rr: [29, 35],
    sys: [84, 92],
    dia: [50, 58],
    noise: 0.06,
  },
  RECOVERY: {
    label: '7. Patient Recovery',
    description: 'Vitals returning to normal baseline',
    hr: [72, 79],
    spo2: [97, 99],
    temp: [36.6, 36.9],
    rr: [15, 18],
    sys: [118, 124],
    dia: [76, 82],
    noise: 0.015,
  },
};

export function synthesizeEcgSamples(
  heartRate: number,
  count = 40,
  noise = 0.02,
  phaseOffset = 0
): number[] {
  const samples: number[] = [];
  const bps = Math.max(30, heartRate) / 60;
  for (let i = 0; i < count; i++) {
    const t = i / count + phaseOffset;
    const cycle = (t * bps * 2.0) % 1.0;
    const p = 0.15 * Math.exp(-Math.pow(cycle - 0.18, 2) / (2 * Math.pow(0.035, 2)));
    const q = -0.15 * Math.exp(-Math.pow(cycle - 0.35, 2) / (2 * Math.pow(0.012, 2)));
    const r = 1.15 * Math.exp(-Math.pow(cycle - 0.38, 2) / (2 * Math.pow(0.01, 2)));
    const s = -0.28 * Math.exp(-Math.pow(cycle - 0.41, 2) / (2 * Math.pow(0.014, 2)));
    const tw = 0.28 * Math.exp(-Math.pow(cycle - 0.65, 2) / (2 * Math.pow(0.048, 2)));
    const n = (Math.random() * 2 - 1) * noise;
    samples.push(Number((p + q + r + s + tw + n).toFixed(4)));
  }
  return samples;
}
