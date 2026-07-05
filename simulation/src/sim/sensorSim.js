import { SENSOR_HISTORY_MAX } from './sensorConfig.js';

// ── Gaussian noise (Box-Muller) ───────────────────────────────────────────────
export function gaussian(sigma) {
  const u1 = Math.max(1e-10, Math.random());
  return sigma * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * Math.random());
}

// ── Noise injection for OPS-SAT telemetry ─────────────────────────────────────
function applyOpsatNoise(value, opts) {
  if (!opts) return value;
  let v = value;
  const { sigma = 0, burstProb = 0, burstAmplitude = 0, driftPerSample = 0, sampleIndex = 0 } = opts;
  if (sigma > 0) v += gaussian(sigma);
  if (burstProb > 0 && Math.random() < burstProb) {
    const sign = Math.random() < 0.5 ? 1 : -1;
    v += sign * Math.abs(gaussian(burstAmplitude));
  }
  if (driftPerSample > 0) v += driftPerSample * sampleIndex;
  return v;
}

// ── OPS-SAT sensor tick ───────────────────────────────────────────────────────
// Reads from pre-loaded OPS-SAT telemetry, feeds through Hankel-SVD detector.
// Returns { rho, isAnomalous, noisyValue, rawValue } or null if data exhausted.
export function tickOpsatSensor(sat, timeSec, cursor) {
  if (!cursor || !cursor.channelData) return null;
  if (cursor.index >= cursor.channelData.values.length) return null;

  const rawValue = cursor.channelData.values[cursor.index];
  const gtAnomaly = cursor.channelData.anomaly[cursor.index];
  cursor.index++;

  // Apply noise overlay if configured
  const opts = sat.opsatNoise || null;
  const noisyValue = opts ? applyOpsatNoise(rawValue, { ...opts, sampleIndex: cursor.index }) : rawValue;

  // Run Hankel-SVD detector
  const rho = cursor.detector.push(noisyValue);
  const isAnomalous = cursor.detector.isAnomalous;
  const windowFull = cursor.detector.windowFull;

  const reading = {
    value: noisyValue,
    raw: rawValue,
    rho,
    isAnomalous,
    gtAnomaly,
    ts_ms: timeSec * 1000,
  };

  // Update the satellite's first active sensor for UI display
  if (sat.sensors && sat.sensors.length > 0) {
    const sensor = sat.sensors[0];
    if (sensor) {
      // Map value to first axis so existing SensorRow displays it
      if (sensor.axes && sensor.axes.length > 0) {
        reading[sensor.axes[0]] = noisyValue;
      }
      reading._rho = rho;
      sensor.last_reading = reading;
      sensor.history.push(reading);
      if (sensor.history.length > 200) sensor.history.shift();
      sensor.status = isAnomalous ? 'FAULT' : 'NOMINAL';
      sensor._rhoHistory = cursor.detector.rhoHistory;
    }
  }

    // Expose rho for UI debugging
  sat._rho = rho;
  sat._windowFull = windowFull;

  // Update DEGR and trigger fault
  if (windowFull) {
    // Map ρ to degr_svd (0-5 scale): ρ up to 2× threshold → degr_svd 0-5
    const mapped = Math.min(5, (rho / cursor.detector.threshold) * 2);
    sat.degr_svd = Math.max(0, mapped);

    if (isAnomalous && sat.state === 'IDLE') {
      sat._pendingFault = 'svd-detector';
    }
  }

  return reading;
}

// ── Per-satellite mutable simulation state ────────────────────────────────────
// Stored as sat._simState so it survives across ticks without React involvement.
function getState(sat) {
  if (!sat._simState) {
    sat._simState = {
      gyroSpike:  { ticks: 0, axis: 0, sign: 1 },
      starQ:      { q0: 1, q1: 0, q2: 0, q3: 0 },
      thermTemp:  {},   // keyed by sensor.id
    };
  }
  return sat._simState;
}

// ── Individual sensor tick functions ─────────────────────────────────────────

function tickGyroscope(sensor, sat, timeSec, state) {
  // Sinusoidal base drift, different frequency per axis
  const x = 0.5 * Math.sin(2 * Math.PI * 0.001  * timeSec) + gaussian(0.02);
  const y = 0.5 * Math.sin(2 * Math.PI * 0.0013 * timeSec) + gaussian(0.02);
  const z = 0.5 * Math.sin(2 * Math.PI * 0.0007 * timeSec) + gaussian(0.02);

  // Spike injection during critical states
  const spike = state.gyroSpike;
  const isCritical = sat.state === 'CORR_COMPUTING' || sat.state === 'CRITICAL_FAIL';
  if (isCritical && spike.ticks === 0 && Math.random() < 0.4) {
    spike.ticks = 3;
    spike.axis  = Math.floor(Math.random() * 3);
    spike.sign  = Math.random() < 0.5 ? 1 : -1;
  }

  let sx = x, sy = y, sz = z;
  if (spike.ticks > 0) {
    const amp = 3 * spike.sign;
    if (spike.axis === 0) sx += amp;
    else if (spike.axis === 1) sy += amp;
    else sz += amp;
    spike.ticks--;
  }
  return { x: sx, y: sy, z: sz };
}

function tickMagnetometer(sensor, sat, timeSec) {
  const T   = sat.period_s || 5570;
  const phi = (2 * Math.PI * timeSec) / T;
  const B0  = 40000;
  const x = B0 * Math.sin(phi)             + gaussian(50);
  const y = B0 * Math.cos(phi)             + gaussian(50);
  let   z = B0 * 0.3 * Math.sin(phi * 2)  + gaussian(50);

  // Van Allen inner belt (1 000–6 000 km altitude) offset
  const alt = sat.altitude_km || 0;
  if (alt >= 1000 && alt <= 6000) z += 5000;

  return { x, y, z };
}

function tickStarTracker(sensor, sat, timeSec, state) {
  const q = state.starQ;
  // Drift rate doubles during slew manoeuvre (RELAY_ACTIVE maps to spec's RELAY_SENDING)
  const rate = sat.state === 'RELAY_ACTIVE' ? 0.002 : 0.001;
  q.q0 += gaussian(rate);
  q.q1 += gaussian(rate);
  q.q2 += gaussian(rate);
  q.q3 += gaussian(rate);
  // Normalise
  const mag = Math.sqrt(q.q0 ** 2 + q.q1 ** 2 + q.q2 ** 2 + q.q3 ** 2);
  if (mag > 0) { q.q0 /= mag; q.q1 /= mag; q.q2 /= mag; q.q3 /= mag; }
  return { q0: q.q0, q1: q.q1, q2: q.q2, q3: q.q3 };
}

function tickSunSensor(sensor, sat, timeSec) {
  // All faces read 0 during eclipse
  if (!sat.inSunlight) {
    return { face0: 0, face1: 0, face2: 0, face3: 0, face4: 0, face5: 0 };
  }
  const T   = sat.period_s || 5570;
  const phi = (2 * Math.PI * timeSec) / T;
  // Simplified rotating sun vector
  const sun    = [Math.cos(phi), Math.sin(phi), 0.2];
  const sunMag = Math.sqrt(sun[0] ** 2 + sun[1] ** 2 + sun[2] ** 2);
  // ±X, ±Y, ±Z face normals
  const normals = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
  const vals = normals.map((n) => {
    const dot = (n[0]*sun[0] + n[1]*sun[1] + n[2]*sun[2]) / sunMag;
    return Math.max(0, dot) * 1361 + gaussian(5);
  });
  return { face0: vals[0], face1: vals[1], face2: vals[2],
           face3: vals[3], face4: vals[4], face5: vals[5] };
}

function tickThermal(sensor, sat, timeSec, state) {
  const key = sensor.id;
  if (state.thermTemp[key] == null) state.thermTemp[key] = 250;
  let T = state.thermTemp[key];

  const target = sat.state === 'CRITICAL_FAIL' ? 380 : (sat.inSunlight ? 320 : 150);
  const sigma  = sat.inSunlight ? 0.5 : 0.2;
  T += (target - T) * 0.1 + gaussian(sigma);
  if (sat.state === 'CRITICAL_FAIL') T = Math.max(T, 350);
  state.thermTemp[key] = T;
  return { surface_K: T };
}

function tickOptical(sensor, sat, timeSec) {
  const T   = sat.period_s || 5570;
  const phi = (2 * Math.PI * timeSec) / T;
  const intensity = Math.max(0, 400 + 400 * Math.sin(phi)) + gaussian(2);
  const azimuth   = ((timeSec % T) / T) * 360;
  return { intensity, azimuth };
}

// ── Fault detection ───────────────────────────────────────────────────────────

function exceedsFaultThreshold(sensor, reading) {
  if (sensor.type === 'STAR_TRACKER') {
    // Check vector-part magnitude; q0 variation is normal for normalised quaternion
    const vMag = Math.sqrt(
      (reading.q1 ?? 0) ** 2 + (reading.q2 ?? 0) ** 2 + (reading.q3 ?? 0) ** 2
    );
    return vMag > sensor.fault_threshold;
  }
  if (sensor.type === 'THERMAL') {
    return (reading.surface_K ?? 0) > sensor.fault_threshold;
  }
  for (const axis of sensor.axes) {
    if (Math.abs(reading[axis] ?? 0) > sensor.fault_threshold) return true;
  }
  return false;
}

function worstAxisOf(sensor, reading) {
  let bestAxis = sensor.axes[0];
  let bestAbs  = 0;
  const axes = sensor.type === 'STAR_TRACKER' ? ['q1', 'q2', 'q3'] : sensor.axes;
  for (const axis of axes) {
    const v = Math.abs(reading[axis] ?? 0);
    if (v > bestAbs) { bestAbs = v; bestAxis = axis; }
  }
  return { axis: bestAxis, value: reading[bestAxis] ?? 0 };
}

function checkFault(sensor, sat, reading, ts_ms) {
  const over = exceedsFaultThreshold(sensor, reading);
  if (over) {
    sensor._normalTicks = 0;
    if (sensor.status !== 'FAULT') {
      sensor.status = 'FAULT';
      const { axis, value } = worstAxisOf(sensor, reading);
      sensor._anomalies.unshift({ ts_ms, axis, value });
      if (sensor._anomalies.length > 10) sensor._anomalies.pop();
      // Signal engine to trigger a correction scenario (consumed in engine.tick)
      if (sat.state === 'IDLE') sat._pendingFault = sensor.id;
    }
  } else {
    if (sensor.status === 'FAULT') {
      sensor._normalTicks = (sensor._normalTicks || 0) + 1;
      if (sensor._normalTicks >= 5) {
        sensor.status  = 'NOMINAL';
        sensor._normalTicks = 0;
      }
    }
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

export function tickSensors(sat, timeSec) {
  const state = getState(sat);
  const ts_ms = timeSec * 1000;

  for (const sensor of sat.sensors) {
    if (!sensor.active || sensor.status === 'OFFLINE') {
      sensor.last_reading = null;
      continue;
    }

    let reading;
    switch (sensor.type) {
      case 'GYROSCOPE':    reading = tickGyroscope(sensor, sat, timeSec, state);    break;
      case 'MAGNETOMETER': reading = tickMagnetometer(sensor, sat, timeSec);        break;
      case 'STAR_TRACKER': reading = tickStarTracker(sensor, sat, timeSec, state); break;
      case 'SUN_SENSOR':   reading = tickSunSensor(sensor, sat, timeSec);           break;
      case 'THERMAL':      reading = tickThermal(sensor, sat, timeSec, state);      break;
      case 'OPTICAL':      reading = tickOptical(sensor, sat, timeSec);             break;
      default:             continue;
    }

    reading.ts_ms       = ts_ms;
    sensor.last_reading = reading;
    sensor.history.push(reading);
    if (sensor.history.length > SENSOR_HISTORY_MAX) sensor.history.shift();

    checkFault(sensor, sat, reading, ts_ms);
  }
}
