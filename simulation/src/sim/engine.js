import { SAT_CONFIG, GROUND_STATIONS } from '../constants/index.js';
import { ProtocolService } from './ProtocolService.js';
import { periodSeconds, altitudeKm, geodeticAt, altitudeDEGR } from './keplerian.js';
import { buildSensors } from './sensorConfig.js';
import { tickSensors } from './sensorSim.js';

const DEGR_HISTORY_LEN = 60;

function dist3(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function createSat(cfg) {
  return {
    id: cfg.id,
    name: cfg.name,
    role: cfg.role,
    state: 'IDLE',
    energy: 60 + Math.floor(Math.random() * 40),
    uptime_s: 30000 + Math.random() * 50000,
    orbit_error_m: 50 + Math.random() * 200,
    sensors: buildSensors(cfg.id),
    seq: 0,
    log: [],
    elements: {
      a: cfg.a_km,
      e: cfg.e,
      i: (cfg.i_deg  * Math.PI) / 180,
      raan: (cfg.raan_deg * Math.PI) / 180,
      argP: (cfg.argP_deg * Math.PI) / 180,
      M0: Math.random() * Math.PI * 2,
      epochSec: 0,
    },
    period_s: periodSeconds(cfg.a_km),
    altitude_km: altitudeKm(cfg.a_km),
    static_geo: !!cfg.static_geo,
    modelKm: cfg.modelKm,
    sample: cfg.sample,
    roleWeights: cfg.roleWeights,
    baseDegrBoost: cfg.baseDegrBoost || 0,
    degr_k: 1 + Math.random() * 2,
    degr_svd: 1 + Math.random() * 2,
    degr_age: 0,
    degr_orbit: 0,
    degr_alt: 0,
    degr: 0,
    activeScenario: null,
    pulseUntil: 0,
    currentPos: null,
    degrHistory: new Array(DEGR_HISTORY_LEN).fill(0),
    inSunlight: true,
    _pendingFault: null,
  };
}

export class SimulationEngine {
  constructor(simClock) {
    this.simClock = simClock;
    this.sats = SAT_CONFIG.map((cfg) => createSat(cfg));
    this.protocol = new ProtocolService(this, simClock);
    this.groundStations = GROUND_STATIONS.map((g) => ({ ...g, currentPos: null }));
    this._minutesElapsed = 0;
  }

  getSat(id) { return this.sats.find((s) => s.id === id); }

  findNearest(sat, count) {
    const others = this.sats.filter((s) => s.id !== sat.id);
    if (sat.currentPos && others.every((s) => s.currentPos)) {
      others.sort((a, b) => dist3(sat.currentPos, a.currentPos) - dist3(sat.currentPos, b.currentPos));
    }
    return others.slice(0, count);
  }

  geodetic(sat) {
    if (sat.static_geo) {
      const cfg = SAT_CONFIG.find((c) => c.id === sat.id);
      const lon = cfg.raan_deg > 180 ? cfg.raan_deg - 360 : cfg.raan_deg;
      return { lat_deg: 0, lon_deg: lon, alt_km: altitudeKm(cfg.a_km) };
    }
    return geodeticAt(sat.elements, this.simClock.currentTime);
  }

  weightedPick(role, sats = this.sats) {
    let total = 0;
    const weights = sats.map((s) => { const w = (s.roleWeights && s.roleWeights[role]) ?? 1; total += w; return w; });
    if (total <= 0) return null;
    let r = Math.random() * total;
    for (let i = 0; i < sats.length; i++) { r -= weights[i]; if (r <= 0) return sats[i]; }
    return sats[sats.length - 1];
  }

  recordMinute() {
    this._minutesElapsed++;
    this.sats.forEach((sat) => {
      sat.degrHistory.push(sat.degr);
      if (sat.degrHistory.length > DEGR_HISTORY_LEN) sat.degrHistory.shift();
    });
    this.protocol.rolloverMinute();
  }

  tick() {
    const timeSec = this.simClock.currentTime;
    this.sats.forEach((sat) => {
      this._updateSat(sat);
      if (sat.telemetrySource !== 'segments.csv') {
        tickSensors(sat, timeSec);
        // Consume pending sensor fault — trigger correction if satellite is idle
        if (sat._pendingFault && sat.state === 'IDLE') {
          sat._pendingFault = null;
          this.protocol.triggerCorrection(sat.id);
        } else if (sat._pendingFault) {
          sat._pendingFault = null;
        }
      }
    });
  }

  _updateSat(sat) {
    sat.uptime_s += 2;
    sat.degr_k   = Math.max(0, Math.min(5, sat.degr_k   + (Math.random() - 0.5) * 0.5));
    sat.degr_svd = Math.max(0, Math.min(5, sat.degr_svd + (Math.random() - 0.5) * 0.4));
    sat.degr_age = Math.min(3, Math.floor(sat.uptime_s / 30000));
    sat.degr_orbit = Math.max(0, Math.min(2, Math.floor(sat.orbit_error_m / 120)));

    let altKm = sat.altitude_km;
    if (!sat.static_geo) {
      const geo = geodeticAt(sat.elements, this.simClock.currentTime);
      if (geo) altKm = geo.alt_km;
    }
    sat.degr_alt = altitudeDEGR(altKm);

    sat.degr = Math.max(0, Math.min(15, Math.round(
      sat.baseDegrBoost + sat.degr_k + sat.degr_svd + sat.degr_age + sat.degr_orbit + sat.degr_alt
    )));
    sat.orbit_error_m = Math.max(20, sat.orbit_error_m + (Math.random() - 0.5) * 10);

    if (sat.state === 'IDLE') {
      const drain = sat.inSunlight ? 0.05 : 0.25;
      sat.energy = Math.max(0, sat.energy - drain);
      if (sat.inSunlight && Math.random() < 0.08) sat.energy = Math.min(100, sat.energy + 4);
    }
  }
}
