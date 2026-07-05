import React from 'react';

export function DegrRow({ label, value, max }) {
  const pct = Math.min(1, value / max);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, marginBottom: 4 }}>
      <div style={{ width: 64, color: '#64748b', letterSpacing: '0.05em', fontSize: 9 }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 1 }}>
        <div
          style={{
            width: `${pct * 100}%`,
            height: '100%',
            background: '#4a9eff',
            borderRadius: 1,
          }}
        />
      </div>
      <div style={{ width: 36, textAlign: 'right', color: '#cbd5e1', fontSize: 10 }}>
        {typeof value === 'number' ? value.toFixed(1) : value}/{max}
      </div>
    </div>
  );
}
