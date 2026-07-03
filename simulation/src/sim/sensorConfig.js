export const SENSOR_HISTORY_MAX = 200;

function makeSensor(id, type, label, unit, axes, nominal_range, fault_threshold) {
  return { id, type, label, unit, axes, nominal_range, fault_threshold,
    active: true, status: 'NOMINAL', last_reading: null,
    history: [], _anomalies: [], _normalTicks: 0 };
}

const SENSOR_DEFS = {
  0x01: [
    makeSensor('optical-01', 'OPTICAL',      'Optical Camera',   'W/m²/sr',   ['intensity', 'azimuth'],                              [0, 800],        850),
    makeSensor('star-01',    'STAR_TRACKER', 'Star Tracker A',   'quaternion', ['q0', 'q1', 'q2', 'q3'],                              [-1, 1],         0.4),
    makeSensor('therm-01',   'THERMAL',      'Thermal Surface',  'K',          ['surface_K'],                                         [140, 330],      370),
  ],
  0x02: [
    makeSensor('gyro-01',    'GYROSCOPE',    'Gyroscope A',      'deg/s',      ['x', 'y', 'z'],                                       [-5, 5],         3.2),
    makeSensor('sun-01',     'SUN_SENSOR',   'Sun Sensor',       'W/m²',       ['face0', 'face1', 'face2', 'face3', 'face4', 'face5'], [0, 1400],       1380),
    makeSensor('mag-01',     'MAGNETOMETER', 'Magnetometer A',   'nT',         ['x', 'y', 'z'],                                       [-50000, 50000],  55000),
  ],
  0x03: [
    makeSensor('mag-01',     'MAGNETOMETER', 'Magnetometer A',   'nT',         ['x', 'y', 'z'],                                       [-50000, 50000],  55000),
    makeSensor('gyro-01',    'GYROSCOPE',    'Gyroscope A',      'deg/s',      ['x', 'y', 'z'],                                       [-5, 5],         3.2),
    makeSensor('therm-01',   'THERMAL',      'Thermal Surface',  'K',          ['surface_K'],                                         [140, 330],      370),
    makeSensor('star-01',    'STAR_TRACKER', 'Star Tracker A',   'quaternion', ['q0', 'q1', 'q2', 'q3'],                              [-1, 1],         0.4),
  ],
  0x04: [
    makeSensor('gyro-01',    'GYROSCOPE',    'Gyroscope A',      'deg/s',      ['x', 'y', 'z'],                                       [-5, 5],         3.2),
    makeSensor('star-01',    'STAR_TRACKER', 'Star Tracker A',   'quaternion', ['q0', 'q1', 'q2', 'q3'],                              [-1, 1],         0.4),
  ],
  0x05: [
    makeSensor('gyro-01',    'GYROSCOPE',    'Gyroscope A',      'deg/s',      ['x', 'y', 'z'],                                       [-5, 5],         3.2),
    makeSensor('star-01',    'STAR_TRACKER', 'Star Tracker A',   'quaternion', ['q0', 'q1', 'q2', 'q3'],                              [-1, 1],         0.4),
  ],
  0x06: [
    makeSensor('therm-01',   'THERMAL',      'Thermal Surface',  'K',          ['surface_K'],                                         [140, 330],      370),
    makeSensor('sun-01',     'SUN_SENSOR',   'Sun Sensor',       'W/m²',       ['face0', 'face1', 'face2', 'face3', 'face4', 'face5'], [0, 1400],       1380),
  ],
  0x07: [
    makeSensor('mag-01',     'MAGNETOMETER', 'Magnetometer A',   'nT',         ['x', 'y', 'z'],                                       [-50000, 50000],  55000),
    makeSensor('gyro-01',    'GYROSCOPE',    'Gyroscope A',      'deg/s',      ['x', 'y', 'z'],                                       [-5, 5],         3.2),
    makeSensor('therm-01',   'THERMAL',      'Thermal Surface',  'K',          ['surface_K'],                                         [140, 330],      370),
  ],
  0x08: [
    makeSensor('optical-01', 'OPTICAL',      'Optical Camera',   'W/m²/sr',   ['intensity', 'azimuth'],                              [0, 800],        850),
    makeSensor('therm-01',   'THERMAL',      'Thermal Surface',  'K',          ['surface_K'],                                         [140, 330],      370),
    makeSensor('mag-01',     'MAGNETOMETER', 'Magnetometer A',   'nT',         ['x', 'y', 'z'],                                       [-50000, 50000],  55000),
    makeSensor('sun-01',     'SUN_SENSOR',   'Sun Sensor',       'W/m²',       ['face0', 'face1', 'face2', 'face3', 'face4', 'face5'], [0, 1400],       1380),
  ],
};

export function buildSensors(satId) {
  const defs = SENSOR_DEFS[satId];
  if (!defs) return [];
  // Deep clone so each satellite instance has its own independent state
  return defs.map((d) => ({
    ...d,
    history:    [],
    _anomalies: [],
    _normalTicks: 0,
  }));
}
