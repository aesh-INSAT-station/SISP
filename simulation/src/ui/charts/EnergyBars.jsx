import React from 'react';
import { useSISP } from '../../context/SISPContext.jsx';

function barColor(p) {
  if (p > 60) return '#4ade80';
  if (p > 20) return '#f5c518';
  return '#ef4444';
}

export function EnergyBars({ snap }) {
  const { setSelectedId, setCameraMode, selectedId } = useSISP();
  const sigs = snap.sigs;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {sigs.map((s) => {
        const e = Math.max(0, Math.min(100, s.energy || 0));
        const isSelected = selectedId === s.id;
        return (
          <div
            key={s.id}
            onClick={() => {
              setSelectedId(s.id);
              setCameraMode('TRACK');
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 9,
              cursor: 'pointer',
              opacity: isSelected ? 1 : 0.92,
            }}
          >
            <span
              title={s.inSunlight ? 'sunlit' : 'eclipse'}
              style={{
                width: 10,
                textAlign: 'center',
                color: s.inSunlight ? '#fbbf24' : '#475569',
              }}
            >
              {s.inSunlight ? '☼' : '◐'}
            </span>
            <span
              style={{
                width: 64,
                color: isSelected ? '#fff' : '#94a3b8',
                fontSize: 9,
                letterSpacing: '0.05em',
              }}
            >
              {s.name}
            </span>
            <div
              style={{
                flex: 1,
                height: 6,
                background: 'rgba(255,255,255,0.05)',
                position: 'relative',
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${e}%`,
                  background: barColor(e),
                  transition: 'width 0.5s ease-out',
                }}
              />
            </div>
            <span
              style={{
                width: 28,
                textAlign: 'right',
                color: '#cbd5e1',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {Math.round(e)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
