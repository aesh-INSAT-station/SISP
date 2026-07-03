// Line-of-sight helpers — plain { x, y, z } in metres, no Cesium.

const EARTH_R_M = 6371000; // mean radius (generous for LOS visualisation)

function mag3(v) { return Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z); }

// True iff the chord between two ECEF positions clears the Earth sphere.
export function losBetween(a, b) {
  if (!a || !b) return false;
  const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
  const d2 = dx * dx + dy * dy + dz * dz;
  if (d2 === 0) return mag3(a) > EARTH_R_M;
  const t = Math.max(0, Math.min(1, -(a.x * dx + a.y * dy + a.z * dz) / d2));
  const cx = a.x + dx * t, cy = a.y + dy * t, cz = a.z + dz * t;
  return Math.sqrt(cx * cx + cy * cy + cz * cz) > EARTH_R_M;
}

// Geodetic surface → ECEF metres (local helper, no import needed).
function gsToEcef(lat_deg, lon_deg) {
  const lat = (lat_deg * Math.PI) / 180;
  const lon = (lon_deg * Math.PI) / 180;
  const a  = 6378137.0;
  const e2 = 0.00669437999014;
  const N  = a / Math.sqrt(1 - e2 * Math.sin(lat) ** 2);
  return {
    x: N * Math.cos(lat) * Math.cos(lon),
    y: N * Math.cos(lat) * Math.sin(lon),
    z: N * (1 - e2) * Math.sin(lat),
  };
}

// True if satPos (ECEF metres) has LOS to a ground station at lat/lon.
export function losToStation(satPos, station) {
  if (!satPos) return false;
  const stPos = gsToEcef(station.lat_deg, station.lon_deg);
  const dx = satPos.x - stPos.x, dy = satPos.y - stPos.y, dz = satPos.z - stPos.z;
  // Above horizon: dot(station_up, sat−station) > 0
  const dotUp = stPos.x * dx + stPos.y * dy + stPos.z * dz;
  return dotUp > 0 && losBetween(satPos, stPos);
}
