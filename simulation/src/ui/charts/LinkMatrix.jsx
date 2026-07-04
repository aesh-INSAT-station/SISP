import React, { useEffect, useRef } from 'react';
import { useSISP } from '../../context/SISPContext.jsx';

const CELL = 22;
const PAD_LEFT = 22;
const PAD_TOP = 14;

// 8×8 LOS matrix. Click a cell to fire STATUS_BROADCAST between those sats.
export function LinkMatrix({ snap }) {
  const canvasRef = useRef(null);
  const { refs, ready } = useSISP();
  const W = PAD_LEFT + 8 * CELL + 6;
  const H = PAD_TOP + 8 * CELL + 6;

  useEffect(() => {
    const ctx = canvasRef.current && canvasRef.current.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#04080d';
    ctx.fillRect(0, 0, W, H);

    if (!snap) return;
    const { matrix, failures, ids } = snap;

    // Header labels
    ctx.fillStyle = '#475569';
    ctx.font = '8px ui-monospace, monospace';
    for (let i = 0; i < 8; i++) {
      const lbl = ids[i].toString(16).padStart(2, '0');
      ctx.fillText(lbl, PAD_LEFT + i * CELL + 4, 10);
      ctx.fillText(lbl, 2, PAD_TOP + i * CELL + 14);
    }

    for (let i = 0; i < 8; i++) {
      for (let j = 0; j < 8; j++) {
        const x = PAD_LEFT + j * CELL;
        const y = PAD_TOP + i * CELL;
        if (i === j) {
          ctx.fillStyle = 'rgba(255,255,255,0.04)';
        } else if (failures[i][j]) {
          ctx.fillStyle = '#f5c518';
        } else if (matrix[i][j]) {
          ctx.fillStyle = '#4a9eff';
        } else {
          ctx.fillStyle = 'rgba(255,255,255,0.05)';
        }
        ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2);
      }
    }
  }, [snap, W, H]);

  const onClick = (e) => {
    if (!ready || !snap) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - PAD_LEFT;
    const y = e.clientY - rect.top - PAD_TOP;
    const j = Math.floor(x / CELL);
    const i = Math.floor(y / CELL);
    if (i < 0 || j < 0 || i >= 8 || j >= 8 || i === j) return;
    const protocol = refs.current.protocol;
    const engine = refs.current.engine;
    const a = engine.getSat(snap.ids[i]);
    const b = engine.getSat(snap.ids[j]);
    if (!a || !b) return;
    protocol.sendPacket(a, b, 'STATUS_BROADCAST');
  };

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      onClick={onClick}
      style={{
        width: W,
        height: H,
        display: 'block',
        cursor: 'crosshair',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    />
  );
}
