import React from 'react';
import { useHUD } from '../hooks/useHUD.js';
import { usePlayback } from '../hooks/usePlayback.js';
import { useGroundContacts } from '../hooks/useGroundContacts.js';
import { FONT_MONO, ACCENT, PANEL_BG, PANEL_BORDER, TEXT_SECONDARY, STATUS_GREEN, PANEL_SHADOW } from '../constants/index.js';

const SNAPS = [1, 10, 60, 300, 600, 3600];

function nearestSnap(m) {
  return SNAPS.reduce((best, s) => (Math.abs(s - m) < Math.abs(best - m) ? s : best), SNAPS[0]);
}

function mulColor(m) {
  if (m > 3600) return '#ff3d5a';
  if (m > 600)  return '#f5c518';
  return '#d4eeff';
}

export function PlaybackBar() {
  const hud      = useHUD();
  const { togglePlay, setMultiplier, stepBack, stepForward } = usePlayback();
  const snap     = nearestSnap(hud.multiplier);
  const stations = useGroundContacts();
  const tColor   = mulColor(hud.multiplier);

  return (
    <div
      style={{
        position: 'fixed',
        left: '50%',
        bottom: 72,
        transform: 'translateX(-50%)',
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: 9999,
        boxShadow: PANEL_SHADOW,
        padding: '7px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontFamily: FONT_MONO,
        fontSize: 10,
        color: TEXT_SECONDARY,
        backdropFilter: 'blur(18px) saturate(130%)',
        zIndex: 22,
        pointerEvents: 'auto',
        whiteSpace: 'nowrap',
      }}
    >
      {/* Transport controls */}
      <IconBtn label="◀◀" onClick={stepBack}   title="−5 min sim" />
      <IconBtn label={hud.isPlaying ? '⏸' : '▶'} onClick={togglePlay} title={hud.isPlaying ? 'pause' : 'play'} />
      <IconBtn label="▶▶" onClick={stepForward} title="+5 min sim" />

      {/* Speed slider */}
      <input
        type="range" min={1} max={3600} step={1}
        value={hud.multiplier}
        onChange={(e) => setMultiplier(Number(e.target.value))}
        style={{ width: 96, accentColor: ACCENT, cursor: 'pointer' }}
      />

      {/* Speed presets */}
      <div style={{ display: 'flex', gap: 2 }}>
        {SNAPS.map((s) => (
          <button
            key={s}
            onClick={() => setMultiplier(s)}
            style={{
              background:  snap === s ? 'rgba(0,185,255,0.18)' : 'transparent',
              border:      `1px solid ${snap === s ? ACCENT : 'rgba(255,255,255,0.06)'}`,
              color:       snap === s ? ACCENT : '#2a5a7a',
              padding:     '1px 5px', fontSize: 8,
              fontFamily:  FONT_MONO, cursor: 'pointer', borderRadius: 3,
            }}
          >
            {s}×
          </button>
        ))}
      </div>

      <div style={{ width: 1, height: 16, background: 'rgba(0,185,255,0.10)' }} />

      {/* Sim time */}
      <span style={{ color: '#2a5a7a', fontSize: 8, letterSpacing: '0.12em' }}>SIM</span>
      <span style={{ color: tColor, fontVariantNumeric: 'tabular-nums', fontSize: 10, letterSpacing: '0.05em' }}>
        {hud.simTime}
      </span>

      {/* Ground stations */}
      <div style={{ width: 1, height: 16, background: 'rgba(0,185,255,0.10)' }} />
      <span style={{ color: '#2a5a7a', fontSize: 8, letterSpacing: '0.12em' }}>GS</span>
      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
        {stations.map((st) => (
          <div
            key={st.id}
            title={`${st.name}${st.contact ? ' · LOS' : ''}`}
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: st.contact ? STATUS_GREEN : 'rgba(255,255,255,0.10)',
              boxShadow: st.contact ? `0 0 5px ${STATUS_GREEN}88` : 'none',
            }}
          />
        ))}
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, title }) {
  return (
    <button
      onClick={onClick} title={title}
      style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 11, padding: '2px 4px', fontFamily: FONT_MONO }}
    >
      {label}
    </button>
  );
}
