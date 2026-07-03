import React, { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { useSatellite } from '../hooks/useSatellite.js';
import { useHUD } from '../hooks/useHUD.js';
import {
  PANEL_BORDER, STATE_COLOR_CSS, FONT_MONO,
  ACCENT, ACCENT_DIM, TEXT_SECONDARY, TEXT_DIM,
} from '../constants/index.js';
import { hex, fmtUptime, degrColor } from '../utils/format.js';
import { Metric } from './Metric.jsx';
import { DegrRow } from './DegrRow.jsx';
import { PacketLogRow } from './PacketLogRow.jsx';
import { Minimap } from './Minimap.jsx';
import { DraggablePanel } from './DraggablePanel.jsx';

const STATUS_DOT_COLOR = {
  NOMINAL:  '#00ff88',
  DEGRADED: '#f5c518',
  FAULT:    '#ff3d5a',
  OFFLINE:  '#4a7a9b',
};

function fmt(deg, pos, neg) {
  if (deg == null) return '—';
  return `${deg >= 0 ? pos : neg}${Math.abs(deg).toFixed(2)}°`;
}

function fmtVal(v) {
  if (v == null || !isFinite(v)) return '—';
  const body = Math.abs(v) > 0 && Math.abs(v) < 0.001
    ? Number(v).toExponential(2)
    : Number(v).toFixed(2);
  return v >= 0 ? `+${body}` : body;
}

export function SatellitePanel() {
  const { selectedId, setSelectedId, cameraMode, setCameraMode, setSelectedSensor } = useSISP();
  const sat = useSatellite(selectedId);
  const hud = useHUD();
  const [expandedIdx, setExpandedIdx] = useState(null);

  useEffect(() => { setExpandedIdx(null); }, [selectedId]);

  if (!sat) return null;

  const close = () => { setSelectedId(null); setCameraMode('FREE'); };
  const detailRect = {
    left: Math.max(16, window.innerWidth - 332),
    top: 74,
    width: 316,
    height: Math.min(680, window.innerHeight - 148),
  };

  return (
    <DraggablePanel
      id="satellite-detail"
      title={sat.name || `SAT ${hex(sat.id)}`}
      defaultRect={detailRect}
      minWidth={292}
      minHeight={360}
      bodyStyle={{ display: 'flex', flexDirection: 'column', fontSize: 11, color: '#94a3b8' }}
    >
      <Header sat={sat} onClose={close} cameraMode={cameraMode} setCameraMode={setCameraMode} />
      <DegrBar degr={sat.degr} />
      <MetricsGrid sat={sat} />
      <Geodetic sat={sat} />
      <Breakdown sat={sat} />
      <SensorList sensors={sat.sensors} satId={sat.id} onViewSensor={setSelectedSensor} />
      <LogSection sat={sat} now={hud.simTimeMs} expandedIdx={expandedIdx} setExpandedIdx={setExpandedIdx} />
      <MinimapSection sat={sat} />
    </DraggablePanel>
  );
}

function Header({ sat, onClose, cameraMode, setCameraMode }) {
  const stateColor = STATE_COLOR_CSS[sat.state] || STATE_COLOR_CSS.IDLE;
  const tracking = cameraMode === 'TRACK';
  return (
    <div style={{ padding: '12px 14px', borderBottom: PANEL_BORDER }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 13, color: '#d4eeff', letterSpacing: '0.08em', fontWeight: 600 }}>
            {sat.name || `SAT ${hex(sat.id)}`}
          </div>
          <div style={{ fontSize: 9, color: TEXT_SECONDARY, marginTop: 2, letterSpacing: '0.05em' }}>
            {hex(sat.id)} · {sat.role}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6, alignItems: 'center' }}>
            <span
              style={{
                padding: '1px 6px', fontSize: 8,
                background: 'rgba(0,0,0,0.4)',
                border: `1px solid ${stateColor}`,
                color: stateColor, letterSpacing: '0.1em',
              }}
            >
              {sat.state}
            </span>
            <button
              onClick={() => setCameraMode(tracking ? 'FREE' : 'TRACK')}
              style={{
                background: tracking ? ACCENT_DIM : 'transparent',
                border: `1px solid ${tracking ? ACCENT : 'rgba(255,255,255,0.10)'}`,
                color: tracking ? ACCENT : TEXT_SECONDARY,
                padding: '1px 6px', fontSize: 8,
                fontFamily: FONT_MONO, cursor: 'pointer',
                letterSpacing: '0.08em',
              }}
            >
              {tracking ? 'TRACKING' : 'TRACK'}
            </button>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'transparent', border: 'none', color: TEXT_SECONDARY, cursor: 'pointer', fontSize: 14, padding: 2 }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}

function DegrBar({ degr }) {
  const segs = [];
  for (let i = 0; i < 15; i++) {
    let bg = 'rgba(255,255,255,0.04)';
    if (i < degr) {
      if (i < 5)  bg = '#00ff88';
      else if (i < 10) bg = '#f5c518';
      else bg = '#ff3d5a';
    }
    segs.push(<div key={i} style={{ flex: 1, height: 4, background: bg, borderRadius: 1 }} />);
  }
  return (
    <div style={{ padding: '8px 14px', borderBottom: PANEL_BORDER }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 8, color: TEXT_SECONDARY, marginBottom: 4, letterSpacing: '0.1em' }}>
        <span>INTEGRITY</span>
        <span style={{ color: degrColor(degr) }}>{degr} / 15</span>
      </div>
      <div style={{ display: 'flex', gap: 2 }}>{segs}</div>
    </div>
  );
}

function MetricsGrid({ sat }) {
  return (
    <div style={{ padding: '8px 14px', borderBottom: PANEL_BORDER, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px' }}>
      <Metric label="ENERGY"   value={`${Math.round(sat.energy)}%`} />
      <Metric label="UPTIME"   value={fmtUptime(sat.uptime_s)} />
      <Metric label="ORB ERR"  value={`${Math.round(sat.orbit_error_m)} m`} />
      <Metric label="SEQ"      value={`#${sat.seq}`} />
      <Metric label="SCENARIO" value={sat.activeScenario || '—'} color={sat.activeScenario ? '#f5c518' : TEXT_DIM} />
    </div>
  );
}

function Geodetic({ sat }) {
  return (
    <div style={{ padding: '8px 14px', borderBottom: PANEL_BORDER, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px' }}>
      <Metric label="LAT"    value={fmt(sat.lat_deg, '+', '')} />
      <Metric label="LON"    value={fmt(sat.lon_deg, '+', '')} />
      <Metric label="ALT"    value={`${(sat.alt_km || 0).toFixed(1)} km`} />
      <Metric label="PERIOD" value={`${(sat.period_s / 60).toFixed(1)} min`} />
    </div>
  );
}

function Breakdown({ sat }) {
  return (
    <div style={{ padding: '8px 14px', borderBottom: PANEL_BORDER }}>
      <div style={{ fontSize: 8, color: ACCENT, opacity: 0.7, marginBottom: 5, letterSpacing: '0.15em' }}>DEGRADATION</div>
      <DegrRow label="K-FACTOR" value={sat.degr_k}    max={5} />
      <DegrRow label="SVD RES"  value={sat.degr_svd}  max={5} />
      <DegrRow label="AGE"      value={sat.degr_age}  max={3} />
      <DegrRow label="ORBIT"    value={sat.degr_orbit} max={2} />
    </div>
  );
}

// ── Sensor list ───────────────────────────────────────────────────────────────

function SensorList({ sensors, satId, onViewSensor }) {
  if (!sensors || sensors.length === 0) return null;
  return (
    <div style={{ padding: '8px 14px', borderBottom: PANEL_BORDER }}>
      <div style={{ fontSize: 8, color: ACCENT, opacity: 0.7, marginBottom: 6, letterSpacing: '0.15em' }}>
        SENSORS
      </div>
      {sensors.map((sensor, idx) => (
        <React.Fragment key={sensor.id}>
          {idx > 0 && (
            <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', margin: '5px 0' }} />
          )}
          <SensorRow sensor={sensor} satId={satId} onViewSensor={onViewSensor} />
        </React.Fragment>
      ))}
    </div>
  );
}

function SensorRow({ sensor, satId, onViewSensor }) {
  const dotColor = STATUS_DOT_COLOR[sensor.status] || STATUS_DOT_COLOR.OFFLINE;
  const r = sensor.last_reading;

  // Show up to 4 axis readings inline, abbreviated for space
  const readingCells = sensor.active && r
    ? sensor.axes.slice(0, 4).map((axis) => (
        <span key={axis} style={{ marginRight: 5 }}>
          <span style={{ color: TEXT_DIM }}>{axis}:</span>
          <span style={{ color: '#94a3b8', marginLeft: 2 }}>{fmtVal(r[axis])}</span>
        </span>
      ))
    : null;

  return (
    <div style={{ opacity: sensor.active ? 1 : 0.45 }}>
      {/* Row 1: status dot + label + status badge + VIEW button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <div
          style={{
            width: 6, height: 6, borderRadius: '50%',
            background: dotColor,
            boxShadow: sensor.status === 'FAULT' ? `0 0 6px ${dotColor}` : 'none',
            flexShrink: 0,
          }}
        />
        <span style={{ flex: 1, fontSize: 10, color: '#d4eeff', fontFamily: FONT_MONO, letterSpacing: '0.04em' }}>
          {sensor.label}
        </span>
        <span style={{ fontSize: 7, color: dotColor, letterSpacing: '0.12em', flexShrink: 0 }}>
          {sensor.status}
        </span>
        {sensor.active ? (
          <button
            onClick={() => onViewSensor({ satelliteId: satId, sensorId: sensor.id })}
            style={{
              background: 'rgba(0,185,255,0.10)',
              border: '1px solid rgba(0,185,255,0.28)',
              color: ACCENT,
              padding: '1px 5px',
              fontSize: 7,
              fontFamily: FONT_MONO,
              cursor: 'pointer',
              letterSpacing: '0.06em',
              flexShrink: 0,
              lineHeight: 1.5,
            }}
          >
            VIEW
          </button>
        ) : (
          <span style={{ fontSize: 7, color: TEXT_DIM, border: '1px solid rgba(255,255,255,0.08)', padding: '1px 4px' }}>
            OFFLINE
          </span>
        )}
      </div>

      {/* Row 2: unit + inline reading values */}
      {sensor.active && (
        <div style={{ marginLeft: 11, marginTop: 2, fontSize: 8, color: TEXT_DIM, fontFamily: FONT_MONO }}>
          <span style={{ marginRight: 6 }}>{sensor.unit}</span>
          {readingCells}
        </div>
      )}
    </div>
  );
}

// ── Packet log ────────────────────────────────────────────────────────────────

function LogSection({ sat, now, expandedIdx, setExpandedIdx }) {
  return (
    <>
      <div style={{ padding: '8px 14px 4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 8, color: ACCENT, opacity: 0.7, letterSpacing: '0.15em' }}>PACKET LOG</div>
        <div style={{ fontSize: 8, color: TEXT_SECONDARY }}>{sat.log.length}</div>
      </div>
      <div className="nuwa-scroll" style={{ flex: 1, overflowY: 'auto', padding: '0 6px 8px', minHeight: 60 }}>
        {sat.log.length === 0 && (
          <div style={{ padding: '6px 8px', fontSize: 10, color: TEXT_DIM, textAlign: 'center' }}>no packets yet</div>
        )}
        {sat.log.map((entry, idx) => (
          <PacketLogRow
            key={`${entry.ts}-${idx}`}
            entry={entry}
            now={now}
            expanded={expandedIdx === idx}
            onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
          />
        ))}
      </div>
    </>
  );
}

function MinimapSection({ sat }) {
  return (
    <div style={{ padding: '6px 14px 12px', borderTop: PANEL_BORDER }}>
      <div style={{ fontSize: 8, color: ACCENT, opacity: 0.7, marginBottom: 5, letterSpacing: '0.15em' }}>GROUND TRACK · 90 MIN</div>
      <Minimap sat={sat} />
    </div>
  );
}
