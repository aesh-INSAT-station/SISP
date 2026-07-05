// Simplified solar geometry — no Cesium. Accuracy ~1°, sufficient for
// eclipse detection and directional lighting.

const SIM_EPOCH_DAYS_J2000 = 9131.5;

function daysSinceJ2000(simSec) {
  return SIM_EPOCH_DAYS_J2000 + simSec / 86400;
}

// Sun direction unit vector in ECI (J2000 ecliptic model).
export function sunDirectionECI(simSec) {
  const n = daysSinceJ2000(simSec);
  const L = ((280.460 + 0.9856474 * n) % 360 + 360) % 360;
  const g = (((357.528 + 0.9856003 * n) % 360 + 360) % 360) * (Math.PI / 180);
  const lambda = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * (Math.PI / 180);
  const eps = 23.439 * (Math.PI / 180);
  return {
    x: Math.cos(lambda),
    y: Math.cos(eps) * Math.sin(lambda),
    z: Math.sin(eps) * Math.sin(lambda),
  };
}

// Sun direction in ECEF (rotated by GMST).
export function sunDirectionFixed(simSec) {
  const eci = sunDirectionECI(simSec);
  const n = daysSinceJ2000(simSec);
  const T = n / 36525;
  const gmstSec = 67310.54841
    + (876600 * 3600 + 8640184.812866) * T
    + 0.093104 * T * T
    - 6.2e-6   * T * T * T;
  let gmstDeg = (gmstSec / 240) % 360;
  if (gmstDeg < 0) gmstDeg += 360;
  const theta = (gmstDeg * Math.PI) / 180;
  const c = Math.cos(theta), s = Math.sin(theta);
  return {
    x:  eci.x * c + eci.y * s,
    y: -eci.x * s + eci.y * c,
    z:  eci.z,
  };
}

// True if pos (ECEF metres) is illuminated: either facing the sun or outside the umbra.
export function isInSunlight(pos, sunDir) {
  if (!pos) return true;
  const dot = pos.x * sunDir.x + pos.y * sunDir.y + pos.z * sunDir.z;
  if (dot > 0) return true;
  const projX = sunDir.x * dot, projY = sunDir.y * dot, projZ = sunDir.z * dot;
  const perpX = pos.x - projX, perpY = pos.y - projY, perpZ = pos.z - projZ;
  return Math.sqrt(perpX * perpX + perpY * perpY + perpZ * perpZ) > 6378137;
}
