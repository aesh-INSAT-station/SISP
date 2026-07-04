import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import {
  PANEL_BORDER, ACCENT, TEXT_SECONDARY, TEXT_DIM, FONT_MONO,
} from '../constants/index.js';
import { DraggablePanel } from './DraggablePanel.jsx';
import { hex, fmtUptime } from '../utils/format.js';

// ── Constants ─────────────────────────────────────────────────────────────────

const AXIS_COLORS = ['#00b9ff', '#00ff88', '#f5c518', '#ff3d5a', '#a78bfa', '#22d3ee'];
const GRAPH_W = 280;
const GRAPH_H = 200;
const ML = 42;
const MR = 6;
const MT = 8;
const MB = 22;
const PW = GRAPH_W - ML - MR;
const PH = GRAPH_H - MT - MB;
const GRID_LINES = 4;

// ── Canvas drawing ────────────────────────────────────────────────────────────

function fmtAxisVal(v) {
  if (!isFinite(v)) return '—';
  if (Math.abs(v) >= 10000) return (v / 1000).toFixed(0) + 'k';
  if (Math.abs(v) >= 1000)  return (v / 1000).toFixed(1) + 'k';
  if (Math.abs(v) > 0 && Math.abs(v) < 0.001) return v.toExponential(2);
  if (Math.abs(v) >= 10)    return v.toFixed(1);
  return v.toFixed(3);
}

function fmtSigned(v) {
  if (v == null || !isFinite(v)) return '—';
  const s = Math.abs(v) > 0 && Math.abs(v) < 0.001 ? v.toExponential(3) : v.toFixed(4);
  return v >= 0 ? `+${s}` : s;
}

function isScalar(sensor) { return sensor.axes.length === 1; }

function fmtSourceTime(reading, fallback) {
  if (reading?.source_timestamp) return reading.source_timestamp.slice(11, 19);
  if (Number.isFinite(reading?.ts_ms) && reading.ts_ms > 1e12) {
    return new Date(reading.ts_ms).toISOString().slice(11, 19);
  }
  return fallback;
}

function drawGraph(canvas, sensor, axisVis) {
  const ctx = canvas.getContext('2d');
  const history = sensor.history;

  ctx.fillStyle = '#080d14';
  ctx.fillRect(0, 0, GRAPH_W, GRAPH_H);

  if (history.length < 2) {
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    ctx.font = `9px ${FONT_MONO}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Collecting data…', GRAPH_W / 2, GRAPH_H / 2);
    return;
  }

  // Y range with 10% padding around nominal_range
  const [nomLo, nomHi] = sensor.nominal_range;
  const span   = nomHi - nomLo || 1;
  const yPad   = span * 0.10;
  const yLo    = nomLo - yPad;
  const yHi    = nomHi + yPad;
  const yRange = yHi - yLo || 1;

  const toX = (i) => ML + (i / Math.max(1, history.length - 1)) * PW;
  const toY = (v)  => MT + PH - Math.max(0, Math.min(PH, ((v - yLo) / yRange) * PH));

  // Grid + y-axis labels
  ctx.font         = `9px ${FONT_MONO}`;
  ctx.textAlign    = 'right';
  ctx.textBaseline = 'middle';
  for (let g = 0; g <= GRID_LINES; g++) {
    const t   = g / GRID_LINES;
    const yPx = MT + t * PH;
    const val = yHi - t * yRange;
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth   = 1;
    ctx.beginPath(); ctx.moveTo(ML, yPx); ctx.lineTo(ML + PW, yPx); ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.fillText(fmtAxisVal(val), ML - 4, yPx);
  }

  // Nominal range band
  const bandY1 = toY(nomHi);
  const bandY2 = toY(nomLo);
  ctx.fillStyle = 'rgba(0,185,255,0.03)';
  ctx.fillRect(ML, bandY1, PW, bandY2 - bandY1);

  // Fault threshold lines
  ctx.save();
  ctx.setLineDash([3, 3]);
  ctx.strokeStyle = 'rgba(255,61,90,0.55)';
  ctx.lineWidth = 1;
  const ft = sensor.fault_threshold;
  if (sensor.type === 'THERMAL' || sensor.type === 'STAR_TRACKER' || sensor.type === 'SUN_SENSOR') {
    const fy = toY(ft);
    if (fy >= MT && fy <= MT + PH) { ctx.beginPath(); ctx.moveTo(ML, fy); ctx.lineTo(ML + PW, fy); ctx.stroke(); }
  } else {
    const fyP = toY(ft);
    const fyN = toY(-ft);
    if (fyP >= MT && fyP <= MT + PH) { ctx.beginPath(); ctx.moveTo(ML, fyP); ctx.lineTo(ML + PW, fyP); ctx.stroke(); }
    if (fyN >= MT && fyN <= MT + PH) { ctx.beginPath(); ctx.moveTo(ML, fyN); ctx.lineTo(ML + PW, fyN); ctx.stroke(); }
  }
  ctx.restore();

  // Data series
  if (isScalar(sensor)) {
    const axis  = sensor.axes[0];
    ctx.save();
    // Filled area
    ctx.beginPath();
    history.forEach((r, i) => {
      const x = toX(i);
      const y = toY(r[axis] ?? nomLo);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(toX(history.length - 1), MT + PH);
    ctx.lineTo(ML, MT + PH);
    ctx.closePath();
    ctx.fillStyle = 'rgba(0,185,255,0.12)';
    ctx.fill();
    // Line
    ctx.beginPath();
    history.forEach((r, i) => {
      const x = toX(i);
      const y = toY(r[axis] ?? nomLo);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = AXIS_COLORS[0];
    ctx.lineWidth   = 1.5;
    ctx.stroke();
    ctx.restore();
  } else {
    sensor.axes.forEach((axis, aIdx) => {
      if (axisVis[axis] === false) return;
      ctx.save();
      ctx.beginPath();
      let first = true;
      history.forEach((r, i) => {
        if (r[axis] == null) return;
        const x = toX(i);
        const y = toY(r[axis]);
        if (first) { ctx.moveTo(x, y); first = false; }
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = AXIS_COLORS[aIdx % AXIS_COLORS.length];
      ctx.lineWidth   = 1.5;
      ctx.stroke();
      ctx.restore();
    });
  }

  // "Now" vertical marker
  const nowX = toX(history.length - 1);
  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.lineWidth   = 1;
  ctx.setLineDash([2, 3]);
  ctx.beginPath(); ctx.moveTo(nowX, MT); ctx.lineTo(nowX, MT + PH); ctx.stroke();
  ctx.restore();

  // X-axis relative timestamp labels
  const labelEvery = Math.max(1, Math.floor(history.length / 4));
  ctx.font         = `8px ${FONT_MONO}`;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle    = 'rgba(255,255,255,0.28)';
  for (let i = 0; i < history.length; i += labelEvery) {
    const delta = (i - (history.length - 1)) * 2;   // 2 sim-s per tick
    ctx.fillText(fmtSourceTime(history[i], `${delta}s`), toX(i), MT + PH + 4);
  }
  ctx.fillText(history[history.length - 1]?.source_timestamp ? 'real' : 'now', nowX, MT + PH + 4);
}

// ── DOM update helpers (RAF-driven, no React re-renders) ──────────────────────

function computeStats(sensor) {
  const last20  = sensor.history.slice(-20);
  const allHist = sensor.history;
  if (last20.length === 0) return {};
  let worstAbs = 0, worstMean = 0, worstStd = 0;
  let gMin = Infinity, gMax = -Infinity;
  sensor.axes.forEach((axis) => {
    const recent = last20.map((r) => r[axis] ?? 0).filter(isFinite);
    if (!recent.length) return;
    const mean = recent.reduce((a, b) => a + b, 0) / recent.length;
    const std  = Math.sqrt(recent.reduce((a, b) => a + (b - mean) ** 2, 0) / recent.length);
    if (Math.abs(mean) > worstAbs) { worstAbs = Math.abs(mean); worstMean = mean; }
    if (std > worstStd) worstStd = std;
    const all = allHist.map((r) => r[axis] ?? 0).filter(isFinite);
    if (all.length) { gMin = Math.min(gMin, ...all); gMax = Math.max(gMax, ...all); }
  });
  return { mean: worstMean, std: worstStd, min: gMin, max: gMax };
}

function updateStatsEl(el, sensor) {
  if (!el) return;
  const { mean, std, min, max } = computeStats(sensor);
  const f = (v) => (v == null || !isFinite(v)) ? '—' : fmtAxisVal(v);
  el.textContent = `MEAN ${f(mean)}   STD ${f(std)}   MIN ${f(min)}   MAX ${f(max)}`;
}

function updateReadingEl(el, sensor) {
  if (!el) return;
  const r = sensor.last_reading;
  if (!r) { el.textContent = 'no data'; return; }
  const lines = sensor.axes.map(
    (axis) => `${axis.padEnd(8)} ${fmtSigned(r[axis] ?? null)} ${sensor.unit}`
  ).join('\n');
  const timestamp = r.source_timestamp || (r.ts_ms ? fmtUptime(r.ts_ms / 1000) : '—');
  const segment = r.segment != null ? `\n${'segment'.padEnd(8)} ${r.segment}` : '';
  const anomaly = r.anomaly != null ? `\n${'anomaly'.padEnd(8)} ${r.anomaly ? 'yes' : 'no'}` : '';
  el.textContent = `${lines}\n${'ts'.padEnd(8)} ${timestamp}${segment}${anomaly}`;
}

// ── GraphBody ─────────────────────────────────────────────────────────────────

function GraphBody({ satelliteId, sensorId, refs, onClose }) {
  const canvasRef  = useRef(null);
  const statsRef   = useRef(null);
  const readingRef = useRef(null);
  const axisVisRef = useRef({});

  // Axis visibility: React state for legend re-render on toggle
  const [axisVis, setAxisVis]     = useState({});
  const [anomalies, setAnomalies] = useState([]);

  // ── Compute meta synchronously ─────────────────────────────────────────────
  // Safe: this component only renders inside SensorGraphPanel which guards on `ready`.
  // Reading refs.current during render is intentional (it's always up-to-date).
  const engine = refs?.current?.engine;
  const _sat   = engine?.getSat(satelliteId);
  const _snsr  = _sat?.sensors?.find((s) => s.id === sensorId) || null;
  const meta   = _snsr ? {
    satName: _sat.name,
    label:   _snsr.label,
    type:    _snsr.type,
    unit:    _snsr.unit,
    axes:    _snsr.axes,
    scalar:  _snsr.axes.length === 1,
  } : null;

  // Sync axisVis state → ref (RAF reads ref to avoid stale closures)
  useEffect(() => { axisVisRef.current = axisVis; }, [axisVis]);

  // Initialise axis visibility once on mount
  useEffect(() => {
    const s = refs?.current?.engine?.getSat(satelliteId)?.sensors?.find((x) => x.id === sensorId);
    if (!s) return;
    const vis = {};
    s.axes.forEach((a) => { vis[a] = true; });
    setAxisVis(vis);
    setAnomalies([...(s._anomalies || [])]);
  }, [satelliteId, sensorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // getSensor: resolves live sensor object each call — no stale closure risk
  const getSensor = useCallback(() => {
    return refs?.current?.engine?.getSat(satelliteId)?.sensors?.find((s) => s.id === sensorId) || null;
  }, [satelliteId, sensorId, refs]);

  // RAF loop — all visual updates via direct DOM writes
  useEffect(() => {
    let animId;
    const frame = () => {
      const canvas = canvasRef.current;
      const sensor = getSensor();
      if (canvas && sensor) {
        drawGraph(canvas, sensor, axisVisRef.current);
        updateStatsEl(statsRef.current, sensor);
        updateReadingEl(readingRef.current, sensor);
      }
      animId = requestAnimationFrame(frame);
    };
    animId = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(animId);
  }, [getSensor]);

  // Slower poll for anomaly list (only triggers React re-render when count changes)
  useEffect(() => {
    const timer = setInterval(() => {
      const sensor = getSensor();
      if (!sensor) return;
      setAnomalies((prev) => {
        const cur = sensor._anomalies || [];
        return prev.length !== cur.length ? [...cur] : prev;
      });
    }, 500);
    return () => clearInterval(timer);
  }, [getSensor]);

  const toggleAxis = (axis) => {
    setAxisVis((prev) => ({ ...prev, [axis]: !prev[axis] }));
  };

  if (!meta) return (
    <div style={{ padding: 16, color: TEXT_DIM, fontSize: 10 }}>Sensor not found.</div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', color: '#94a3b8', fontSize: 11 }}>

      {/* ── Panel header ──────────────────────────────────────────────────── */}
      <div style={{ padding: '10px 14px 8px', borderBottom: PANEL_BORDER, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 12, color: '#d4eeff', fontFamily: FONT_MONO, letterSpacing: '0.07em', fontWeight: 600 }}>
              {meta.satName} · {meta.label}
            </div>
            <div style={{ marginTop: 3, fontSize: 8, color: TEXT_SECONDARY, letterSpacing: '0.12em' }}>
              {meta.type} · {meta.unit}
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

      {/* ── Scrollable body ────────────────────────────────────────────────── */}
      <div className="nuwa-scroll" style={{ flex: 1, overflowY: 'auto', padding: '10px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* Graph canvas */}
        <div>
          <canvas
            ref={canvasRef}
            width={GRAPH_W}
            height={GRAPH_H}
            style={{ display: 'block', borderRadius: 4, border: '1px solid rgba(255,255,255,0.06)' }}
          />
          {/* Axis legend */}
          {!meta.scalar && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px', marginTop: 6 }}>
              {meta.axes.map((axis, aIdx) => {
                const color   = AXIS_COLORS[aIdx % AXIS_COLORS.length];
                const visible = axisVis[axis] !== false;
                return (
                  <button
                    key={axis}
                    onClick={() => toggleAxis(axis)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      padding: '1px 4px', opacity: visible ? 1 : 0.35,
                    }}
                  >
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                    <span style={{ fontSize: 8, color: TEXT_SECONDARY, fontFamily: FONT_MONO }}>{axis}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Stats row */}
        <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.22)', borderRadius: 4, border: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ fontSize: 7, color: ACCENT, opacity: 0.65, letterSpacing: '0.14em', marginBottom: 3 }}>
            STATISTICS · LAST 20 READINGS
          </div>
          <div
            ref={statsRef}
            style={{ fontSize: 8, color: TEXT_SECONDARY, fontFamily: FONT_MONO, letterSpacing: '0.05em', whiteSpace: 'pre' }}
          />
        </div>

        {/* Anomaly log */}
        <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.22)', borderRadius: 4, border: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ fontSize: 7, color: ACCENT, opacity: 0.65, letterSpacing: '0.14em', marginBottom: 4 }}>ANOMALY LOG</div>
          {anomalies.length === 0 ? (
            <div style={{ fontSize: 8, color: TEXT_DIM, fontStyle: 'italic' }}>No anomalies recorded</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 110, overflowY: 'auto' }}>
              {anomalies.map((a, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, fontSize: 8, fontFamily: FONT_MONO }}>
                  <span style={{ color: TEXT_DIM, flexShrink: 0 }}>{fmtUptime((a.ts_ms || 0) / 1000)}</span>
                  <span style={{ color: '#ff3d5a', flexShrink: 0 }}>{a.axis}</span>
                  <span style={{ color: TEXT_SECONDARY }}>{fmtSigned(a.value)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Live reading */}
        <div style={{ padding: '6px 8px', background: 'rgba(0,0,0,0.22)', borderRadius: 4, border: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ fontSize: 7, color: ACCENT, opacity: 0.65, letterSpacing: '0.14em', marginBottom: 4 }}>LIVE READING</div>
          <pre
            ref={readingRef}
            style={{
              margin: 0, fontSize: 10, fontFamily: FONT_MONO,
              color: '#d4eeff', letterSpacing: '0.04em', lineHeight: 1.7, whiteSpace: 'pre',
            }}
          />
        </div>

      </div>
    </div>
  );
}

// ── Public export ─────────────────────────────────────────────────────────────

export function SensorGraphPanel() {
  const { selectedSensor, setSelectedSensor, refs, ready } = useSISP();

  if (!selectedSensor || !ready) return null;

  const { satelliteId, sensorId } = selectedSensor;

  const panelRect = {
    left: Math.max(16, window.innerWidth - 332 - 8 - 320),
    top: 74,
    width: 320,
    height: Math.min(660, window.innerHeight - 148),
  };

  return (
    <DraggablePanel
      id="sensor-graph"
      title="Sensor Data"
      defaultRect={panelRect}
      minWidth={300}
      minHeight={420}
      bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}
    >
      <GraphBody
        key={`${satelliteId}-${sensorId}`}
        satelliteId={satelliteId}
        sensorId={sensorId}
        refs={refs}
        onClose={() => setSelectedSensor(null)}
      />
    </DraggablePanel>
  );
}
