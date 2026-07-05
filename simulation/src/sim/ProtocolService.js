import { GROUND_ID, SERVICE_FAMILY } from '../constants/index.js';

const PACKET_DURATION_S = 1.2;
const MAX_IN_FLIGHT = 20;
const GLOBAL_LOG_CAP = 500;
const PKT_RATE_BUCKETS = 10;

// Sim epoch as UTC ms — used so existing format/relTime utilities stay ms-based.
const SIM_EPOCH_MS = 1735689600000; // Date.UTC(2025, 0, 1)

// ── Correction algorithms ──────────────────────────────────────────────────────

function degrWeight(degr) { return Math.max(0.05, 1 - degr / 15); }

// Weighted Median Filter: sort readings by value, accumulate weights,
// return value where cumulative weight first reaches 50% of total.
function weightedMedian(readings) {
  if (readings.length === 0) return 0;
  const sorted = [...readings].sort((a, b) => a.value - b.value);
  const totalW = sorted.reduce((s, r) => s + r.weight, 0);
  let acc = 0;
  for (const r of sorted) {
    acc += r.weight;
    if (acc >= totalW * 0.5) return r.value;
  }
  return sorted[sorted.length - 1].value;
}

// 6-state constant-velocity Kalman filter (scalar per axis).
// State: [pos, vel]; measurement: pos; process noise q, measurement noise r.
function kalmanStep(mean, cov, z, q, r) {
  // Predict
  const pPred = cov + q;
  // Update
  const k = pPred / (pPred + r);
  const newMean = mean + k * (z - mean);
  const newCov = (1 - k) * pPred;
  return { mean: newMean, cov: newCov };
}

// Hybrid: Weighted Median pre-filter → Kalman temporal smoothing.
function hybridCorrect(readings, prevState) {
  const q = 0.02, r = 0.8;
  const med = weightedMedian(readings);
  const kf = prevState
    ? kalmanStep(prevState.mean, prevState.cov, med, q, r)
    : { mean: med, cov: 1.0 };
  return { corrected: kf.mean, state: kf };
}

// ── Sensor helpers ────────────────────────────────────────────────────────────

function primarySensor(sat) {
  if (!sat.sensors || sat.sensors.length === 0) return null;
  // Prefer a faulted/degraded sensor, fall back to first active sensor
  return (
    sat.sensors.find((s) => s.active && (s.status === 'FAULT' || s.status === 'DEGRADED')) ||
    sat.sensors.find((s) => s.active) ||
    sat.sensors[0]
  );
}

function sensorOfType(sat, type) {
  if (!sat.sensors) return null;
  return sat.sensors.find((s) => s.type === type && s.active) || null;
}

function hasOpticalSensor(sat) {
  return !!(sat.sensors && sat.sensors.some((s) => s.type === 'OPTICAL' && s.active));
}

// ── Payload factory ───────────────────────────────────────────────────────────

function payloadFor(service, sat) {
  switch (service) {
    case 'CORRECTION_REQ': {
      const s = primarySensor(sat);
      return { degr: sat.degr, sensor: s?.type ?? 'UNKNOWN', orbit_err_m: Math.round(sat.orbit_error_m) };
    }
    case 'CORRECTION_RSP': {
      // Responder reports its sensor reading (real OPS-SAT value if available)
      const teleVal = sat._lastTelemetryValue;
      const reading = teleVal != null
        ? teleVal
        : sat.orbit_error_m * (1 + (Math.random() - 0.5) * 0.1 * sat.degr);
      return {
        degr: sat.degr,
        k: sat.degr_k,
        svd: sat.degr_svd,
        reading_x: Math.round(reading * 10) / 10,
      };
    }
    case 'RELAY_REQ':        return { reason: 'ENERGY_LOW', energy_pct: Math.round(sat.energy) };
    case 'RELAY_ACCEPT':     return { capacity: 'OK', window_s: 12 };
    case 'RELAY_REJECT':     return { reason: 'BUSY' };
    case 'DOWNLINK_DATA':    return { length: 256, frag: '1/1' };
    case 'DOWNLINK_ACK':     return { ok: true };
    case 'BORROW_REQ':       return { want: 'OPTICAL_FRAME', priority: 1 };
    case 'BORROW_RSP': {
      const s = sensorOfType(sat, 'OPTICAL') || primarySensor(sat);
      // Responder returns its actual telemetry reading (real value if available)
      const teleVal = sat._lastTelemetryValue;
      const reading = teleVal != null
        ? teleVal
        : sat.orbit_error_m * (1 + (Math.random() - 0.5) * 0.1);
      return {
        sensor: s?.type ?? 'UNKNOWN',
        frame_id: Math.floor(Math.random() * 9999),
        degr: sat.degr,
        reading_x: Math.round(reading * 10) / 10,
      };
    }
    case 'HEARTBEAT':        return { uptime_s: Math.floor(sat.uptime_s), energy_pct: Math.round(sat.energy) };
    case 'FAILURE': {
      const s = sat.sensors?.find((x) => x.status === 'FAULT') || primarySensor(sat);
      return { code: 'CRITICAL', subsys: s?.type ?? 'UNKNOWN' };
    }
    case 'STATUS_BROADCAST': return { degr: sat.degr, energy_pct: Math.round(sat.energy), state: sat.state };
    default:                 return {};
  }
}

function randomFlags(service, fromSat) {
  const flags = [];
  if (service.startsWith('RELAY')) flags.push('R');
  if (fromSat && fromSat.role === 'RELAY_HUB') flags.push('O');
  if (Math.random() < 0.15) flags.push('T');
  if (Math.random() < 0.1)  flags.push('O');
  if (Math.random() < 0.2)  flags.push('P');
  return [...new Set(flags)];
}

export class ProtocolService {
  constructor(engine, simClock) {
    this.engine = engine;
    this.simClock = simClock;
    this.packets = [];
    this.queue = [];
    this.packetCount = 0;
    this.failureCount = 0;
    this.relayCount = 0;
    this.activeScenarios = 0;
    this._nextId = 1;

    this.globalLog = [];
    this._globalSeq = 1;

    this._currentBucket = { total: 0, errors: 0 };
    this.packetBuckets = Array.from({ length: PKT_RATE_BUCKETS }, () => ({ total: 0, errors: 0 }));

    // keyed "minId:maxId" → simSec of last failure
    this.linkFailures = new Map();

    this._txListeners = new Set();
  }

  onTransmit(fn) {
    this._txListeners.add(fn);
    return () => this._txListeners.delete(fn);
  }

  sendPacket(fromSat, toSat, service, onArrive) {
    const pkt = {
      id: this._nextId++,
      from: fromSat,
      to: toSat,
      service,
      startSimTime: null,
      duration_s: PACKET_DURATION_S,
      onArrive,
      seq: 0,
    };
    if (fromSat) {
      fromSat.seq++;
      pkt.seq = fromSat.seq;
      this._log(fromSat, 'TX', service, toSat ? toSat.id : GROUND_ID, pkt.seq);
    }
    this.packetCount++;
    this._currentBucket.total++;
    if (service === 'FAILURE' || service === 'RELAY_REJECT') this._currentBucket.errors++;
    if (service.startsWith('RELAY') || service.startsWith('DOWNLINK')) this.relayCount++;
    this._dispatchOrQueue(pkt);
    this._txListeners.forEach((fn) => { try { fn(pkt); } catch (e) { /* listener error */ } });
    return pkt;
  }

  _dispatchOrQueue(pkt) {
    if (this.packets.length >= MAX_IN_FLIGHT) { this.queue.push(pkt); return; }
    pkt.startSimTime = this.simClock.currentTime;
    this.packets.push(pkt);
  }

  onPacketArrive(pkt) {
    if (pkt.to) this._log(pkt.to, 'RX', pkt.service, pkt.from ? pkt.from.id : GROUND_ID, pkt.seq);
    if (pkt.onArrive) pkt.onArrive(pkt);
    if (this.queue.length > 0 && this.packets.length < MAX_IN_FLIGHT) {
      const next = this.queue.shift();
      next.startSimTime = this.simClock.currentTime;
      this.packets.push(next);
    }
  }

  request(fromSat, toSat, reqService, rspService, processingSeconds = 0.2) {
    return new Promise((resolve) => {
      this.sendPacket(fromSat, toSat, reqService, () => {
        this.simClock.scheduleAfter(processingSeconds, () => {
          this.sendPacket(toSat, fromSat, rspService, (rspPkt) => resolve(rspPkt));
        });
      });
    });
  }

  triggerCorrection(satId) {
    const sat = this.engine.getSat(satId);
    if (!sat || sat.state !== 'IDLE') return;
    sat.state = 'CORR_WAIT_RSP'; sat.activeScenario = 'CORR'; this.activeScenarios++;
    const navRefs = this.engine.sats.filter((s) => s.id !== sat.id && s.role === 'NAV_REFERENCE');
    const others  = this.engine.findNearest(sat, 4).filter((s) => s.role !== 'NAV_REFERENCE');
    const neighbors = [...navRefs, ...others].slice(0, 3);
    let received = 0;
    const readings = [];

    // The "true" value being measured: orbit error drives the simulated reading
    const trueVal = sat.orbit_error_m;

    neighbors.forEach((n, idx) => {
      this.simClock.scheduleAfter(idx * 0.12, () => {
        this.request(sat, n, 'CORRECTION_REQ', 'CORRECTION_RSP').then((rspPkt) => {
          // Extract sensor reading + weight from the responder's payload
          const p = rspPkt?.payload ?? {};
          const measurement = p.reading_x ?? trueVal;
          const weight = degrWeight(p.degr ?? n.degr);
          readings.push({ value: measurement, weight });
          received++;
          if (received === neighbors.length) {
            // Run the hybrid correction algorithm
            sat.state = 'CORR_COMPUTING';
            const result = hybridCorrect(readings, sat._correctionState);
            sat._correctionState = result.state;
            const corrected = Math.max(20, result.corrected);
            // Apply correction: reduce orbit error
            const improvement = Math.abs(sat.orbit_error_m - corrected);
            sat.orbit_error_m = Math.max(20, sat.orbit_error_m - improvement * 0.6);
            sat.degr_svd = Math.max(0, sat.degr_svd - 0.5);
            this._log(sat, 'TX', 'CORRECTION_DONE', 0, 0);
            this.simClock.scheduleAfter(0.8, () => { if (sat.state === 'CORR_COMPUTING') this._endScenario(sat); });
          }
        });
      });
    });
    this.simClock.scheduleAfter(6.5, () => { if (sat.activeScenario === 'CORR') this._endScenario(sat); });
  }

  triggerRelay(satId) {
    const sat = this.engine.getSat(satId);
    if (!sat || sat.state !== 'IDLE') return;
    sat.state = 'RELAY_WAIT_ACCEPT'; sat.activeScenario = 'RELAY'; this.activeScenarios++;
    const hub      = this.engine.sats.find((s) => s.role === 'RELAY_HUB' && s.state === 'IDLE');
    const neighbor = hub || this.engine.findNearest(sat, 1)[0];
    if (!neighbor) { this._endScenario(sat); return; }
    this.request(sat, neighbor, 'RELAY_REQ', 'RELAY_ACCEPT').then(() => {
      sat.state = 'RELAY_SENDING';
      this.sendPacket(sat, neighbor, 'DOWNLINK_DATA', () => {
        sat.state = 'RELAY_WAIT_ACK';
        this.sendPacket(neighbor, null, 'DOWNLINK_DATA', () => {
          this.simClock.scheduleAfter(0.2, () => {
            this.sendPacket(null, neighbor, 'DOWNLINK_ACK', () => {
              this.sendPacket(neighbor, sat, 'DOWNLINK_ACK', () => {
                sat.state = 'RELAY_DONE';
                sat.energy = Math.min(100, sat.energy + 20);
                this._endScenario(sat);
              });
            });
          });
        });
      });
    });
    this.simClock.scheduleAfter(9, () => { if (sat.activeScenario === 'RELAY') this._endScenario(sat); });
  }

  triggerHeartbeat(senderId) {
    let sender = senderId ? this.engine.getSat(senderId) : null;
    if (!sender) {
      const sats = this.engine.sats;
      sender = sats[0];
    }
    sender.pulseUntil = this.simClock.currentTime + 0.6;
    this.engine.sats.forEach((other) => {
      if (other.id !== sender.id) {
        this.sendPacket(sender, other, 'HEARTBEAT', () => {
          other.pulseUntil = this.simClock.currentTime + 0.5;
        });
      }
    });
  }

  triggerFailure(satId) {
    const sat = this.engine.getSat(satId);
    if (!sat || sat.state === 'CRITICAL_FAIL') return;
    // Only one satellite may be failed at a time (state machine constraint)
    if (this.engine.sats.some((s) => s.state === 'CRITICAL_FAIL')) return;
    sat.state = 'CRITICAL_FAIL'; sat.activeScenario = 'FAIL';
    this.activeScenarios++; this.failureCount++;
    this.engine.findNearest(sat, 3).forEach((other) => this.sendPacket(sat, other, 'FAILURE'));
    this.simClock.scheduleAfter(4, () => this._endScenario(sat));
  }

  triggerStatus(satId) {
    const sat = this.engine.getSat(satId);
    if (!sat) return;
    this.engine.findNearest(sat, 2).forEach((n) => this.sendPacket(sat, n, 'STATUS_BROADCAST'));
  }

  triggerBorrow(satId) {
    const sat = this.engine.getSat(satId);
    if (!sat || sat.state !== 'IDLE') return;
    // Find a peer with an active OPTICAL sensor
    const obs =
      this.engine.sats.find((s) => s.id !== sat.id && s.role === 'OBSERVATION' && s.state === 'IDLE') ||
      this.engine.sats.find((s) => s.id !== sat.id && hasOpticalSensor(s)       && s.state === 'IDLE');
    if (!obs) return;
    sat.state = 'BORROW_WAIT_ACCEPT'; sat.activeScenario = 'BORROW'; this.activeScenarios++;
    this.request(sat, obs, 'BORROW_REQ', 'BORROW_RSP').then(() => {
      sat.state = 'BORROW_RECEIVING';
      this.simClock.scheduleAfter(0.5, () => {
        sat.state = 'BORROW_DONE';
        this._endScenario(sat);
      });
    });
    this.simClock.scheduleAfter(7, () => { if (sat.activeScenario === 'BORROW') this._endScenario(sat); });
  }

  resetAll() {
    this.engine.sats.forEach((s) => { s.state = 'IDLE'; s.activeScenario = null; s.pulseUntil = 0; });
    this.activeScenarios = 0;
    this.packets = [];
    this.queue = [];
  }

  rolloverMinute() {
    this.packetBuckets.unshift(this._currentBucket);
    if (this.packetBuckets.length > PKT_RATE_BUCKETS) this.packetBuckets.pop();
    this._currentBucket = { total: 0, errors: 0 };
    const cutoff = this.simClock.currentTime - 5 * 60;
    for (const [k, ts] of this.linkFailures) {
      if (ts < cutoff) this.linkFailures.delete(k);
    }
  }

  markLinkFailure(idA, idB) {
    const k = idA < idB ? `${idA}:${idB}` : `${idB}:${idA}`;
    this.linkFailures.set(k, this.simClock.currentTime);
  }

  hasRecentLinkFailure(idA, idB) {
    const k = idA < idB ? `${idA}:${idB}` : `${idB}:${idA}`;
    return this.linkFailures.has(k);
  }

  _endScenario(sat) {
    sat.state = 'IDLE'; sat.activeScenario = null;
    this.activeScenarios = Math.max(0, this.activeScenarios - 1);
  }

  _simNowMs() {
    return SIM_EPOCH_MS + this.simClock.currentTime * 1000;
  }

  _log(sat, dir, service, peerId, seq) {
    const flags = randomFlags(service, sat);
    const entry = {
      ts: this._simNowMs(),
      dir, service,
      family: SERVICE_FAMILY[service] || 'OTHER',
      peer: peerId, seq, flags,
      src: dir === 'TX' ? sat.id : peerId,
      dst: dir === 'TX' ? peerId : sat.id,
      length: 16 + Math.floor(Math.random() * 48),
      checksum: '0x' + Math.floor(Math.random() * 0xffff).toString(16).toUpperCase().padStart(4, '0'),
      payload: payloadFor(service, sat),
    };
    sat.log.unshift(entry);
    if (sat.log.length > 50) sat.log.pop();
    if (dir === 'TX') {
      this.globalLog.unshift({ ...entry, gseq: this._globalSeq++ });
      if (this.globalLog.length > GLOBAL_LOG_CAP) this.globalLog.pop();
    }
  }
}
