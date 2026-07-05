import { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { POLL_INTERVAL_MS } from '../constants/index.js';

function snapshotSensors(sensors) {
  if (!sensors || sensors.length === 0) return [];
  return sensors.map((s) => ({
    id:              s.id,
    type:            s.type,
    label:           s.label,
    unit:            s.unit,
    axes:            s.axes,
    active:          s.active,
    status:          s.status,
    nominal_range:   s.nominal_range,
    fault_threshold: s.fault_threshold,
    // last_reading copied by value (shallow) — safe because tick always replaces the object
    last_reading: s.last_reading ? { ...s.last_reading } : null,
    // history is NOT included in the snapshot; the graph panel reads it live via engine ref
  }));
}

function snapshot(sat, engine) {
  const geo = engine.geodetic(sat);
  return {
    id: sat.id,
    name: sat.name,
    role: sat.role,
    state: sat.state,
    degr: sat.degr,
    energy: sat.energy,
    uptime_s: sat.uptime_s,
    orbit_error_m: sat.orbit_error_m,
    sensors: snapshotSensors(sat.sensors),
    seq: sat.seq,
    degr_k: sat.degr_k,
    degr_svd: sat.degr_svd,
    degr_age: sat.degr_age,
    degr_orbit: sat.degr_orbit,
    degr_alt: sat.degr_alt,
    _rho: sat._rho,
    _windowFull: sat._windowFull,
    activeScenario: sat.activeScenario,
    log: sat.log.slice(0, 50),
    period_s: sat.period_s,
    altitude_km: sat.altitude_km,
    static_geo: !!sat.static_geo,
    elements: sat.elements,
    inSunlight: sat.inSunlight,
    degrHistory: sat.degrHistory ? sat.degrHistory.slice() : [],
    lat_deg: geo ? geo.lat_deg : null,
    lon_deg: geo ? geo.lon_deg : null,
    alt_km: geo ? geo.alt_km : sat.altitude_km,
  };
}

export function useSatellite(satId, intervalMs = POLL_INTERVAL_MS) {
  const { refs, ready } = useSISP();
  const [snap, setSnap] = useState(null);

  useEffect(() => {
    if (!ready) return;
    if (satId == null) {
      setSnap(null);
      return;
    }
    const engine = refs.current.engine;
    const update = () => {
      const sat = engine.getSat(satId);
      if (sat) setSnap(snapshot(sat, engine));
    };
    update();
    const id = setInterval(update, intervalMs);
    return () => clearInterval(id);
  }, [satId, ready, refs, intervalMs]);

  return snap;
}
