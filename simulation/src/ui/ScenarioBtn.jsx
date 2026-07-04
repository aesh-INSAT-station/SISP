import React from 'react';
import { FONT_MONO, ACCENT, ACCENT_DIM } from '../constants/index.js';

export function ScenarioBtn({ label, onClick, enabled, running }) {
  return (
    <button
      onClick={onClick}
      disabled={!enabled}
      style={{
        background: running ? ACCENT_DIM : 'rgba(0,0,0,0.3)',
        border: `1px solid ${running ? ACCENT : 'rgba(255,255,255,0.08)'}`,
        color: running ? ACCENT : enabled ? '#94a3b8' : '#2a4a6a',
        padding: '4px 10px',
        fontFamily: FONT_MONO,
        fontSize: 9,
        letterSpacing: '0.10em',
        cursor: enabled ? 'pointer' : 'not-allowed',
        textTransform: 'uppercase',
        borderRadius: 2,
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        flexShrink: 0,
        whiteSpace: 'nowrap',
      }}
    >
      {running && (
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: ACCENT, animation: 'nuwa-blink 1s infinite' }} />
      )}
      {label}
      <style>{`@keyframes nuwa-blink{0%,100%{opacity:1}50%{opacity:0.15}}`}</style>
    </button>
  );
}
