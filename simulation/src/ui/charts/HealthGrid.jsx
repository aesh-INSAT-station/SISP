import React from 'react';
import { STATE_COLOR_CSS } from '../../constants/index.js';
import { hex } from '../../utils/format.js';
import { useSISP } from '../../context/SISPContext.jsx';

function fleetLabel(p) {
  if (p > 70) return { color: '#4ade80', text: 'NOMINAL' };
  if (p > 40) return { color: '#f5c518', text: 'DEGRADED' };
  return { color: '#ef4444', text: 'CRITICAL' };
}

export function HealthGrid({ snap }) {
  const { selectedId, setSelectedId, setCameraMode } = useSISP();
  const sigs = snap.sigs;
  const lab = fleetLabel(snap.fleetHealth);
  const select = (id) => {
    setSelectedId(id);
    setCameraMode('TRACK');
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {sigs.map((s) => (
          <div
            key={s.id}
            title={`${s.name} · ${s.state}`}
            onClick={() => select(s.id)}
            style={{
              width: 14,
              height: 14,
              borderRadius: '50%',
              background: s.pulse
                ? '#4ade80'
                : STATE_COLOR_CSS[s.state] || STATE_COLOR_CSS.IDLE,
              border:
                selectedId === s.id ? '1px solid #fff' : '1px solid rgba(255,255,255,0.10)',
              cursor: 'pointer',
            }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 28, color: lab.color, fontVariantNumeric: 'tabular-nums' }}>
          {snap.fleetHealth.toFixed(0)}%
        </span>
        <span
          style={{
            fontSize: 9,
            color: lab.color,
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
          }}
        >
          {lab.text} FLEET
        </span>
      </div>
      <div style={{ display: 'flex', gap: 6, fontSize: 9 }}>
        <Pill label="PKT" value={snap.totalPkts} />
        <Pill label="SCEN" value={snap.activeScenarios} accent={snap.activeScenarios > 0} />
        <Pill label="RELAY" value={`${snap.relayLoad}%`} />
      </div>
    </div>
  );
}

function Pill({ label, value, accent }) {
  return (
    <div
      style={{
        flex: 1,
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.06)',
        padding: '4px 6px',
        textAlign: 'center',
      }}
    >
      <div style={{ color: '#475569', letterSpacing: '0.1em' }}>{label}</div>
      <div style={{ color: accent ? '#f5c518' : '#cbd5e1', marginTop: 2 }}>{value}</div>
    </div>
  );
}
