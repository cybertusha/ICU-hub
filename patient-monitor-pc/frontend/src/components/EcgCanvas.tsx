import React, { useEffect, useRef } from 'react';

interface EcgCanvasProps {
  heartRate: number;
  status: 'NORMAL' | 'WARNING' | 'CRITICAL';
  running: boolean;
}

export const EcgCanvas: React.FC<EcgCanvasProps> = ({ heartRate, status, running }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let x = 0;
    let phase = 0;
    const width = canvas.width;
    const height = canvas.height;
    const points: number[] = new Array(width).fill(height / 2);

    const render = () => {
      if (running) {
        const bps = Math.max(40, heartRate) / 60;
        for (let step = 0; step < 3; step++) {
          phase = (phase + bps / 60) % 1.0;
          const p = 0.15 * Math.exp(-Math.pow(phase - 0.18, 2) / (2 * Math.pow(0.035, 2)));
          const q = -0.15 * Math.exp(-Math.pow(phase - 0.35, 2) / (2 * Math.pow(0.012, 2)));
          const r = 1.15 * Math.exp(-Math.pow(phase - 0.38, 2) / (2 * Math.pow(0.01, 2)));
          const s = -0.28 * Math.exp(-Math.pow(phase - 0.41, 2) / (2 * Math.pow(0.014, 2)));
          const tw = 0.28 * Math.exp(-Math.pow(phase - 0.65, 2) / (2 * Math.pow(0.048, 2)));
          const val = p + q + r + s + tw + (Math.random() - 0.5) * 0.03;
          points[x] = height * 0.62 - val * (height * 0.44);
          x = (x + 1) % width;
        }
      }

      ctx.fillStyle = '#070d19';
      ctx.fillRect(0, 0, width, height);

      // Medical grid
      ctx.strokeStyle = 'rgba(30, 58, 138, 0.28)';
      ctx.lineWidth = 1;
      for (let gx = 0; gx < width; gx += 25) {
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, height);
        ctx.stroke();
      }
      for (let gy = 0; gy < height; gy += 25) {
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(width, gy);
        ctx.stroke();
      }

      // Draw ECG trace with phosphor sweep gap
      ctx.strokeStyle =
        status === 'CRITICAL' ? '#ef4444' : status === 'WARNING' ? '#f59e0b' : '#10b981';
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      for (let i = 0; i < width; i++) {
        if (Math.abs(i - x) < 14) continue;
        if (i === 0 || Math.abs(i - 1 - x) < 14) {
          ctx.moveTo(i, points[i]);
        } else {
          ctx.lineTo(i, points[i]);
        }
      }
      ctx.stroke();

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, [heartRate, status, running]);

  return (
    <canvas
      ref={canvasRef}
      width={760}
      height={170}
      className="w-full h-44 rounded-lg border border-slate-800 bg-slate-950"
    />
  );
};
