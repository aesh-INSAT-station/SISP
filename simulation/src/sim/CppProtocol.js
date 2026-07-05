const DEV_WS_URL =
	typeof window !== 'undefined'
		? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:3001`
		: 'ws://127.0.0.1:3001';
const WS_URL =
	import.meta.env?.VITE_SISP_WS_URL ||
	(import.meta.env?.DEV ? DEV_WS_URL : 'ws://localhost:3001');
const RECONNECT_DELAY_MS = 2000;
const CONNECT_TIMEOUT_MS = 5000;
const MAX_RECONNECT_DELAY_MS = 10000;
const LOG_CAP = 300;
const TELEMETRY_INTERVAL_MS = 750;
const SERVER_SENSOR_HISTORY_MAX = 200;

// Event values matching server/index.js and sisp_state_machine.hpp
export const CPP_EVT = {
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
};

// Maps C++ service names to the JS SERVICE_COLOR keys (for packet animation)
const SVC_TO_JS_SERVICE = {
	CORRECTION_REQ: 'CORRECTION_REQ',
	CORRECTION_RSP: 'CORRECTION_RSP',
	RELAY_REQ: 'RELAY_REQ',
	RELAY_ACCEPT: 'RELAY_ACCEPT',
	RELAY_REJECT: 'RELAY_REJECT',
	DOWNLINK_DATA: 'DOWNLINK_DATA',
	DOWNLINK_ACK: 'DOWNLINK_ACK',
	STATUS_BROADCAST: 'STATUS_BROADCAST',
	HEARTBEAT: 'HEARTBEAT',
	HEARTBEAT_ACK: 'HEARTBEAT',
	BORROW_DECISION: 'BORROW_RSP',
	BORROW_REQ: 'BORROW_REQ',
	FAILURE: 'FAILURE',
};

export class CppProtocol {
	constructor() {
		this._ws = null;
		this.connected = false;
		this.status = 'connecting'; // 'connecting' | 'live' | 'offline'
		this.lastError = null;
		this.wsUrl = WS_URL;
		this.log = []; // CppLogEntry[]
		this.satStates = {}; // satId → { state, degr, rawState }
		this.satellites = {}; // satId → server-authoritative satellite snapshot
		this.satelliteList = []; // ordered server context + latest state
		this.context = []; // static constellation context from server
		this.dataSource = []; // server CSV channel assignments
		this._listeners = new Set();
		this._jsProtocol = null; // set by attachProtocol
		this._simClock = null;
		this._lastSimTime = null;
		this._clockUnsub = null;
		this._reconnTimer = null;
		this._connectTimer = null;
		this._retryAttempt = 0;
		this._telemetryTimer = null;
		this._destroyed = false;
		this._socketSeq = 0;
		this._tickAccum = 0; // accumulated sim-ms, flushed in batches
		this._pktId = 10000; // packet id namespace separate from JS protocol
		// Helpful debug: show where the C++ bridge will be contacted
		if (typeof window !== 'undefined' && window.console) {
			console.debug('[SISP] CppProtocol connecting to', this.wsUrl);
		}
		this._connect();
	}

	// ── Attach the JS engine protocol so C++ packets get visually animated ──────
	attachProtocol(jsProtocol) {
		this._jsProtocol = jsProtocol;
		this._applyServerSatellitesToEngine();
		this._startTelemetry();
	}

	// ── Attach SimClock to drive C++ timers in lockstep with the sim ─────────────
	attachClock(simClock) {
		if (this._clockUnsub) this._clockUnsub();
		this._simClock = simClock;
		this._lastSimTime = simClock.currentTime;
		this._clockUnsub = simClock.onTick((simTime, _mult, playing) => {
			if (!playing || this._lastSimTime === null) {
				this._lastSimTime = simTime;
				return;
			}
			const deltaSec = simTime - this._lastSimTime;
			this._lastSimTime = simTime;
			if (deltaSec <= 0) return;
			// Accumulate and send in 500 ms sim-time batches to limit WS traffic
			this._tickAccum += deltaSec * 1000;
			if (this._tickAccum >= 500) {
				this._send({ type: 'TICK', deltaMs: Math.round(this._tickAccum) });
				this._tickAccum = 0;
			}
		});
	}

	// ── Scenario triggers ─────────────────────────────────────────────────────────
	triggerCorrection(satId) {
		this._send({ type: 'EVENT', satId, event: CPP_EVT.FAULT_DETECTED });
	}

	triggerRelay(satId) {
		this._send({ type: 'EVENT', satId, event: CPP_EVT.ENERGY_LOW });
	}

	triggerHeartbeat(satId) {
		this._send({ type: 'HEARTBEAT', satId });
	}

	triggerFailure(satId) {
		this._send({ type: 'EVENT', satId, event: CPP_EVT.CRITICAL_FAILURE });
	}

	triggerStatus(satId) {
		this._send({ type: 'STATUS', satId });
	}

	resetAll() {
		this._send({ type: 'RESET' });
	}

	// ── Subscribe to events ──────────────────────────────────────────────────────
	// fn(type, data) where type is 'status' | 'connect' | 'disconnect' | 'error' | 'packet' | 'state'
	on(fn) {
		this._listeners.add(fn);
		return () => this._listeners.delete(fn);
	}

	// ── Internal ──────────────────────────────────────────────────────────────────
	_connect() {
		if (this._destroyed) return;
		this._setStatus('connecting');
		if (this._reconnTimer) {
			clearTimeout(this._reconnTimer);
			this._reconnTimer = null;
		}
		if (this._ws) {
			this._closeSocket(this._ws);
			this._ws = null;
		}

		let ws;
		try {
			ws = new WebSocket(WS_URL);
		} catch (e) {
			this._scheduleReconnect(`Invalid bridge URL: ${e?.message || String(e)}`);
			return;
		}

		const socketSeq = ++this._socketSeq;
		this._ws = ws;
		this._connectTimer = setTimeout(() => {
			if (
				this._destroyed ||
				socketSeq !== this._socketSeq ||
				ws.readyState !== WebSocket.CONNECTING
			)
				return;
			this.lastError = `Bridge connection timed out after ${CONNECT_TIMEOUT_MS / 1000}s (${WS_URL})`;
			this._emit('error', { message: this.lastError, url: WS_URL });
			try {
				ws.close();
			} catch (_) {}
		}, CONNECT_TIMEOUT_MS);

		ws.onopen = () => {
			if (this._destroyed || socketSeq !== this._socketSeq) {
				this._closeSocket(ws);
				return;
			}
			this._clearConnectTimer();
			this.connected = true;
			this.lastError = null;
			this._retryAttempt = 0;
			this._setStatus('live');
			this._emit('connect', null);
			this._send({ type: 'GET_CONTEXT' });
			this.publishSatelliteTelemetry();
			console.debug('[SISP] CppProtocol: websocket open, sent GET_CONTEXT');
		};

		ws.onclose = (ev) => {
			if (socketSeq !== this._socketSeq) return;
			this._clearConnectTimer();
			this.connected = false;
			this._ws = null;
			if (this._destroyed) {
				this._setStatus('offline');
				this._emit('disconnect', null);
				return;
			}
			const closeInfo = ev?.code
				? `Bridge disconnected (code ${ev.code})`
				: 'Bridge disconnected';
			this._scheduleReconnect(this.lastError || closeInfo);
			console.debug('[SISP] CppProtocol: websocket closed', ev && ev.code);
		};

		ws.onerror = () => {
			if (socketSeq !== this._socketSeq) return;
			this.lastError = `Cannot reach SISP bridge at ${WS_URL}`;
			this._setStatus('offline');
			this._emit('error', { message: this.lastError, url: WS_URL });
			console.debug('[SISP] CppProtocol: websocket error', this.lastError);
		};

		ws.onmessage = (ev) => {
			if (socketSeq !== this._socketSeq) return;
			let msg;
			try {
				msg = JSON.parse(ev.data);
			} catch (_) {
				return;
			}
			console.debug('[SISP] CppProtocol: received message', msg && msg.type);
			this._handleMessage(msg);
		};
	}

	_handleMessage(msg) {
		if (msg.type === 'ERROR') {
			this.lastError = msg.message || msg.detail || 'Bridge reported an error';
			this._emit('error', {
				message: this.lastError,
				detail: msg.detail,
				ts: msg.ts,
			});
		} else if (msg.type === 'PACKET') {
			this._addLogEntry(msg);
			// Push into JS protocol packet list for visual animation
			this._injectJsPacket(msg);
			this._emit('packet', msg);
		} else if (
			msg.type === 'CONTEXT' ||
			msg.type === 'SATELLITES' ||
			msg.type === 'STATE'
		) {
			if (Array.isArray(msg.dataSource))
				this.dataSource = msg.dataSource.slice();
			this._setServerSatellites(
				msg.sats || msg.satellites || [],
				msg.context || null,
			);
			if (msg.type === 'CONTEXT') this._emit('context', this.satelliteList);
			this._emit('state', this.satelliteList);
			this._emit('satellites', this.satelliteList);
		}
	}

	_setServerSatellites(sats, context = null) {
		if (Array.isArray(context)) this.context = context.slice();
		if (!Array.isArray(sats)) return;

		const nextStates = { ...this.satStates };
		const nextSats = { ...this.satellites };
		for (const s of sats) {
			if (!s || s.id == null) continue;
			nextStates[s.id] = { state: s.state, degr: s.degr, rawState: s.rawState };
			nextSats[s.id] = { ...(nextSats[s.id] || {}), ...s };
		}
		this.satStates = nextStates;
		this.satellites = nextSats;

		const orderedIds = (this.context.length ? this.context : sats)
			.map((s) => s.id)
			.filter((id, idx, arr) => id != null && arr.indexOf(id) === idx);
		this.satelliteList = orderedIds.map((id) => nextSats[id]).filter(Boolean);
		this._applyServerSatellitesToEngine();
	}

	_applyServerSatellitesToEngine() {
		const engine = this._jsProtocol?.engine;
		if (!engine || this.satelliteList.length === 0) return;

		for (const serverSat of this.satelliteList) {
			const sat = engine.getSat(serverSat.id);
			if (!sat) continue;
			this._copyIfPresent(serverSat, sat, [
				'name',
				'role',
				'state',
				'degr',
				'energy',
				'uptime_s',
				'orbit_error_m',
				'seq',
				'degr_k',
				'degr_svd',
				'degr_age',
				'degr_orbit',
				'degr_alt',
				'activeScenario',
				'pulseUntil',
				'inSunlight',
				'telemetrySource',
				'dataChannel',
				'dataTimestamp',
				'dataSampleIndex',
			]);
			this._applyServerSensorsToEngine(serverSat, sat);
		}
	}

	_applyServerSensorsToEngine(serverSat, sat) {
		if (!Array.isArray(serverSat.sensors)) return;

		const existing = new Map(
			(sat.sensors || []).map((sensor) => [sensor.id, sensor]),
		);
		sat.telemetrySource = serverSat.telemetrySource || 'server';

		sat.sensors = serverSat.sensors.map((serverSensor) => {
			const local = existing.get(serverSensor.id) || {};
			const history = Array.isArray(serverSensor.history)
				? serverSensor.history
						.slice(-SERVER_SENSOR_HISTORY_MAX)
						.map((reading) => ({ ...reading }))
				: this._nextSensorHistory(local, serverSensor.last_reading);
			const anomalies = Array.isArray(serverSensor._anomalies)
				? serverSensor._anomalies.map((item) => ({ ...item }))
				: Array.isArray(serverSensor.anomalies)
					? serverSensor.anomalies.map((item) => ({ ...item }))
					: local._anomalies || [];

			return {
				...local,
				...serverSensor,
				last_reading: serverSensor.last_reading
					? { ...serverSensor.last_reading }
					: null,
				history,
				_anomalies: anomalies,
				_normalTicks: serverSensor._normalTicks ?? local._normalTicks ?? 0,
			};
		});
	}

	_nextSensorHistory(localSensor, reading) {
		const history = Array.isArray(localSensor.history)
			? localSensor.history.slice()
			: [];
		if (!reading) return history;
		const last = history[history.length - 1];
		const lastKey = last?.sample_index ?? last?.source_timestamp ?? last?.ts_ms;
		const nextKey =
			reading.sample_index ?? reading.source_timestamp ?? reading.ts_ms;
		if (lastKey !== nextKey) {
			history.push({ ...reading });
			if (history.length > SERVER_SENSOR_HISTORY_MAX) {
				history.splice(0, history.length - SERVER_SENSOR_HISTORY_MAX);
			}
		}
		return history;
	}

	_copyIfPresent(src, dst, keys) {
		for (const key of keys) {
			if (
				Object.prototype.hasOwnProperty.call(src, key) &&
				src[key] !== undefined
			) {
				dst[key] = src[key];
			}
		}
	}

	_startTelemetry() {
		if (this._telemetryTimer || !this._jsProtocol?.engine) return;
		this._telemetryTimer = setInterval(
			() => this.publishSatelliteTelemetry(),
			TELEMETRY_INTERVAL_MS,
		);
		this.publishSatelliteTelemetry();
	}

	publishSatelliteTelemetry() {
		const engine = this._jsProtocol?.engine;
		if (!engine) return;
		const sats = engine.sats.map((sat) =>
			this._snapshotSatForServer(sat, engine),
		);
		this._send({ type: 'SATELLITE_TELEMETRY', sats });
	}

	_snapshotSatForServer(sat, engine) {
		const geo = engine.geodetic(sat);
		return {
			id: sat.id,
			name: sat.name,
			role: sat.role,
			state: sat.state,
			degr: sat.degr,
			energy: sat.energy,
			uptime_s: sat.uptime_s,
			orbit_error_m: sat.orbit_error_m,
			seq: sat.seq,
			degr_k: sat.degr_k,
			degr_svd: sat.degr_svd,
			degr_age: sat.degr_age,
			degr_orbit: sat.degr_orbit,
			degr_alt: sat.degr_alt,
			activeScenario: sat.activeScenario,
			pulseUntil: sat.pulseUntil,
			inSunlight: sat.inSunlight,
			lat_deg: geo?.lat_deg ?? null,
			lon_deg: geo?.lon_deg ?? null,
			alt_km: geo?.alt_km ?? sat.altitude_km,
			sensors: (sat.sensors || []).map((sensor) => ({
				id: sensor.id,
				type: sensor.type,
				label: sensor.label,
				active: sensor.active,
				status: sensor.status,
				unit: sensor.unit,
				last_reading: sensor.last_reading ? { ...sensor.last_reading } : null,
			})),
			logCount: sat.log?.length || 0,
		};
	}

	_injectJsPacket(msg) {
		if (!this._jsProtocol || !this._simClock) return;
		const engine = this._jsProtocol.engine;
		if (!engine) return;

		const fromSat = msg.from ? engine.getSat(msg.from) : null;
		const toSat = msg.to ? engine.getSat(msg.to) : null;
		const service = SVC_TO_JS_SERVICE[msg.svc] || 'STATUS_BROADCAST';

		// Create a lightweight packet object matching the shape PacketAnimator expects
		const pkt = {
			id: this._pktId++,
			from: fromSat,
			to: toSat,
			service,
			startSimTime: null, // set by _dispatchOrQueue
			duration_s: 1.2,
			onArrive: null,
			seq: msg.seq ?? 0,
			_fromCpp: true,
		};

		// TX log only — onPacketArrive (called by ThreeGlobe) handles the RX side
		if (fromSat) {
			this._jsProtocol._log(
				fromSat,
				'TX',
				service,
				toSat ? toSat.id : 0x00,
				pkt.seq,
			);
		}

		this._jsProtocol._dispatchOrQueue(pkt);
	}

	_addLogEntry(msg) {
		this.log.unshift({
			ts: Date.now(),
			svc: msg.svc,
			from: msg.from,
			to: msg.to,
			seq: msg.seq,
			degr: msg.degr,
			flags: msg.flags,
			hex: msg.hex,
			len: msg.len,
		});
		if (this.log.length > LOG_CAP) this.log.length = LOG_CAP;
	}

	_send(msg) {
		if (this._ws && this._ws.readyState === WebSocket.OPEN) {
			try {
				this._ws.send(JSON.stringify(msg));
			} catch (e) {
				this.lastError = `Bridge send failed: ${e?.message || String(e)}`;
				this._emit('error', { message: this.lastError });
				this._closeSocket(this._ws);
				this._ws = null;
				this._scheduleReconnect(this.lastError);
			}
		}
	}

	_emit(type, data) {
		this._listeners.forEach((fn) => {
			try {
				fn(type, data);
			} catch (_) {}
		});
	}

	_setStatus(status) {
		if (this.status === status) return;
		this.status = status;
		this._emit('status', status);
	}

	_closeSocket(ws) {
		if (!ws) return;
		try {
			ws.onmessage = null;
			ws.onerror = null;
			if (ws.readyState === WebSocket.CONNECTING) {
				ws.onopen = () => {
					try {
						ws.close();
					} catch (_) {}
				};
				ws.onclose = null;
				return;
			}
			ws.onopen = null;
			ws.onclose = null;
			if (
				ws.readyState === WebSocket.OPEN ||
				ws.readyState === WebSocket.CLOSING
			) {
				ws.close();
			}
		} catch (_) {}
	}

	_clearConnectTimer() {
		if (!this._connectTimer) return;
		clearTimeout(this._connectTimer);
		this._connectTimer = null;
	}

	_scheduleReconnect(reason) {
		if (this._destroyed) return;
		this._clearConnectTimer();
		if (reason) {
			this.lastError = reason;
			this._emit('error', { message: reason, url: WS_URL });
		}

		this.connected = false;
		this._setStatus('offline');
		this._emit('disconnect', { error: this.lastError });

		const delay = Math.min(
			RECONNECT_DELAY_MS * Math.max(1, this._retryAttempt + 1),
			MAX_RECONNECT_DELAY_MS,
		);
		this._retryAttempt++;

		if (this._reconnTimer) clearTimeout(this._reconnTimer);
		this._reconnTimer = setTimeout(() => this._connect(), delay);
	}

	destroy() {
		this._destroyed = true;
		this._socketSeq++;
		this.connected = false;
		this._setStatus('offline');
		if (this._clockUnsub) this._clockUnsub();
		if (this._reconnTimer) clearTimeout(this._reconnTimer);
		this._clearConnectTimer();
		if (this._telemetryTimer) clearInterval(this._telemetryTimer);
		if (this._ws) this._closeSocket(this._ws);
		this._ws = null;
	}
}
