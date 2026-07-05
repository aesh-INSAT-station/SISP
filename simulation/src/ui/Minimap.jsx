import React, { useEffect, useRef } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { getGroundTrack } from '../sim/keplerian.js';

const W = 252;
const H = 126;

function project(lonDeg, latDeg) {
  return {
    x: ((lonDeg + 180) / 360) * W,
    y: ((90 - latDeg) / 180) * H,
  };
}

export function Minimap({ sat }) {
  const canvasRef = useRef(null);
  const { refs, ready } = useSISP();
  const lastRedrawRef = useRef(0);

  useEffect(() => {
    if (!ready || !sat) return;
    const draw = () => {
      const ctx = canvasRef.current && canvasRef.current.getContext('2d');
      if (!ctx) return;

      // Background
      ctx.fillStyle = '#020810';
      ctx.fillRect(0, 0, W, H);

      // Grid
      ctx.strokeStyle = 'rgba(0,185,255,0.08)';
      ctx.lineWidth = 0.5;
      for (let x = 0; x <= W; x += W / 12) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (let y = 0; y <= H; y += H / 6) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }

      // Ground track
      const simSec = refs.current.simClock.currentTime;
      const track = getGroundTrack(sat.elements, simSec, 90, 60);

      ctx.strokeStyle = 'rgba(0,185,255,0.55)';
      ctx.setLineDash([3, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      let pen = false, prevX = null;
      for (const pt of track) {
        const p = project(pt.lon_deg, pt.lat_deg);
        if (pen && prevX != null && Math.abs(p.x - prevX) > W * 0.5) pen = false;
        if (!pen) { ctx.moveTo(p.x, p.y); pen = true; }
        else ctx.lineTo(p.x, p.y);
        prevX = p.x;
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Current position crosshair
      if (sat.lat_deg != null && sat.lon_deg != null) {
        const p = project(sat.lon_deg, sat.lat_deg);
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(p.x - 5, p.y); ctx.lineTo(p.x + 5, p.y);
        ctx.moveTo(p.x, p.y - 5); ctx.lineTo(p.x, p.y + 5);
        ctx.stroke();
        ctx.fillStyle = '#00ff88';
        ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI * 2); ctx.fill();
      }
    };

    draw();
    lastRedrawRef.current = Date.now();
    const id = setInterval(() => {
      const m = refs.current.simClock.multiplier || 1;
      const realMs = Math.max(33, (2 * 1000) / m);
      if (Date.now() - lastRedrawRef.current >= realMs) {
        draw();
        lastRedrawRef.current = Date.now();
      }
    }, 100);
    return () => clearInterval(id);
  }, [ready, refs, sat]);

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      style={{ width: W, height: H, display: 'block', border: '1px solid rgba(0,185,255,0.12)' }}
    />
  );
}
