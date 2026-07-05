import React from 'react';

export function Metric({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: 8, color: '#64748b', letterSpacing: '0.1em' }}>{label}</div>
      <div style={{ color: color || '#cbd5e1', marginTop: 2 }}>{value}</div>
    </div>
  );
}
