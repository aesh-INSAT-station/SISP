'use strict';

const koffi = require('koffi');
const path = require('path');
const fs = require('fs');
const { loadBridgeEnv, parsePort } = require('./src/env');
const { createWebSocketHub } = require('./src/websocketHub');

// ── Environment ──────────────────────────────────────────────────────────────
// Vite reads .env automatically, but this plain Node bridge does not. Load the
// root .env here so SISP_PORT stays in sync when running `npm run dev`.
loadBridgeEnv({
	rootDir: path.join(__dirname, '..'),
	serverDir: __dirname,
});

// ── DLL path ─────────────────────────────────────────────────────────────────
// The C++ protocol engine now lives at the SISP repo root (this app was merged
// in from the standalone SISP-SIM repo, where cpp/sisp was a git submodule).
// Resolve the DLL from the repo root, with an env override for custom builds.
const DLL_CANDIDATES = [
	process.env.SISP_DLL_PATH,
	// SISP repo root: simulation/server -> ../../
	path.join(__dirname, '../../c++ implemnetation/build/bin/Release/sisp.dll'),
	// Legacy submodule location (kept as a fallback)
	path.join(__dirname, '../cpp/sisp/c++ implemnetation/build/bin/Release/sisp.dll'),
].filter(Boolean);

const DLL_PATH = DLL_CANDIDATES.find((p) => fs.existsSync(p)) || DLL_CANDIDATES[0];

// ── Load library ──────────────────────────────────────────────────────────────
let lib;
try {
	lib = koffi.load(DLL_PATH);
} catch (e) {
	console.error('[SISP] Failed to load sisp.dll:', e.message);
	console.error('[SISP] Tried:', DLL_CANDIDATES.join('\n         '));
	process.exit(1);
}

// ── C API bindings ────────────────────────────────────────────────────────────
const sim_create_context = lib.func('sim_create_context', 'void *', ['uint8']);
const sim_destroy_context = lib.func('sim_destroy_context', 'void', ['void *']);
const sim_inject_packet = lib.func('sim_inject_packet', 'void', [
	'void *',
	'uint8 *',
	'uint16',
]);
const sim_inject_event = lib.func('sim_inject_event', 'void', [
	'void *',
	'int',
]);
const sim_advance_time = lib.func('sim_advance_time', 'void', [
	'void *',
	'uint32',
]);
const sim_get_state = lib.func('sim_get_state', 'int', ['void *']);
const sim_get_degr = lib.func('sim_get_degr', 'uint8', ['void *']);
// sim_get_known_failures not used by the bridge — omit to keep binding simple
koffi.proto('sim_tx_cb', 'void', ['uint8', 'uint8 *', 'uint16']);

const sim_register_tx_callback = lib.func('sim_register_tx_callback', 'void', [
	'sim_tx_cb *',
]);

// ── Enum maps (must match sisp_state_machine.hpp) ─────────────────────────────
const STATE_JS = [
	'IDLE', // 0  IDLE
	'CORR_WAIT_RSP', // 1  CORR_WAIT_RSP
	'CORR_WAIT_RSP', // 2  CORR_COLLECTING
	'CORR_COMPUTING', // 3  CORR_COMPUTING
	'IDLE', // 4  CORR_DONE
	'IDLE', // 5  CORR_RESPONDING
	'RELAY_WAIT_ACCEPT', // 6  RELAY_WAIT_ACCEPT
	'RELAY_ACTIVE', // 7  RELAY_SENDING
	'RELAY_ACTIVE', // 8  RELAY_WAIT_ACK
	'IDLE', // 9  RELAY_DONE
	'RELAY_ACTIVE', // 10 RELAY_RECEIVING
	'RELAY_ACTIVE', // 11 RELAY_STORING
	'RELAY_ACTIVE', // 12 RELAY_DOWNLINKING
	'BORROW_WAIT_RSP', // 13 BORROW_WAIT_ACCEPT
	'BORROW_WAIT_RSP', // 14 BORROW_RECEIVING
	'IDLE', // 15 BORROW_DONE
	'IDLE', // 16 BORROW_SAMPLING
	'IDLE', // 17 BORROW_SENDING
	'IDLE', // 18 TIMEOUT
	'IDLE', // 19 ERROR
	'CRITICAL_FAIL', // 20 CRITICAL_FAIL
];

// Service code (high nibble of byte 0) → JS string (matches sisp_protocol.hpp enum)
const SVC_NAME = {
	0x0: 'CORRECTION_REQ',
	0x1: 'CORRECTION_RSP',
	0x2: 'RELAY_REQ',
	0x3: 'RELAY_ACCEPT',
	0x4: 'RELAY_REJECT',
	0x5: 'DOWNLINK_DATA',
	0x6: 'DOWNLINK_ACK',
	0x7: 'STATUS_BROADCAST',
	0x8: 'HEARTBEAT',
	0x9: 'HEARTBEAT_ACK',
	0xa: 'BORROW_DECISION',
	0xe: 'BORROW_REQ',
	0xf: 'FAILURE',
};

// Event values (must match sisp_state_machine.hpp Event enum)
const EVT = {
	RX_CORRECTION_REQ: 0,
	RX_CORRECTION_RSP: 1,
	RX_RELAY_REQ: 2,
	RX_RELAY_ACCEPT: 3,
	RX_RELAY_REJECT: 4,
	RX_DOWNLINK_DATA: 5,
	RX_DOWNLINK_ACK: 6,
	RX_STATUS: 7,
	RX_HEARTBEAT: 8,
	RX_HEARTBEAT_ACK: 9,
	RX_BORROW_REQ: 10,
	RX_FAILURE: 11,
	FAULT_DETECTED: 12,
	TIMER_EXPIRED: 13,
	ENERGY_LOW: 14,
	GS_VISIBLE: 15,
	GS_LOST: 16,
	ALL_FRAGS_SENT: 17,
	ALL_FRAGS_RCVD: 18,
	SENSOR_READ_DONE: 19,
	CORRECTION_DONE: 20,
	CRITICAL_FAILURE: 21,
	RESET: 22,
	RX_BORROW_DECISION: 23,
};

// ── Real OPSSAT segment telemetry ────────────────────────────────────────────
// Lives at the SISP repo root (data/raw/segments.csv). The legacy default
// pointed at the old cpp/sisp submodule; keep it as a fallback and allow an
// env override via SISP_SEGMENTS_CSV.
const SEGMENTS_CSV_PATH =
	process.env.SISP_SEGMENTS_CSV ||
	[
		path.join(__dirname, '../../data/raw/segments.csv'),
		path.join(__dirname, '../cpp/sisp/data/raw/segments.csv'),
	].find((p) => fs.existsSync(p)) ||
	path.join(__dirname, '../../data/raw/segments.csv');
const SENSOR_HISTORY_MAX = 200;
const INITIAL_SENSOR_HISTORY = 32;
const DEFAULT_SAMPLE_INTERVAL_MS = 1000;

// segments.csv contains 9 CADC channels. The visual constellation has 8
// satellites, so the smallest channel (CADC0886 in the bundled data) is left out.
const CHANNEL_ASSIGNMENTS = [
	{ satId: 1, channel: 'CADC0872' },
	{ satId: 2, channel: 'CADC0873' },
	{ satId: 3, channel: 'CADC0874' },
	{ satId: 4, channel: 'CADC0884' },
	{ satId: 5, channel: 'CADC0888' },
	{ satId: 6, channel: 'CADC0890' },
	{ satId: 7, channel: 'CADC0892' },
	{ satId: 8, channel: 'CADC0894' },
];

function numberOrNull(value) {
	const n = Number(value);
	return Number.isFinite(n) ? n : null;
}

function sampleIntervalMs(row) {
	const sampling = Number(row?.sampling);
	return Number.isFinite(sampling) && sampling > 0
		? Math.max(100, sampling * 1000)
		: DEFAULT_SAMPLE_INTERVAL_MS;
}

function paddedRange(lo, hi) {
	if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [-1, 1];
	if (lo === hi) {
		const pad = Math.max(Math.abs(lo) * 0.1, 1e-12);
		return [lo - pad, hi + pad];
	}
	const pad = Math.max(Math.abs(hi - lo) * 0.12, 1e-12);
	return [lo - pad, hi + pad];
}

function computeChannelStats(channel, rows) {
	const values = rows.map((row) => row.value).filter(Number.isFinite);
	const normalValues = rows
		.filter((row) => row.anomaly !== 1)
		.map((row) => row.value)
		.filter(Number.isFinite);
	const nominalBase = normalValues.length > 0 ? normalValues : values;
	const min = Math.min(...values);
	const max = Math.max(...values);
	const normalMin = Math.min(...nominalBase);
	const normalMax = Math.max(...nominalBase);
	const [rangeLo, rangeHi] = paddedRange(normalMin, normalMax);
	const maxNominalAbs = Math.max(Math.abs(rangeLo), Math.abs(rangeHi));
	const maxAbs = Math.max(...values.map((value) => Math.abs(value)));
	return {
		channel,
		sampleCount: rows.length,
		anomalyCount: rows.reduce((n, row) => n + (row.anomaly === 1 ? 1 : 0), 0),
		min,
		max,
		normalMin: rangeLo,
		normalMax: rangeHi,
		faultThreshold: Math.max(maxNominalAbs, maxAbs * 0.85, 1e-12),
		firstTimestamp: rows[0]?.timestamp ?? null,
		lastTimestamp: rows[rows.length - 1]?.timestamp ?? null,
	};
}

function makeSegmentSensor(channel, stats) {
	return {
		id: `segment-${channel}`,
		type: 'OPSSAT_CHANNEL',
		label: channel,
		unit: 'raw',
		axes: ['value'],
		nominal_range: [stats.normalMin, stats.normalMax],
		fault_threshold: stats.faultThreshold,
		active: true,
		status: 'NOMINAL',
		last_reading: null,
		history: [],
		_anomalies: [],
		_normalTicks: 0,
		source: 'segments.csv',
		source_channel: channel,
		stats,
	};
}

function loadSegmentTelemetry(filePath) {
	const bySat = new Map();
	const empty = {
		bySat,
		filePath,
		availableChannels: [],
		selectedChannels: [],
		loadedRows: 0,
	};

	if (!fs.existsSync(filePath)) {
		console.warn(`[SISP] segments.csv not found at ${filePath}`);
		return empty;
	}

	const text = fs.readFileSync(filePath, 'utf8').trim();
	if (!text) {
		console.warn(`[SISP] segments.csv is empty at ${filePath}`);
		return empty;
	}

	const lines = text.split(/\r?\n/);
	const headers = lines.shift().split(',').map((header) => header.trim());
	const idx = {
		channel: headers.indexOf('channel'),
		timestamp: headers.indexOf('timestamp'),
		value: headers.indexOf('value'),
		sampling: headers.indexOf('sampling'),
		anomaly: headers.indexOf('anomaly'),
		segment: headers.indexOf('segment'),
		train: headers.indexOf('train'),
	};
	if (idx.channel < 0 || idx.timestamp < 0 || idx.value < 0) {
		console.warn('[SISP] segments.csv is missing required columns');
		return empty;
	}

	const byChannel = new Map();
	for (const line of lines) {
		if (!line.trim()) continue;
		const cols = line.split(',');
		const channel = cols[idx.channel];
		const value = numberOrNull(cols[idx.value]);
		if (!channel || value == null) continue;
		const timestamp = cols[idx.timestamp] || null;
		const tsMs = timestamp ? Date.parse(timestamp) : NaN;
		const row = {
			channel,
			timestamp,
			ts_ms: Number.isFinite(tsMs) ? tsMs : null,
			value,
			sampling: numberOrNull(cols[idx.sampling]) ?? 1,
			anomaly: Number(cols[idx.anomaly]) === 1 ? 1 : 0,
			segment: numberOrNull(cols[idx.segment]),
			train: numberOrNull(cols[idx.train]),
		};
		if (!byChannel.has(channel)) byChannel.set(channel, []);
		byChannel.get(channel).push(row);
	}

	for (const rows of byChannel.values()) {
		rows.sort((a, b) => (a.ts_ms ?? 0) - (b.ts_ms ?? 0));
	}

	const availableChannels = Array.from(byChannel.entries())
		.map(([channel, rows]) => ({ channel, count: rows.length }))
		.sort((a, b) => a.channel.localeCompare(b.channel));

	for (const assignment of CHANNEL_ASSIGNMENTS) {
		const rows = byChannel.get(assignment.channel) || [];
		if (rows.length === 0) continue;
		const stats = computeChannelStats(assignment.channel, rows);
		bySat.set(assignment.satId, {
			satId: assignment.satId,
			channel: assignment.channel,
			rows,
			stats,
			sensor: makeSegmentSensor(assignment.channel, stats),
			cursor: 0,
			totalSamples: 0,
			elapsedMs: 0,
			nextIntervalMs: sampleIntervalMs(rows[0]),
			lastAnomaly: 0,
		});
	}

	const selectedChannels = Array.from(bySat.values()).map((stream) => ({
		satId: stream.satId,
		channel: stream.channel,
		count: stream.rows.length,
		anomalyCount: stream.stats.anomalyCount,
	}));

	const skipped = availableChannels
		.filter(
			(item) =>
				!selectedChannels.some((selected) => selected.channel === item.channel),
		)
		.map((item) => `${item.channel} (${item.count})`);
	if (skipped.length > 0) {
		console.log(`[SISP] Unmapped CSV channel(s): ${skipped.join(', ')}`);
	}

	return {
		bySat,
		filePath,
		availableChannels,
		selectedChannels,
		loadedRows: lines.length,
	};
}

// ── Satellite contexts + centralized satellite store ─────────────────────────
const SATELLITE_CONTEXT = [
	{ id: 1, name: 'LEO-IMG', role: 'IMAGING' },
	{ id: 2, name: 'LEO-COM', role: 'COMMS' },
	{ id: 3, name: 'LEO-SCI', role: 'SCIENCE' },
	{ id: 4, name: 'MEO-NAV-A', role: 'NAV_REFERENCE' },
	{ id: 5, name: 'MEO-NAV-B', role: 'NAV_REFERENCE' },
	{ id: 6, name: 'GEO-RELAY', role: 'RELAY_HUB' },
	{ id: 7, name: 'HEO-MOL', role: 'HIGH_LATITUDE' },
	{ id: 8, name: 'LEO-OBS', role: 'OBSERVATION' },
];
const SAT_IDS = SATELLITE_CONTEXT.map((sat) => sat.id);
const segmentTelemetry = loadSegmentTelemetry(SEGMENTS_CSV_PATH);
const ctxMap = {};
const satelliteStore = new Map(
	SATELLITE_CONTEXT.map((sat) => [
		sat.id,
		{
			...sat,
			state: 'IDLE',
			rawState: 0,
			degr: 0,
			energy: 0,
			activeScenario: null,
			sensors: segmentTelemetry.bySat.has(sat.id)
				? [segmentTelemetry.bySat.get(sat.id).sensor]
				: [],
			telemetrySource: segmentTelemetry.bySat.has(sat.id)
				? 'segments.csv'
				: null,
			dataChannel: segmentTelemetry.bySat.get(sat.id)?.channel ?? null,
			dataTimestamp: null,
			dataSampleIndex: null,
			updatedAt: Date.now(),
		},
	]),
);

for (const id of SAT_IDS) {
	const ctx = sim_create_context(id);
	if (!ctx) {
		console.error(`[SISP] Failed to create context for sat ${id}`);
		process.exit(1);
	}
	ctxMap[id] = ctx;
}
console.log('[SISP] Created contexts for sats:', SAT_IDS.join(', '));
console.log(
	`[SISP] Loaded ${segmentTelemetry.loadedRows} segment rows from ${SEGMENTS_CSV_PATH}`,
);
console.log(
	'[SISP] CSV channel map:',
	segmentTelemetry.selectedChannels
		.map((item) => `sat ${item.satId}=${item.channel}`)
		.join(', '),
);

// ── Header decode (pure JS, matches encoder bit layout) ──────────────────────
function decodeHeader(frame) {
	const [b0, b1, b2, b3, b4] = frame;
	return {
		svc: (b0 >> 4) & 0x0f,
		sndr: ((b0 & 0x0f) << 4) | ((b1 >> 4) & 0x0f),
		rcvr: ((b1 & 0x0f) << 4) | ((b2 >> 4) & 0x0f),
		seq: ((b2 & 0x0f) << 4) | ((b3 >> 4) & 0x0f),
		degr: b3 & 0x0f,
		flags: (b4 >> 4) & 0x0f,
	};
}

// ── Build a minimal 64-byte frame ─────────────────────────────────────────────
function buildFrame(svc, sndr, rcvr, seq = 0, degr = 0, flags = 0) {
	const buf = Buffer.alloc(64, 0);
	buf[0] = ((svc & 0x0f) << 4) | ((sndr >> 4) & 0x0f);
	buf[1] = ((sndr & 0x0f) << 4) | ((rcvr >> 4) & 0x0f);
	buf[2] = ((rcvr & 0x0f) << 4) | ((seq >> 4) & 0x0f);
	buf[3] = ((seq & 0x0f) << 4) | (degr & 0x0f);
	buf[4] = (flags & 0x0f) << 4;
	return buf;
}

function scenarioFromState(state) {
	if (!state || state === 'IDLE') return null;
	if (state.startsWith('CORR_')) return 'CORR';
	if (state.startsWith('RELAY_')) return 'RELAY';
	if (state.startsWith('BORROW_')) return 'BORROW';
	if (state === 'CRITICAL_FAIL') return 'FAIL';
	return null;
}

function syncCxxStateToStore() {
	for (const id of SAT_IDS) {
		const current = satelliteStore.get(id) || { id };
		const rawState = sim_get_state(ctxMap[id]);
		const state = STATE_JS[rawState] ?? 'IDLE';
		satelliteStore.set(id, {
			...current,
			id,
			state,
			rawState,
			degr: sim_get_degr(ctxMap[id]),
			activeScenario: scenarioFromState(state),
			updatedAt: Date.now(),
		});
	}
}

function mergeSatelliteTelemetry(items) {
	if (!Array.isArray(items)) return;
	for (const item of items) {
		if (!item || !ctxMap[item.id]) continue;
		const current = satelliteStore.get(item.id) || { id: item.id };
		const {
			sensors: incomingSensors,
			state: _state,
			rawState: _rawState,
			degr: _degr,
			activeScenario: _activeScenario,
			...telemetry
		} = item;
		const hasRealSensorStream = segmentTelemetry.bySat.has(item.id);
		const merged = {
			...current,
			...telemetry,
			id: item.id,
			// C++ FSM state/degr are authoritative on the bridge.
			state: current.state,
			rawState: current.rawState,
			degr: current.degr,
			activeScenario: current.activeScenario,
			sensors: hasRealSensorStream
				? current.sensors
				: incomingSensors || current.sensors,
			telemetrySource: hasRealSensorStream
				? 'segments.csv'
				: current.telemetrySource,
			dataChannel: hasRealSensorStream ? current.dataChannel : null,
			dataTimestamp: hasRealSensorStream ? current.dataTimestamp : null,
			dataSampleIndex: hasRealSensorStream ? current.dataSampleIndex : null,
			updatedAt: Date.now(),
		};
		satelliteStore.set(item.id, merged);
	}
	syncCxxStateToStore();
}

function satelliteSnapshots() {
	syncCxxStateToStore();
	return SAT_IDS.map((id) => satelliteStore.get(id));
}

function rowToReading(stream, row) {
	return {
		value: row.value,
		ts_ms: row.ts_ms,
		source_timestamp: row.timestamp,
		channel: stream.channel,
		sample_index: stream.totalSamples,
		segment: row.segment,
		sampling: row.sampling,
		anomaly: row.anomaly,
		train: row.train,
	};
}

function applySegmentSample(stream, row, { triggerEvents = true } = {}) {
	const sensor = stream.sensor;
	const reading = rowToReading(stream, row);

	sensor.last_reading = reading;
	sensor.status = row.anomaly === 1 ? 'FAULT' : 'NOMINAL';
	sensor.current_segment = row.segment;
	sensor.source_timestamp = row.timestamp;
	sensor.sample_index = stream.totalSamples;
	sensor.history.push(reading);
	if (sensor.history.length > SENSOR_HISTORY_MAX) {
		sensor.history.splice(0, sensor.history.length - SENSOR_HISTORY_MAX);
	}

	if (row.anomaly === 1) {
		sensor._normalTicks = 0;
		sensor._anomalies.unshift({
			ts_ms: row.ts_ms,
			source_timestamp: row.timestamp,
			axis: 'value',
			value: row.value,
			segment: row.segment,
			sample_index: stream.totalSamples,
		});
		if (sensor._anomalies.length > 10) sensor._anomalies.pop();
	} else {
		sensor._normalTicks++;
	}

	const current = satelliteStore.get(stream.satId) || { id: stream.satId };
	satelliteStore.set(stream.satId, {
		...current,
		sensors: [sensor],
		telemetrySource: 'segments.csv',
		dataChannel: stream.channel,
		dataTimestamp: row.timestamp,
		dataSampleIndex: stream.totalSamples,
		updatedAt: Date.now(),
	});

	if (triggerEvents && row.anomaly === 1 && stream.lastAnomaly !== 1) {
		const ctx = ctxMap[stream.satId];
		if (ctx) sim_inject_event(ctx, EVT.FAULT_DETECTED);
	}
	stream.lastAnomaly = row.anomaly;
	stream.totalSamples++;
}

function consumeSegmentSample(stream, options) {
	if (!stream || stream.rows.length === 0) return false;
	if (stream.cursor >= stream.rows.length) {
		stream.cursor = 0;
		stream.lastAnomaly = 0;
	}
	const row = stream.rows[stream.cursor++];
	applySegmentSample(stream, row, options);
	stream.nextIntervalMs = sampleIntervalMs(stream.rows[stream.cursor] || row);
	return true;
}

function primeSegmentTelemetry(count = INITIAL_SENSOR_HISTORY) {
	for (const stream of segmentTelemetry.bySat.values()) {
		stream.sensor.history.length = 0;
		stream.sensor._anomalies.length = 0;
		stream.cursor = 0;
		stream.totalSamples = 0;
		stream.elapsedMs = 0;
		stream.lastAnomaly = 0;
		for (let i = 0; i < count && i < stream.rows.length; i++) {
			consumeSegmentSample(stream, { triggerEvents: false });
		}
	}
}

function advanceSegmentTelemetry(deltaMs) {
	if (segmentTelemetry.bySat.size === 0) return false;
	let changed = false;
	const ms = Math.max(0, Number(deltaMs) || 0);
	for (const stream of segmentTelemetry.bySat.values()) {
		stream.elapsedMs += ms;
		let samples = 0;
		while (
			stream.elapsedMs >= stream.nextIntervalMs &&
			samples < 120 &&
			stream.rows.length > 0
		) {
			stream.elapsedMs -= stream.nextIntervalMs;
			if (consumeSegmentSample(stream)) changed = true;
			samples++;
		}
	}
	return changed;
}

primeSegmentTelemetry();

// ── Frame queue (deferred routing to avoid reentrant C calls) ─────────────────
const frameQueue = [];

function drainQueue(maxFrames = 64) {
	let n = 0;
	while (frameQueue.length > 0 && n++ < maxFrames) {
		const { tgt, frame } = frameQueue.shift();
		if (ctxMap[tgt]) {
			const arr = new Uint8Array(frame);
			sim_inject_packet(ctxMap[tgt], arr, arr.length);
		}
	}
}

// Pre-allocated decode type — koffi can't decode with a runtime-dynamic length
// using the string form; use a fixed 128-byte array type instead.
const FRAME_ARRAY_TYPE = koffi.array('uint8', 128);

function copyCallbackBuf(buf, len) {
	// koffi may provide `buf` as a TypedArray view OR an opaque pointer.
	// Handle both so we always get a plain Buffer copy.
	if (
		buf &&
		typeof buf === 'object' &&
		(buf.buffer instanceof ArrayBuffer || ArrayBuffer.isView(buf))
	) {
		return Buffer.copyBytesFrom(buf, 0, len);
	}
	// Opaque pointer path — decode via pre-allocated array type
	try {
		const raw = koffi.decode(buf, FRAME_ARRAY_TYPE);
		return Buffer.from(raw.slice(0, len));
	} catch (_) {
		return null;
	}
}

// ── TX callback — fires synchronously inside sim_inject_event / sim_advance_time ─
const txCallback = koffi.register(function onTx(dst, buf, len) {
	const frame = copyCallbackBuf(buf, len);
	if (!frame || frame.length < 5) return;

	const { svc, sndr, rcvr, seq, degr, flags } = decodeHeader(frame);
	const svcName = SVC_NAME[svc] || `SVC_0x${svc.toString(16)}`;

	// Queue deferred injection to target(s) — avoids recursive C call
	const targets =
		rcvr === 0xff
			? SAT_IDS.filter((id) => id !== sndr)
			: ctxMap[rcvr]
				? [rcvr]
				: [];

	for (const tgt of targets) {
		frameQueue.push({ tgt, frame: Buffer.from(frame) });
	}

	// Notify all WebSocket clients about this frame
	broadcast({
		type: 'PACKET',
		ts: Date.now(),
		svc: svcName,
		from: sndr,
		to: rcvr === 0xff ? null : rcvr,
		seq,
		degr,
		flags,
		hex: frame.slice(0, 10).toString('hex'),
		len,
	});
}, 'sim_tx_cb *');

sim_register_tx_callback(txCallback);

// ── WebSocket server ──────────────────────────────────────────────────────────
const PORT = parsePort(process.env.SISP_PORT, 3001);
const HOST = process.env.SISP_HOST || undefined;
const hub = createWebSocketHub({ port: PORT, host: HOST, logger: console });

function sendError(ws, message, detail) {
	hub.sendJson(ws, {
		type: 'ERROR',
		message,
		detail,
		ts: Date.now(),
	});
}

function broadcast(msg) {
	hub.broadcast(msg);
}

function sendContext(ws, extra = {}) {
	const sats = satelliteSnapshots();
	hub.sendJson(ws, {
		type: 'CONTEXT',
		context: SATELLITE_CONTEXT,
		sats,
		satellites: sats,
		dataSource: segmentTelemetry.selectedChannels,
		ts: Date.now(),
		...extra,
	});
}

function broadcastState() {
	const sats = satelliteSnapshots();
	broadcast({
		type: 'STATE',
		sats,
		satellites: sats,
		context: SATELLITE_CONTEXT,
		dataSource: segmentTelemetry.selectedChannels,
	});
}

function broadcastSatellites() {
	const sats = satelliteSnapshots();
	broadcast({
		type: 'SATELLITES',
		sats,
		satellites: sats,
		context: SATELLITE_CONTEXT,
		dataSource: segmentTelemetry.selectedChannels,
		ts: Date.now(),
	});
}

hub.onConnection((ws, req) => {
	console.log(`[SISP] Frontend connected from ${req.socket.remoteAddress}`);
	sendContext(ws);

	ws.on('message', (raw) => {
		let msg;
		try {
			msg = JSON.parse(raw.toString());
		} catch (e) {
			sendError(ws, 'Invalid JSON message', e.message);
			return;
		}

		try {
			handleMessage(msg, ws);
		} catch (e) {
			console.error('[SISP] Message handler failed:', e);
			sendError(ws, 'Message handler failed', e?.message || String(e));
		}
	});
});

// ── Message handlers ──────────────────────────────────────────────────────────
function handleMessage(msg, ws) {
	switch (msg.type) {
		case 'TICK': {
			const ms = Math.min(Math.round(msg.deltaMs ?? 0), 60000);
			if (ms <= 0) break;
			for (const id of SAT_IDS) {
				sim_advance_time(ctxMap[id], ms);
			}
			advanceSegmentTelemetry(ms);
			drainQueue();
			broadcastSatellites();
			break;
		}

		case 'EVENT': {
			const { satId, event } = msg;
			if (!ctxMap[satId]) break;
			sim_inject_event(ctxMap[satId], event);
			drainQueue();
			broadcastSatellites();
			break;
		}

		case 'HEARTBEAT': {
			// Manually route HEARTBEAT frames — no per-context send-heartbeat event in C++ FSM
			const sndr = msg.satId;
			const degr = sim_get_degr(ctxMap[sndr] || ctxMap[1]) || 0;
			const frame = buildFrame(0x8, sndr, 0xff, 0, degr);
			const arr = new Uint8Array(frame);
			for (const id of SAT_IDS) {
				if (id === sndr) continue;
				sim_inject_packet(ctxMap[id], arr, arr.length);
				broadcast({
					type: 'PACKET',
					ts: Date.now(),
					svc: 'HEARTBEAT',
					from: sndr,
					to: id,
					seq: 0,
					degr,
					flags: 0,
					hex: frame.slice(0, 10).toString('hex'),
					len: 64,
				});
			}
			drainQueue();
			broadcastSatellites();
			break;
		}

		case 'STATUS': {
			const { satId } = msg;
			if (!ctxMap[satId]) break;
			// Trigger status by firing SENSOR_READ_DONE which lets the FSM respond
			sim_inject_event(ctxMap[satId], EVT.SENSOR_READ_DONE);
			drainQueue();
			broadcastSatellites();
			break;
		}

		case 'RESET': {
			frameQueue.length = 0;
			for (const id of SAT_IDS) {
				sim_inject_event(ctxMap[id], EVT.RESET);
			}
			primeSegmentTelemetry();
			drainQueue();
			broadcastSatellites();
			break;
		}

		case 'GET_CONTEXT': {
			if (msg.reply !== false && ws?.readyState === 1 /* OPEN */) {
				const target = msg.requestId
					? { requestId: msg.requestId }
					: {};
				sendContext(ws, target);
			}
			break;
		}

		case 'SATELLITE_TELEMETRY': {
			mergeSatelliteTelemetry(msg.sats || msg.satellites);
			broadcastSatellites();
			break;
		}
	}
}

// ── Keepalive state broadcast every 2s (catches timer-driven transitions) ─────
setInterval(() => {
	if (hub.clientCount() > 0) broadcastState();
}, 2000);

// ── Startup ───────────────────────────────────────────────────────────────────
let shuttingDown = false;

function destroyContexts() {
	for (const id of SAT_IDS) {
		const ctx = ctxMap[id];
		if (!ctx) continue;
		try {
			sim_destroy_context(ctx);
		} catch (e) {
			console.warn(`[SISP] Failed to destroy context for sat ${id}:`, e.message);
		}
	}
}

function shutdown(code = 0) {
	if (shuttingDown) return;
	shuttingDown = true;
	try {
		hub.close();
	} catch (_) {
		// Closing during process exit should never mask the original reason.
	}
	destroyContexts();
	process.exit(code);
}

process.once('SIGINT', () => shutdown(0));
process.once('SIGTERM', () => shutdown(0));

hub.listen()
	.then(({ url }) => {
		console.log(`[SISP] Bridge server listening on ${url}`);
		console.log('[SISP] DLL:', DLL_PATH);
	})
	.catch((e) => {
		if (e && e.code === 'EADDRINUSE') {
			console.error(
				`[SISP] Port ${PORT} is already in use. Close the other bridge or set SISP_PORT/VITE_SISP_WS_URL to a free port.`,
			);
		} else {
			console.error(
				'[SISP] Failed to start bridge server:',
				e && e.message ? e.message : e,
			);
		}
		destroyContexts();
		process.exit(1);
	});
