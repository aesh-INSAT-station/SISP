import React, { useEffect, useRef } from 'react';

function colorFor(v) {
  if (v <= 5) return '#4ade80';
  if (v <= 10) return '#f5c518';
  return '#ef4444';
}

// Single sparkline canvas. `series` is a 0..15 array up to length=samples.
export function Sparkline({ series, width = 160, height = 48, label }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current && canvasRef.current.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#04080d';
    ctx.fillRect(0, 0, width, height);

    // Threshold dashed line at degr=10
    ctx.strokeStyle = 'rgba(245,197,24,0.35)';
    ctx.setLineDash([3, 3]);
    const ty = height - (10 / 15) * height;
    ctx.beginPath();
    ctx.moveTo(0, ty);
    ctx.lineTo(width, ty);
    ctx.stroke();
    ctx.setLineDash([]);

    if (!series || series.length < 2) return;

    const n = series.length;
    const step = width / (n - 1);

    // Filled area below the line
    ctx.beginPath();
    ctx.moveTo(0, height);
    for (let i = 0; i < n; i++) {
      const v = Math.max(0, Math.min(15, series[i]));
      const x = i * step;
      const y = height - (v / 15) * height;
      ctx.lineTo(x, y);
    }
    ctx.lineTo(width, height);
    ctx.closePath();
    // Vertical gradient: green→amber→red
    const g = ctx.createLinearGradient(0, 0, 0, height);
    g.addColorStop(0, 'rgba(239,68,68,0.55)');
    g.addColorStop(0.33, 'rgba(245,197,24,0.45)');
    g.addColorStop(0.67, 'rgba(74,222,128,0.45)');
    g.addColorStop(1, 'rgba(74,222,128,0.05)');
    ctx.fillStyle = g;
    ctx.fill();

    // Line on top
    ctx.beginPath();
    ctx.lineWidth = 1.2;
    for (let i = 0; i < n; i++) {
      const v = Math.max(0, Math.min(15, series[i]));
      const x = i * step;
      const y = height - (v / 15) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    const last = series[series.length - 1] || 0;
    ctx.strokeStyle = colorFor(last);
    ctx.stroke();

    // Last-value dot
    ctx.fillStyle = colorFor(last);
    ctx.beginPath();
    ctx.arc((n - 1) * step, height - (last / 15) * height, 1.8, 0, Math.PI * 2);
    ctx.fill();
  }, [series, width, height]);

  return (
    <div style={{ position: 'relative' }}>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{ width, height, display: 'block' }}
      />
      {label && (
        <div
          style={{
            position: 'absolute',
            top: 2,
            left: 4,
            fontSize: 8,
            color: '#475569',
            letterSpacing: '0.1em',
          }}
        >
          {label}
        </div>
      )}
    </div>
  );
}
