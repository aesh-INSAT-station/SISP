import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { useGlobalLog } from '../hooks/useGlobalLog.js';
import { useHUD } from '../hooks/useHUD.js';
import {
  PANEL_BG, PANEL_BORDER, FONT_MONO, SERVICE_COLOR, SAT_CONFIG, PANEL_SHADOW, PANEL_RADIUS,
} from '../constants/index.js';
import { hex, relTime } from '../utils/format.js';
import { DraggablePanel } from './DraggablePanel.jsx';

const FILTERS = ['ALL', 'CORRECTION', 'RELAY', 'HEARTBEAT', 'FAILURE', 'BORROW', 'STATUS'];
const DRAWER_HEIGHT = 240;
const TOGGLE_OFFSET_BOTTOM = 72;

function nameFor(id) {
  if (id === 0) return 'GROUND';
  const cfg = SAT_CONFIG.find((c) => c.id === id);
  return cfg ? cfg.name : `0x${id.toString(16).toUpperCase()}`;
}

function payloadSummary(entry) {
  const p = entry.payload || {};
  const keys = Object.keys(p);
  if (keys.length === 0) return '';
  return keys
    .slice(0, 3)
    .map((k) => `${k}=${p[k]}`)
    .join(' ');
}

// Hex view: 64-byte synthetic frame derived deterministically from the entry.
// Header bytes 0–3 = src, dst, service-id, seq.
// Bytes 4 = length, 5–6 = checksum, 7 = flags-bitmap.
// Bytes 8..(7+payloadLen) = JSON-encoded payload (truncated to fit).
// Last byte = trailer checksum complement.
function buildFrame(entry) {
  const total = 64;
  const buf = new Uint8Array(total);
  buf[0] = entry.src & 0xff;
  buf[1] = entry.dst & 0xff;
  buf[2] = hash8(entry.service);
  buf[3] = entry.seq & 0xff;
  buf[4] = (entry.length || 16) & 0xff;
  const csum = parseInt(entry.checksum, 16) || 0;
  buf[5] = (csum >> 8) & 0xff;
  buf[6] = csum & 0xff;
  let flagBits = 0;
  if (entry.flags) {
    if (entry.flags.includes('R')) flagBits |= 0x01;
    if (entry.flags.includes('T')) flagBits |= 0x02;
    if (entry.flags.includes('O')) flagBits |= 0x04;
    if (entry.flags.includes('P')) flagBits |= 0x08;
  }
  buf[7] = flagBits;
  // payload starts at 8
  const payloadStr = JSON.stringify(entry.payload || {}).slice(0, total - 9);
  for (let i = 0; i < payloadStr.length; i++) {
    buf[8 + i] = payloadStr.charCodeAt(i) & 0xff;
  }
  buf[total - 1] = (~buf[6]) & 0xff;
  return buf;
}

function hash8(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return h & 0xff;
}

export function EventLogDrawer() {
  const { drawerOpen, setDrawerOpen, logFilter, setLogFilter, setSelectedId, setCameraMode } = useSISP();
  const allLog = useGlobalLog();
  const hud = useHUD();
  const [expanded, setExpanded] = useState(null);
  const tableRef = useRef(null);
  const userScrolledRef = useRef(false);

  const filtered = useMemo(() => {
    if (logFilter === 'ALL') return allLog;
    return allLog.filter((e) => e.family === logFilter);
  }, [allLog, logFilter]);

  // Auto-scroll-to-top behaviour: pause when the user scrolls down, resume when at top.
  useEffect(() => {
    const el = tableRef.current;
    if (!el) return;
    const onScroll = () => {
      userScrolledRef.current = el.scrollTop > 8;
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (!userScrolledRef.current && tableRef.current) {
      tableRef.current.scrollTop = 0;
    }
  }, [filtered]);

  const logPanelRect = {
    left: Math.min(318, Math.max(16, window.innerWidth - 792)),
    top: Math.max(86, window.innerHeight - 360),
    width: Math.max(420, Math.min(760, window.innerWidth - 48)),
    height: DRAWER_HEIGHT,
  };

  return (
    <>
      <button
        onClick={() => setDrawerOpen(!drawerOpen)}
        style={{
          position: 'fixed',
          left: 16,
          bottom: TOGGLE_OFFSET_BOTTOM,
          background: drawerOpen ? 'rgba(74,158,255,0.20)' : PANEL_BG,
          border: PANEL_BORDER,
          borderRadius: PANEL_RADIUS,
          boxShadow: PANEL_SHADOW,
          color: drawerOpen ? '#4a9eff' : '#cbd5e1',
          padding: '6px 10px',
          fontFamily: FONT_MONO,
          fontSize: 10,
          letterSpacing: '0.1em',
          cursor: 'pointer',
          textTransform: 'uppercase',
          zIndex: 5000,
          backdropFilter: 'blur(16px) saturate(130%)',
        }}
      >
        ≡ PROTOCOL LOG · {allLog.length}
      </button>

      {drawerOpen && (
        <DraggablePanel
          id="protocol-log"
          title="Protocol Log"
          defaultRect={logPanelRect}
          minWidth={420}
          minHeight={180}
          bodyStyle={{ display: 'flex', flexDirection: 'column', fontFamily: FONT_MONO, color: '#cbd5e1' }}
          actions={
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              title="Close log"
              style={{
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(0,0,0,0.18)',
                color: '#94a3b8',
                width: 22,
                height: 22,
                borderRadius: 4,
                cursor: 'pointer',
                fontFamily: FONT_MONO,
              }}
            >
              x
            </button>
          }
        >
          <div
            style={{
              display: 'flex',
              gap: 4,
              padding: '6px 12px',
              borderBottom: PANEL_BORDER,
              alignItems: 'center',
            }}
          >
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setLogFilter(f)}
                style={{
                  background: logFilter === f ? 'rgba(74,158,255,0.20)' : 'transparent',
                  border: '1px solid rgba(255,255,255,0.10)',
                  color: logFilter === f ? '#4a9eff' : '#94a3b8',
                  padding: '3px 8px',
                  fontSize: 9,
                  letterSpacing: '0.1em',
                  cursor: 'pointer',
                }}
              >
                {f}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 9, color: '#475569' }}>
              {filtered.length} / {allLog.length}
            </span>
          </div>

						<div
							ref={tableRef}
							className="nuwa-scroll"
							style={{
								flex: 1,
								overflowY: 'auto',
              padding: '0 4px',
            }}
          >
            {filtered.length === 0 && (
              <div style={{ padding: 16, color: '#475569', fontSize: 10, textAlign: 'center' }}>
                no events match filter
              </div>
            )}
            {filtered.map((entry) => (
              <Row
                key={entry.gseq}
                entry={entry}
                now={hud.simTimeMs}
                expanded={expanded === entry.gseq}
                onClick={() => setExpanded(expanded === entry.gseq ? null : entry.gseq)}
                selectSat={(id) => {
                  setSelectedId(id);
                  setCameraMode('TRACK');
                }}
              />
            ))}
          </div>
        </DraggablePanel>
      )}
    </>
  );
}

function Row({ entry, now, expanded, onClick, selectSat }) {
  const svcColor = SERVICE_COLOR[entry.service] || '#94a3b8';
  const summary = payloadSummary(entry);
  return (
    <div
      onClick={onClick}
      style={{
        padding: '3px 8px',
        margin: '1px 0',
        background: expanded ? 'rgba(255,255,255,0.04)' : 'transparent',
        borderLeft: `2px solid ${expanded ? svcColor : 'transparent'}`,
        cursor: 'pointer',
        fontSize: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: '#475569', width: 50, fontSize: 9 }}>{relTime(now, entry.ts)}</span>
        <span
          style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: svcColor,
          }}
        />
        <button
          onClick={(e) => {
            e.stopPropagation();
            selectSat(entry.src);
          }}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#cbd5e1',
            cursor: 'pointer',
            fontFamily: FONT_MONO,
            fontSize: 9,
            padding: 0,
            width: 78,
            textAlign: 'left',
          }}
        >
          {nameFor(entry.src)}
        </button>
        <span style={{ color: '#475569', width: 14, textAlign: 'center' }}>→</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (entry.dst !== 0) selectSat(entry.dst);
          }}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#cbd5e1',
            cursor: 'pointer',
            fontFamily: FONT_MONO,
            fontSize: 9,
            padding: 0,
            width: 78,
            textAlign: 'left',
          }}
        >
          {nameFor(entry.dst)}
        </button>
        <span
          style={{
            background: 'rgba(0,0,0,0.4)',
            color: svcColor,
            padding: '1px 5px',
            fontSize: 9,
            letterSpacing: '0.05em',
          }}
        >
          {entry.service}
        </span>
        <span style={{ color: '#475569', fontSize: 9, width: 32 }}>#{entry.seq}</span>
        <span style={{ color: '#f5c518', fontSize: 9, width: 30 }}>
          {entry.flags.length ? '[' + entry.flags.join('') + ']' : ''}
        </span>
        <span
          style={{
            color: '#94a3b8',
            fontSize: 9,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {summary}
        </span>
      </div>
      {expanded && <FrameView entry={entry} svcColor={svcColor} />}
    </div>
  );
}

function FrameView({ entry, svcColor }) {
  const buf = useMemo(() => buildFrame(entry), [entry]);
  return (
    <div
      style={{
        marginTop: 6,
        padding: '6px 8px',
        background: 'rgba(0,0,0,0.4)',
        border: '1px solid rgba(255,255,255,0.05)',
        fontSize: 9,
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(16, 1fr)',
          gap: 1,
          fontFamily: FONT_MONO,
        }}
      >
        {Array.from(buf).map((b, i) => {
          let bg = 'rgba(255,255,255,0.03)';
          let color = '#94a3b8';
          if (i < 8) {
            bg = 'rgba(74,158,255,0.18)';
            color = '#4a9eff';
          } else if (i === buf.length - 1) {
            bg = 'rgba(239,68,68,0.18)';
            color = '#ef4444';
          } else if (b !== 0) {
            bg = 'rgba(74,222,128,0.10)';
            color = '#4ade80';
          }
          return (
            <span
              key={i}
              style={{
                background: bg,
                color,
                textAlign: 'center',
                padding: '2px 0',
                fontSize: 9,
              }}
            >
              {b.toString(16).padStart(2, '0').toUpperCase()}
            </span>
          );
        })}
      </div>
      <div
        style={{
          marginTop: 6,
          display: 'grid',
          gridTemplateColumns: '70px 1fr',
          gap: '2px 8px',
          fontSize: 9,
          color: '#94a3b8',
        }}
      >
        <span style={{ color: '#4a9eff' }}>HEADER</span>
        <span>SRC={hex(entry.src)} DST={hex(entry.dst)} SVC={entry.service} SEQ={entry.seq}</span>
        <span style={{ color: '#4ade80' }}>PAYLOAD</span>
        <span>
          {Object.entries(entry.payload || {})
            .map(([k, v]) => `${k}=${v}`)
            .join(' · ') || '∅'}
        </span>
        <span style={{ color: '#f5c518' }}>FLAGS</span>
        <span>{entry.flags.length ? entry.flags.join(' ') : '—'}</span>
        <span style={{ color: '#ef4444' }}>CHECKSUM</span>
        <span>{entry.checksum}</span>
      </div>
      <div style={{ marginTop: 4, fontSize: 8, color: '#475569' }}>
        <span style={{ color: '#4a9eff' }}>blue</span>=header ·{' '}
        <span style={{ color: '#4ade80' }}>green</span>=payload ·{' '}
        <span style={{ color: '#ef4444' }}>red</span>=checksum
      </div>
    </div>
  );
}
