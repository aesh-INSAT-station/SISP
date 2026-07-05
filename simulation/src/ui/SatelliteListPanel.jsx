import React from 'react';
import { useInsights } from '../hooks/useInsights.js';
import { useSISP } from '../context/SISPContext.jsx';
import { SAT_CONFIG, STATE_COLOR_CSS, TEXT_DIM, TEXT_SECONDARY } from '../constants/index.js';
import { DraggablePanel } from './DraggablePanel.jsx';

export function SatelliteListPanel() {
  const snap = useInsights();
  const { selectedId, setSelectedId, setCameraMode } = useSISP();

  const select = (id) => {
    setSelectedId(id);
    setCameraMode('TRACK');
  };

  const rows = snap?.sigs || SAT_CONFIG.map((sat) => ({
    id: sat.id,
    name: sat.name,
    state: 'IDLE',
    energy: 0,
    degr: 0,
    inSunlight: false,
  }));
  const listRect = {
    left: Math.min(296, Math.max(16, window.innerWidth - 614)),
    top: 74,
    width: 282,
    height: Math.min(338, window.innerHeight - 148),
  };

  return (
    <DraggablePanel
      id="satellite-list"
      title="Satellites"
      defaultRect={listRect}
      minWidth={250}
      minHeight={220}
      bodyStyle={{ padding: 8 }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {rows.map((sat) => {
          const cfg = SAT_CONFIG.find((item) => item.id === sat.id);
          const active = selectedId === sat.id;
          const color = STATE_COLOR_CSS[sat.state] || STATE_COLOR_CSS.IDLE;
          return (
            <button
              key={sat.id}
              type="button"
              onClick={() => select(sat.id)}
              style={{
                width: '100%',
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: '7px 10px',
                alignItems: 'center',
                padding: '9px 10px',
                textAlign: 'left',
                border: `1px solid ${active ? color : 'rgba(255,255,255,0.07)'}`,
                borderRadius: 6,
                background: active ? 'rgba(0,185,255,0.13)' : 'rgba(0,0,0,0.18)',
                color: '#d4eeff',
                cursor: 'pointer',
                font: 'inherit',
              }}
            >
              <span style={{ minWidth: 0 }}>
                <span
                  style={{
                    display: 'block',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontSize: 11,
                    letterSpacing: '0.06em',
                  }}
                >
                  {sat.name || cfg?.name || `SAT ${sat.id}`}
                </span>
                <span style={{ display: 'block', marginTop: 3, color: TEXT_SECONDARY, fontSize: 8 }}>
                  {cfg?.role || 'ORBITAL NODE'}
                </span>
              </span>
              <span
                style={{
                  color,
                  border: `1px solid ${color}`,
                  borderRadius: 999,
                  padding: '2px 6px',
                  fontSize: 8,
                  background: 'rgba(0,0,0,0.22)',
                }}
              >
                {sat.state}
              </span>
              <Meter label="PWR" value={sat.energy} color={sat.energy < 30 ? '#ff3d5a' : '#00ff88'} />
              <Meter label="DEGR" value={(sat.degr / 15) * 100} color={sat.degr > 10 ? '#ff3d5a' : '#f5c518'} />
            </button>
          );
        })}
      </div>
      <div style={{ marginTop: 8, color: TEXT_DIM, fontSize: 8, letterSpacing: '0.08em' }}>
        SELECTING A SATELLITE ENTERS TRACK MODE
      </div>
    </DraggablePanel>
  );
}

function Meter({ label, value, color }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <span style={{ width: 34, color: TEXT_SECONDARY, fontSize: 8 }}>{label}</span>
      <span style={{ flex: 1, height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.07)', overflow: 'hidden' }}>
        <span
          style={{
            display: 'block',
            width: `${Math.max(0, Math.min(100, value))}%`,
            height: '100%',
            background: color,
          }}
        />
      </span>
    </span>
  );
}
