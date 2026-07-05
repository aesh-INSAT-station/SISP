import { SAT_CONFIG, GROUND_STATIONS } from '../constants/index.js';
import { ProtocolService } from './ProtocolService.js';
import { periodSeconds, altitudeKm, geodeticAt, altitudeDEGR } from './keplerian.js';
import { buildSensors } from './sensorConfig.js';
import { tickSensors, tickOpsatSensor } from './sensorSim.js';
import { HankelSVDDetector } from './HankelSVDDetector.js';
import { losToStation } from '../utils/los.js';

const DEGR_HISTORY_LEN = 60;

function dist3(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function createSat(cfg) {
  const sat = {
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
    degr_svd: 0,
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
    _relayPending: false,
    _borrowPending: false,
    _hadLOS: null, // null = first tick, skip transition detection
    _ticksSinceScenario: 0,
    _correctionCooldown: 0,
    _correctionState: null,
    telemetrySource: cfg.telemetrySource,
    opsatChannel: cfg.opsatChannel,
    opsatDetectorOpts: cfg.opsatDetectorOpts,
    opsatNoise: cfg.opsatNoise,
  };
  return sat;
}

export class SimulationEngine {
  constructor(simClock) {
    this.simClock = simClock;
    this.sats = SAT_CONFIG.map((cfg) => createSat(cfg));
    this.protocol = new ProtocolService(this, simClock);
    this.groundStations = GROUND_STATIONS.map((g) => ({ ...g, currentPos: null }));
    this._minutesElapsed = 0;
    this._opsatData = null;
    this._opsatCursors = {};
    this._opsatReady = false;
    this._loadOpsatData();
    // Periodic heartbeat every 5 sim-minutes (not 30s — was too spammy)
    this.simClock.setInterval(300, () => {
      this.protocol.triggerHeartbeat();
    });
  }

  _repeatIndex(index, length) {
    if (length <= 0) return 0;
    return index % length;
  }

  async _loadOpsatData() {
    try {
      const res = await fetch('/segments.json');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this._opsatData = await res.json();
      this.sats.forEach((sat) => {
        if (sat.telemetrySource === 'segments.csv' && sat.opsatChannel) {
          const chData = this._opsatData.channels[sat.opsatChannel];
          if (chData) {
            this._opsatCursors[sat.id] = {
              channel: sat.opsatChannel,
              channelData: chData,
              index: 0,
              detector: new HankelSVDDetector(sat.opsatDetectorOpts || {}),
            };
          }
        }
      });
      this._opsatReady = true;
      console.log(`OPS-SAT data loaded: ${Object.keys(this._opsatCursors).length} channels`);
    } catch (e) {
      console.warn('OPS-SAT data not available:', e.message);
    }
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
      if (sat.telemetrySource === 'segments.csv') {
        this._tickOpsat(sat, timeSec);
      } else {
        tickSensors(sat, timeSec);
      }
      this._processSatScenario(sat);
    });
  }

  _processSatScenario(sat) {
    if (sat.state !== 'IDLE') {
      sat._pendingFault = null;
      sat._ticksSinceScenario = 0;
      return;
    }
    sat._ticksSinceScenario++;
    if (sat._correctionCooldown > 0) sat._correctionCooldown--;

    // 1. Hankel-SVD or sensor fault → CORRECTION (only when cooldown is 0)
    if (sat._pendingFault && sat._correctionCooldown === 0) {
      sat._pendingFault = null;
      sat._correctionCooldown = 80; // ~160 sim-sec gap so relay/borrow can fire
      this.protocol.triggerCorrection(sat.id);
      return;
    }
    // Clear fault if on cooldown (will re-arm on next tick)
    sat._pendingFault = null;

    // 2. GS_LOST → RELAY (once per dark pass), GS_VISIBLE → BORROW
    if (sat.currentPos) {
      // First tick: seed _hadLOS without triggering
      if (sat._hadLOS === null) {
        sat._hadLOS = this.groundStations.some((gs) => losToStation(sat.currentPos, gs));
      } else {
        const hasLOS = this.groundStations.some((gs) => losToStation(sat.currentPos, gs));
        const lostLOS = sat._hadLOS && !hasLOS;
        const gainedLOS = !sat._hadLOS && hasLOS;
        sat._hadLOS = hasLOS;

        // GS_LOST → relay (fire every LOS loss, no probability gate)
        if (lostLOS && !sat._relayPending) {
          sat._relayPending = true;
          this.protocol.triggerRelay(sat.id);
          return;
        }
        // GS_VISIBLE → borrow (fire every LOS gain)
        if (gainedLOS) {
          this.protocol.triggerBorrow(sat.id);
          return;
        }
        // Reset relay flag when LOS is regained
        if (hasLOS) sat._relayPending = false;
      }
    }

    // 4. Random HEARTBEAT pulse from busy satellites (rare, every ~330 ticks)
    if (sat.role !== 'NAV_REFERENCE' && Math.random() < 0.001) {
      this.protocol.triggerHeartbeat(sat.id);
    }
  }

  _tickOpsat(sat, timeSec) {
    const cursor = this._opsatCursors[sat.id];
    if (!cursor || !this._opsatReady) return;
    // Consume 1 sample per sim-second (tick fires every 2 sim-seconds → 2 samples)
    // Wrap index when data exhausted (infinite repeat)
    const totalLen = cursor.channelData.values.length;
    const samplesPerTick = Math.min(2, totalLen);
    for (let i = 0; i < samplesPerTick; i++) {
      if (totalLen > 0) cursor.index = this._repeatIndex(cursor.index, totalLen);
      const result = tickOpsatSensor(sat, timeSec, cursor);
      if (!result) break;
      if (result.value !== undefined) sat._lastTelemetryValue = result.value;
    }
  }

  _updateSat(sat) {
    sat.uptime_s += 2;
    sat.degr_k   = Math.max(0, Math.min(5, sat.degr_k   + (Math.random() - 0.5) * 0.5));
    if (!sat.telemetrySource) {
      sat.degr_svd = Math.max(0, Math.min(5, sat.degr_svd + (Math.random() - 0.5) * 0.4));
    }
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

    // ── Energy & failure simulation ──────────────────────────────────────────
    if (sat.state === 'IDLE') {
      // Normal drain
      if (sat.inSunlight) {
        sat.energy -= 0.05;
        // 2% chance solar panel fails to charge this tick
        if (Math.random() < 0.02) { /* charge skipped */ }
        else if (Math.random() < 0.08) sat.energy += 4;
      } else {
        sat.energy -= 0.25;
      }

      // 0.2% chance of energy spike (solar panel misalignment / heater stuck on)
      if (Math.random() < 0.002) {
        sat.energy -= 10 + Math.random() * 15; // 10–25% loss
      }

      // No random critical failure — only triggered by energy depletion
      // (deterministic: run out of juice → fail)

      // Energy at zero → die
      if (sat.energy <= 0) {
        sat.energy = 0;
        this.protocol.triggerFailure(sat.id);
      }

      sat.energy = Math.max(0, Math.min(100, sat.energy));
    }

    // Recovery from CRITICAL_FAIL: revive after ~60 sim-seconds with 10% energy
    if (sat.state === 'CRITICAL_FAIL' && sat.uptime_s % 60 < 2) {
      sat.energy = 10;
      sat.state = 'IDLE';
      sat.activeScenario = null;
      this.protocol.triggerHeartbeat(sat.id);  // announce recovery to neighbours
    }
  }
}
