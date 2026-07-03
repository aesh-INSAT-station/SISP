// Pure orbital mechanics — no Cesium, no Three.js.
// All positions are plain { x, y, z } in metres.
// Time is simSec = seconds since sim epoch (2025-01-01T00:00:00Z).

const MU_EARTH = 398600.4418;        // km³/s²
const EARTH_RADIUS_KM = 6378.137;    // km
const EARTH_RADIUS_M  = 6378137.0;   // m (WGS-84 equatorial)
const EARTH_F = 1 / 298.257223563;   // WGS-84 flattening
const EARTH_B = EARTH_RADIUS_M * (1 - EARTH_F);
const EARTH_E2 = 1 - (EARTH_B * EARTH_B) / (EARTH_RADIUS_M * EARTH_RADIUS_M);

// Days from J2000 (2000-01-01T12:00:00Z) to sim epoch (2025-01-01T00:00:00Z).
// 25 years × 365 + 7 leap years − 0.5 day (noon → midnight) = 9131.5
const SIM_EPOCH_DAYS_J2000 = 9131.5;

export function meanMotion(a_km) { return Math.sqrt(MU_EARTH / a_km ** 3); } // rad/s

export function periodSeconds(a_km) { return (2 * Math.PI) / meanMotion(a_km); }

export function altitudeKm(a_km) { return a_km - EARTH_RADIUS_KM; }

// Newton–Raphson for Kepler's equation M = E − e·sin(E).
function solveKepler(M, e, iterations = 10) {
  let E = e < 0.8 ? M : Math.PI;
  for (let k = 0; k < iterations; k++) {
    E -= (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  }
  return E;
}

// Vallado mean GMST (Algorithm 15). simSec = seconds since sim epoch.
export function gmstRad(simSec) {
  const d = SIM_EPOCH_DAYS_J2000 + simSec / 86400;
  const T = d / 36525;
  const gmstSec = 67310.54841
    + (876600 * 3600 + 8640184.812866) * T
    + 0.093104 * T * T
    - 6.2e-6  * T * T * T;
  let deg = (gmstSec / 240) % 360;
  if (deg < 0) deg += 360;
  return (deg * Math.PI) / 180;
}

// ECI position { x, y, z } in metres at simSec.
export function getPositionAtTime(elements, simSec) {
  const { a, e = 0, i, raan, argP = 0, M0, epochSec = 0 } = elements;
  const n = meanMotion(a);
  const M = M0 + n * (simSec - epochSec);
  const E = solveKepler(M, e);

  const cosE = Math.cos(E), sinE = Math.sin(E);
  const sqrt1e = Math.sqrt(1 - e * e);
  const xp = a * (cosE - e);
  const yp = a * sqrt1e * sinE;

  const cosO = Math.cos(raan), sinO = Math.sin(raan);
  const cosI = Math.cos(i),    sinI = Math.sin(i);
  const cosW = Math.cos(argP), sinW = Math.sin(argP);

  const x = (cosO*cosW - sinO*sinW*cosI)*xp + (-cosO*sinW - sinO*cosW*cosI)*yp;
  const y = (sinO*cosW + cosO*sinW*cosI)*xp + (-sinO*sinW + cosO*cosW*cosI)*yp;
  const z = sinW*sinI*xp + cosW*sinI*yp;

  return { x: x * 1000, y: y * 1000, z: z * 1000 };
}

// ECI → ECEF rotation by GMST (Z-axis). Both in metres.
export function eciToEcef(eci, simSec) {
  const theta = gmstRad(simSec);
  const c = Math.cos(theta), s = Math.sin(theta);
  return {
    x:  eci.x * c + eci.y * s,
    y: -eci.x * s + eci.y * c,
    z:  eci.z,
  };
}

// Full orbit as ECI points (metres). Closed by repeating point[0] at end.
export function getOrbitPoints(elements, numPoints = 120) {
  const { a, e = 0, i, raan, argP = 0 } = elements;
  const cosO = Math.cos(raan), sinO = Math.sin(raan);
  const cosI = Math.cos(i),    sinI = Math.sin(i);
  const cosW = Math.cos(argP), sinW = Math.sin(argP);
  const points = [];

  for (let k = 0; k <= numPoints; k++) {
    const nu = (k / numPoints) * 2 * Math.PI;
    const r = (a * (1 - e * e)) / (1 + e * Math.cos(nu));
    const xp = r * Math.cos(nu), yp = r * Math.sin(nu);

    const x = (cosO*cosW - sinO*sinW*cosI)*xp + (-cosO*sinW - sinO*cosW*cosI)*yp;
    const y = (sinO*cosW + cosO*sinW*cosI)*xp + (-sinO*sinW + cosO*cosW*cosI)*yp;
    const z = sinW*sinI*xp + cosW*sinI*yp;
    points.push({ x: x * 1000, y: y * 1000, z: z * 1000 });
  }
  return points;
}

// ECEF metres → geodetic { lat_deg, lon_deg, alt_km }.
export function ecefToGeodetic({ x, y, z }) {
  const lon = Math.atan2(y, x);
  const p = Math.sqrt(x * x + y * y);
  let lat = Math.atan2(z, p * (1 - EARTH_E2));
  for (let k = 0; k < 5; k++) {
    const sinLat = Math.sin(lat);
    const N = EARTH_RADIUS_M / Math.sqrt(1 - EARTH_E2 * sinLat * sinLat);
    lat = Math.atan2(z + EARTH_E2 * N * sinLat, p);
  }
  const sinLat = Math.sin(lat);
  const N = EARTH_RADIUS_M / Math.sqrt(1 - EARTH_E2 * sinLat * sinLat);
  const alt = p / Math.cos(lat) - N;
  return {
    lat_deg: (lat * 180) / Math.PI,
    lon_deg: (lon * 180) / Math.PI,
    alt_km:  alt / 1000,
  };
}

// Convenience: geodetic at a given sim time.
export function geodeticAt(elements, simSec) {
  const eci  = getPositionAtTime(elements, simSec);
  const ecef = eciToEcef(eci, simSec);
  return ecefToGeodetic(ecef);
}

// Ground track over the next durationMinutes, sampled every intervalSeconds.
// Returns [{ lat_deg, lon_deg }].
export function getGroundTrack(elements, simSec, durationMinutes, intervalSeconds = 60) {
  const total = durationMinutes * 60;
  const out = [];
  for (let s = 0; s <= total; s += intervalSeconds) {
    const eci  = getPositionAtTime(elements, simSec + s);
    const ecef = eciToEcef(eci, simSec + s);
    out.push(ecefToGeodetic(ecef));
  }
  return out;
}

// Geodetic surface position → ECEF metres (alt = 0).
export function latLonToEcef(lat_deg, lon_deg) {
  const lat = (lat_deg * Math.PI) / 180;
  const lon = (lon_deg * Math.PI) / 180;
  const N = EARTH_RADIUS_M / Math.sqrt(1 - EARTH_E2 * Math.sin(lat) ** 2);
  return {
    x: N * Math.cos(lat) * Math.cos(lon),
    y: N * Math.cos(lat) * Math.sin(lon),
    z: N * (1 - EARTH_E2) * Math.sin(lat),
  };
}

// Altitude-driven DEGR contribution.
export function altitudeDEGR(altKm) {
  let d = 0;
  if (altKm >= 160  && altKm <= 2000)  d += Math.min(5, Math.max(0, Math.floor((2000 - altKm) / 200)));
  if (altKm >= 1000 && altKm <= 6000)  d += 3;
  if (altKm >= 13000&& altKm <= 60000) d += 2;
  if (altKm > 60000)                   d += 1;
  return d;
}
