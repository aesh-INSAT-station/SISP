import React, { useEffect, useRef } from 'react';

const W = 240;
const H = 60;

// `buckets` is newest-first array of { total, errors }, length up to 10.
export function PacketRate({ buckets }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current && canvasRef.current.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#04080d';
    ctx.fillRect(0, 0, W, H);

    if (!buckets || buckets.length === 0) return;

    // Reverse so x increases with time (oldest left, newest right).
    const data = buckets.slice().reverse();
    const max = Math.max(1, ...data.map((b) => b.total));
    const step = W / (data.length - 1 || 1);

    const yFor = (v) => H - (v / max) * (H - 4) - 2;

    // Total area
    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let i = 0; i < data.length; i++) {
      ctx.lineTo(i * step, yFor(data[i].total));
    }
    ctx.lineTo(W, H);
    ctx.closePath();
    const g1 = ctx.createLinearGradient(0, 0, 0, H);
    g1.addColorStop(0, 'rgba(74,158,255,0.55)');
    g1.addColorStop(1, 'rgba(74,158,255,0.05)');
    ctx.fillStyle = g1;
    ctx.fill();

    // Total stroke
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = i * step;
      const y = yFor(data[i].total);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = '#4a9eff';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // Errors area
    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let i = 0; i < data.length; i++) {
      ctx.lineTo(i * step, yFor(data[i].errors));
    }
    ctx.lineTo(W, H);
    ctx.closePath();
    const g2 = ctx.createLinearGradient(0, 0, 0, H);
    g2.addColorStop(0, 'rgba(239,68,68,0.55)');
    g2.addColorStop(1, 'rgba(239,68,68,0.05)');
    ctx.fillStyle = g2;
    ctx.fill();

    // y-axis tick label
    ctx.fillStyle = '#475569';
    ctx.font = '8px ui-monospace, monospace';
    ctx.fillText(`max ${max}/min`, 4, 10);
  }, [buckets]);

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      style={{
        width: W,
        height: H,
        display: 'block',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    />
  );
}
