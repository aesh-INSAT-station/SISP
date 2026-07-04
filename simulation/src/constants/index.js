export const SAT_COUNT = 8;
export const SENSORS = ['MAGNETOMETER', 'SUN_SENSOR', 'GYROSCOPE', 'STAR_TRACKER', 'THERMAL', 'OPTICAL'];
export const PACKET_DURATION_MS = 1200;
export const TICK_INTERVAL_MS = 2000;
export const HEARTBEAT_INTERVAL_MS = 10000;
export const POLL_INTERVAL_MS = 250;

export const STATE_COLOR_HEX = {
  IDLE:              0x00b9ff,
  CORR_WAIT_RSP:     0xf5c518,
  CORR_COMPUTING:    0xf5c518,
  RELAY_WAIT_ACCEPT: 0x22d3ee,
  RELAY_ACTIVE:      0x22d3ee,
  BORROW_WAIT_RSP:   0xa78bfa,
  CRITICAL_FAIL:     0xff3d5a,
};

export const STATE_COLOR_CSS = {
  IDLE:              '#00b9ff',
  CORR_WAIT_RSP:     '#f5c518',
  CORR_COMPUTING:    '#f5c518',
  RELAY_WAIT_ACCEPT: '#22d3ee',
  RELAY_ACTIVE:      '#22d3ee',
  BORROW_WAIT_RSP:   '#a78bfa',
  CRITICAL_FAIL:     '#ff3d5a',
};

export const SERVICE_COLOR = {
  CORRECTION_REQ:  '#f5c518',
  CORRECTION_RSP:  '#f5c518',
  RELAY_REQ:       '#22d3ee',
  RELAY_ACCEPT:    '#22d3ee',
  RELAY_REJECT:    '#22d3ee',
  DOWNLINK_DATA:   '#a855f7',
  DOWNLINK_ACK:    '#a855f7',
  BORROW_REQ:      '#a78bfa',
  BORROW_RSP:      '#a78bfa',
  HEARTBEAT:       '#00ff88',
  FAILURE:         '#ff3d5a',
  STATUS_BROADCAST:'#64748b',
};

export const SERVICE_FAMILY = {
  CORRECTION_REQ:  'CORRECTION',
  CORRECTION_RSP:  'CORRECTION',
  RELAY_REQ:       'RELAY',
  RELAY_ACCEPT:    'RELAY',
  RELAY_REJECT:    'RELAY',
  DOWNLINK_DATA:   'RELAY',
  DOWNLINK_ACK:    'RELAY',
  BORROW_REQ:      'BORROW',
  BORROW_RSP:      'BORROW',
  HEARTBEAT:       'HEARTBEAT',
  FAILURE:         'FAILURE',
  STATUS_BROADCAST:'STATUS',
};

// ── NUWA Design System ────────────────────────────────────────────────────────

export const NUWA_BG           = '#00040c';           // near-black space
export const PANEL_BG          = 'linear-gradient(145deg, rgba(5,14,31,0.58), rgba(2,7,18,0.46))';
export const PANEL_BORDER      = '1px solid rgba(112,211,255,0.18)';
export const PANEL_SHADOW      = '0 18px 60px rgba(0,0,0,0.36), inset 0 1px 0 rgba(255,255,255,0.06)';
export const PANEL_RADIUS      = 8;
export const ACCENT            = '#00b9ff';           // electric cyan-blue
export const ACCENT_DIM        = 'rgba(0,185,255,0.18)';
export const TEXT_PRIMARY      = '#d4eeff';
export const TEXT_SECONDARY    = '#4a7a9b';
export const TEXT_DIM          = '#1c3550';
export const STATUS_GREEN      = '#00ff88';
export const STATUS_AMBER      = '#f5c518';
export const STATUS_RED        = '#ff3d5a';

export const FONT_MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

// ── Ground stations ───────────────────────────────────────────────────────────

export const GROUND_ID = 0x00;

export const GROUND_STATIONS = [
  { id: 'KOU', name: 'Kourou',   lat_deg:  5.16, lon_deg:  -52.69 },
  { id: 'SVA', name: 'Svalbard', lat_deg: 78.23, lon_deg:   15.39 },
  { id: 'MCM', name: 'McMurdo',  lat_deg:-77.85, lon_deg:  166.67 },
  { id: 'HAW', name: 'Hawaii',   lat_deg: 22.13, lon_deg: -159.67 },
];

export const SENSOR_HALF_ANGLE_DEG = {
  OPTICAL:      15,
  THERMAL:      18,
  MAGNETOMETER: 45,
  SUN_SENSOR:   60,
  GYROSCOPE:    30,
  STAR_TRACKER:  5,
};

// ── Constellation config ──────────────────────────────────────────────────────

export const SAT_CONFIG = [
  {
    id: 0x01, name: 'LEO-IMG', role: 'IMAGING',
    a_km: 6853, e: 0.001, i_deg: 97.4,  raan_deg:   0, argP_deg: 0,
    sensor: 'OPTICAL', baseDegrBoost: 0, modelKm: 40,
    sample: { intervalSec: 30, windowMin: 180 },
    roleWeights: { failure: 1.0, correction: 1.0, relay: 2.5, status: 1.2, borrow: 0.5 },
    telemetrySource: 'segments.csv',
    opsatChannel: 'CADC0873',
    opsatDetectorOpts: { windowLen: 100, hankelRows: 50, threshold: 0.15 },
    opsatNoise: { sigma: 5e-7 },   // data std≈2e-5 → σ=2.5% of range
  },
  {
    id: 0x02, name: 'LEO-COM', role: 'COMMS',
    a_km: 6928, e: 0.001, i_deg: 53.0,  raan_deg:  45, argP_deg: 0,
    sensor: 'GYROSCOPE', baseDegrBoost: 0, modelKm: 40,
    sample: { intervalSec: 30, windowMin: 180 },
    roleWeights: { failure: 1.0, correction: 1.0, relay: 1.4, status: 1.6, borrow: 0.8 },
    telemetrySource: 'segments.csv',
    opsatChannel: 'CADC0872',
    opsatDetectorOpts: { windowLen: 100, hankelRows: 50, threshold: 0.15 },
    opsatNoise: { sigma: 5e-7 },   // data std≈2e-5 → σ=2.5% of range
  },
  {
    id: 0x03, name: 'LEO-SCI', role: 'SCIENCE',
    a_km: 6778, e: 0.001, i_deg: 51.6,  raan_deg:  90, argP_deg: 0,
    sensor: 'MAGNETOMETER', baseDegrBoost: 0, modelKm: 40,
    sample: { intervalSec: 30, windowMin: 180 },
    roleWeights: { failure: 1.0, correction: 2.8, relay: 1.0, status: 1.0, borrow: 1.0 },
    telemetrySource: 'segments.csv',
    opsatChannel: 'CADC0894',
    opsatDetectorOpts: { windowLen: 100, hankelRows: 50, threshold: 0.15 },
    opsatNoise: { sigma: 0.01 },   // data std≈0.21 → σ≈5% of range
  },
  {
    id: 0x04, name: 'MEO-NAV-A', role: 'NAV_REFERENCE',
    a_km: 26578, e: 0.001, i_deg: 55.0, raan_deg:   0, argP_deg: 0,
    sensor: 'STAR_TRACKER', baseDegrBoost: 4, modelKm: 80,
    sample: { intervalSec: 300, windowMin: 1440 },
    roleWeights: { failure: 0.4, correction: 0.2, relay: 0.5, status: 1.5, borrow: 0.5 },
  },
  {
    id: 0x05, name: 'MEO-NAV-B', role: 'NAV_REFERENCE',
    a_km: 26578, e: 0.001, i_deg: 55.0, raan_deg: 120, argP_deg: 0,
    sensor: 'STAR_TRACKER', baseDegrBoost: 4, modelKm: 80,
    sample: { intervalSec: 300, windowMin: 1440 },
    roleWeights: { failure: 0.4, correction: 0.2, relay: 0.5, status: 1.5, borrow: 0.5 },
  },
  {
    id: 0x06, name: 'GEO-RELAY', role: 'RELAY_HUB',
    a_km: 42164, e: 0.0,   i_deg: 0.0,  raan_deg: 180, argP_deg: 0,
    sensor: 'THERMAL', baseDegrBoost: 1, modelKm: 120,
    sample: { intervalSec: 600, windowMin: 1440 },
    static_geo: true,
    roleWeights: { failure: 0.3, correction: 0.0, relay: 2.0, status: 0.8, borrow: 0.3 },
  },
  {
    id: 0x07, name: 'HEO-MOL', role: 'HIGH_LATITUDE',
    a_km: 27178, e: 0.737, i_deg: 63.4, raan_deg: 270, argP_deg: 270,
    sensor: 'GYROSCOPE', baseDegrBoost: 2, modelKm: 80,
    sample: { intervalSec: 300, windowMin: 1440 },
    roleWeights: { failure: 1.6, correction: 1.0, relay: 0.8, status: 0.8, borrow: 0.7 },
  },
  {
    id: 0x08, name: 'LEO-OBS', role: 'OBSERVATION',
    a_km: 7068, e: 0.001, i_deg: 98.2,  raan_deg: 315, argP_deg: 0,
    sensor: 'OPTICAL', baseDegrBoost: 0, modelKm: 40,
    sample: { intervalSec: 30, windowMin: 180 },
    roleWeights: { failure: 0.7, correction: 1.0, relay: 1.0, status: 1.0, borrow: 2.5 },
    telemetrySource: 'segments.csv',
    opsatChannel: 'CADC0892',
    opsatDetectorOpts: { windowLen: 100, hankelRows: 50, threshold: 0.15 },
    opsatNoise: { sigma: 0.015 },  // data std≈0.33 → σ≈4.5% of range
  },
];
