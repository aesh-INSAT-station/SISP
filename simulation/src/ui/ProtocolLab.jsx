import React, { useState, useEffect, useCallback } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import {
	PANEL_BG,
	PANEL_BORDER,
	PANEL_SHADOW,
	PANEL_RADIUS,
	FONT_MONO,
	TEXT_PRIMARY,
	TEXT_SECONDARY,
	TEXT_DIM,
	ACCENT,
	ACCENT_DIM,
	STATUS_GREEN,
	STATUS_AMBER,
	STATUS_RED,
	SERVICE_COLOR,
	SAT_CONFIG,
} from '../constants/index.js';

const FALLBACK_SATS = SAT_CONFIG.map(({ id, name, role }) => ({
	id,
	name,
	role,
	state: 'IDLE',
	degr: 0,
}));

const STATE_COLOR = {
	IDLE: '#00b9ff',
	CORR_WAIT_RSP: '#f5c518',
	CORR_COMPUTING: '#f5c518',
	RELAY_WAIT_ACCEPT: '#22d3ee',
	RELAY_ACTIVE: '#22d3ee',
	BORROW_WAIT_RSP: '#a78bfa',
	CRITICAL_FAIL: '#ff3d5a',
};

const SVC_COLOR = (svc) => SERVICE_COLOR[svc] || '#64748b';

function pad2(n) {
	return String(n).padStart(2, '0');
}
function fmtTs(ts) {
	const d = new Date(ts);
	return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`;
}

function ScenBtn({ label, color, onClick, disabled }) {
	const [flash, setFlash] = useState(false);
	const handleClick = () => {
		if (disabled) return;
		onClick();
		setFlash(true);
		setTimeout(() => setFlash(false), 300);
	};
	return (
		<button
			onClick={handleClick}
			style={{
				fontFamily: FONT_MONO,
				fontSize: 10,
				fontWeight: 700,
				letterSpacing: '0.08em',
				padding: '4px 10px',
				border: `1px solid ${disabled ? 'rgba(255,255,255,0.08)' : color}44`,
				borderRadius: 4,
				background: flash
					? color + '33'
					: disabled
						? 'rgba(255,255,255,0.03)'
						: 'rgba(255,255,255,0.04)',
				color: disabled ? TEXT_DIM : color,
				cursor: disabled ? 'default' : 'pointer',
				transition: 'background 0.15s',
				whiteSpace: 'nowrap',
				userSelect: 'none',
			}}
		>
			{label}
		</button>
	);
}

function StateBadge({ state }) {
	const c = STATE_COLOR[state] || '#64748b';
	return (
		<span
			style={{
				fontFamily: FONT_MONO,
				fontSize: 9,
				letterSpacing: '0.06em',
				color: c,
				background: c + '18',
				border: `1px solid ${c}44`,
				borderRadius: 3,
				padding: '1px 5px',
				whiteSpace: 'nowrap',
			}}
		>
			{state ?? 'IDLE'}
		</span>
	);
}

function FrameRow({ entry, satName }) {
	const color = SVC_COLOR(entry.svc);
	const fromName = entry.from ? satName(entry.from) : 'GND';
	const toName = entry.to ? satName(entry.to) : 'BCAST';
	return (
		<div
			style={{
				borderBottom: '1px solid rgba(255,255,255,0.04)',
				padding: '5px 10px',
				fontFamily: FONT_MONO,
				fontSize: 10,
				lineHeight: 1.5,
			}}
		>
			<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
				<span style={{ color: TEXT_DIM, flexShrink: 0, fontSize: 9 }}>
					{fmtTs(entry.ts)}
				</span>
				<span
					style={{
						color,
						background: color + '18',
						border: `1px solid ${color}44`,
						borderRadius: 3,
						padding: '0 5px',
						fontSize: 9,
						fontWeight: 700,
						letterSpacing: '0.06em',
						flexShrink: 0,
					}}
				>
					{entry.svc}
				</span>
				<span style={{ color: TEXT_SECONDARY }}>
					<span style={{ color: ACCENT }}>{fromName}</span>
					<span style={{ color: TEXT_DIM }}> → </span>
					<span style={{ color: TEXT_PRIMARY }}>{toName}</span>
				</span>
				<span style={{ marginLeft: 'auto', color: TEXT_DIM, fontSize: 9 }}>
					seq={entry.seq} degr={entry.degr}
				</span>
			</div>
			{entry.hex && (
				<div
					style={{
						color: TEXT_DIM,
						fontSize: 9,
						paddingTop: 1,
						letterSpacing: '0.04em',
					}}
				>
					{entry.hex.replace(/../g, '$& ').trim()} …
				</div>
			)}
		</div>
	);
}

export function ProtocolLab() {
	const { cppProtocol, ready } = useSISP();

	const [connected, setConnected] = useState(false);
	const [bridgeStatus, setBridgeStatus] = useState('connecting');
	const [log, setLog] = useState([]);
	const [satellites, setSatellites] = useState(FALLBACK_SATS);
	const [selectedSat, setSelectedSat] = useState(1);
	const [open, setOpen] = useState(true);
	const [hidden, setHidden] = useState(false);
	const [bridgeError, setBridgeError] = useState(null);

	// Subscribe to CppProtocol events
	useEffect(() => {
		if (!cppProtocol) return;
		setConnected(cppProtocol.connected);
		setBridgeStatus(
			cppProtocol.status || (cppProtocol.connected ? 'live' : 'connecting'),
		);
		setBridgeError(cppProtocol.lastError || null);
		setLog(cppProtocol.log.slice(0, 150));
		setSatellites(
			cppProtocol.satelliteList.length
				? cppProtocol.satelliteList
				: FALLBACK_SATS,
		);

		const unsub = cppProtocol.on((type, data) => {
			if (type === 'status') setBridgeStatus(data);
			if (type === 'connect') {
				setConnected(true);
				setBridgeStatus('live');
				setBridgeError(null);
			}
			if (type === 'disconnect') {
				setConnected(false);
				setBridgeStatus(cppProtocol.status || 'offline');
				setBridgeError(data?.error || cppProtocol.lastError || null);
			}
			if (type === 'error') {
				setBridgeError(
					data?.message || String(data || 'Bridge connection failed'),
				);
			}
			if (type === 'packet') {
				// Append to log — shallow copy to trigger re-render
				setLog((prev) => [data, ...prev].slice(0, 150));
			}
			if (type === 'state' || type === 'context' || type === 'satellites') {
				setSatellites(
					Array.isArray(data) && data.length ? data : FALLBACK_SATS,
				);
			}
		});

		return unsub;
	}, [cppProtocol]);

	useEffect(() => {
		if (!satellites.some((sat) => sat.id === selectedSat)) {
			setSelectedSat(satellites[0]?.id ?? 1);
		}
	}, [satellites, selectedSat]);

	const trigger = useCallback(
		(action) => {
			if (!cppProtocol || !connected) return;
			switch (action) {
				case 'CORRECTION':
					cppProtocol.triggerCorrection(selectedSat);
					break;
				case 'RELAY':
					cppProtocol.triggerRelay(selectedSat);
					break;
				case 'HEARTBEAT':
					cppProtocol.triggerHeartbeat(selectedSat);
					break;
				case 'FAILURE':
					cppProtocol.triggerFailure(selectedSat);
					break;
				case 'BORROW':
					cppProtocol.triggerStatus(selectedSat);
					break;
				case 'RESET':
					cppProtocol.resetAll();
					break;
			}
		},
		[cppProtocol, connected, selectedSat],
	);

	const clearLog = () => setLog([]);
	const satName = useCallback(
		(id) => {
			const sat =
				satellites.find((item) => item.id === id) ||
				SAT_CONFIG.find((item) => item.id === id);
			return sat?.name || `SAT-${id}`;
		},
		[satellites],
	);

	// Allow the Protocol Lab to show websocket bridge data even before the
	// 3D viewer is ready (so users can see bridge status/logs while the
	// globe initializes). Only respect explicit hide by the user.
	if (hidden) return null;

	const connecting = bridgeStatus === 'connecting' && !connected;
	const statusColor = connected
		? STATUS_GREEN
		: connecting
			? STATUS_AMBER
			: STATUS_RED;
	const statusText = connected
		? '● LIVE'
		: connecting
			? '◌ CONNECTING...'
			: '○ OFFLINE';
	const offlineText =
		bridgeError || 'Bridge offline. Retrying in the background.';

	return (
		<div
			style={{
				position: 'fixed',
				right: 14,
				top: '50%',
				transform: 'translateY(-50%)',
				width: 360,
				maxHeight: 'calc(100vh - 120px)',
				background: PANEL_BG,
				border: PANEL_BORDER,
				borderRadius: PANEL_RADIUS,
				boxShadow: PANEL_SHADOW,
				backdropFilter: 'blur(18px) saturate(130%)',
				zIndex: 30,
				display: 'flex',
				flexDirection: 'column',
				overflow: 'hidden',
				fontFamily: FONT_MONO,
			}}
		>
			{/* ── Header ── */}
			<div
				style={{
					display: 'flex',
					alignItems: 'center',
					padding: '8px 12px',
					borderBottom: '1px solid rgba(255,255,255,0.07)',
					gap: 8,
					flexShrink: 0,
				}}
			>
				<span
					style={{
						fontSize: 10,
						fontWeight: 700,
						letterSpacing: '0.12em',
						color: ACCENT,
					}}
				>
					PROTOCOL LAB
				</span>
				<span style={{ fontSize: 9, letterSpacing: '0.06em', color: TEXT_DIM }}>
					C++ SISP ENGINE
				</span>
				<div
					style={{
						marginLeft: 'auto',
						display: 'flex',
						alignItems: 'center',
						gap: 6,
					}}
				>
					{/* Connection indicator */}
					<span
						style={{
							fontSize: 9,
							color: statusColor,
							letterSpacing: '0.06em',
						}}
					>
						{statusText}
					</span>
					<button
						onClick={() => setOpen((o) => !o)}
						style={{
							background: 'none',
							border: 'none',
							cursor: 'pointer',
							color: TEXT_SECONDARY,
							fontSize: 12,
							lineHeight: 1,
							padding: '0 2px',
						}}
						title={open ? 'Collapse' : 'Expand'}
					>
						{open ? '−' : '+'}
					</button>
					<button
						onClick={() => setHidden(true)}
						style={{
							background: 'none',
							border: 'none',
							cursor: 'pointer',
							color: TEXT_DIM,
							fontSize: 10,
							lineHeight: 1,
							padding: '0 2px',
							fontFamily: FONT_MONO,
							letterSpacing: '0.08em',
						}}
						title="Hide Protocol Lab"
					>
						HIDE
					</button>
				</div>
			</div>

			{open && (
				<>
					{/* ── Satellite selector + trigger buttons ── */}
					<div
						style={{
							padding: '8px 10px',
							borderBottom: '1px solid rgba(255,255,255,0.07)',
							display: 'flex',
							flexWrap: 'wrap',
							alignItems: 'center',
							gap: 6,
							flexShrink: 0,
						}}
					>
						<select
							value={selectedSat}
							onChange={(e) => setSelectedSat(Number(e.target.value))}
							style={{
								fontFamily: FONT_MONO,
								fontSize: 10,
								background: 'rgba(0,185,255,0.08)',
								border: `1px solid ${ACCENT}44`,
								borderRadius: 4,
								color: TEXT_PRIMARY,
								padding: '3px 6px',
								cursor: 'pointer',
								outline: 'none',
							}}
						>
							{satellites.map((sat) => (
								<option
									key={sat.id}
									value={sat.id}
									style={{ background: '#020712' }}
								>
									{sat.name || `SAT-${sat.id}`}
								</option>
							))}
						</select>
						<ScenBtn
							label="CORR"
							color={SERVICE_COLOR.CORRECTION_REQ}
							onClick={() => trigger('CORRECTION')}
							disabled={!connected}
						/>
						<ScenBtn
							label="RELAY"
							color={SERVICE_COLOR.RELAY_REQ}
							onClick={() => trigger('RELAY')}
							disabled={!connected}
						/>
						<ScenBtn
							label="PING"
							color={SERVICE_COLOR.HEARTBEAT}
							onClick={() => trigger('HEARTBEAT')}
							disabled={!connected}
						/>
						<ScenBtn
							label="FAIL"
							color={SERVICE_COLOR.FAILURE}
							onClick={() => trigger('FAILURE')}
							disabled={!connected}
						/>
						<ScenBtn
							label="RESET"
							color={TEXT_SECONDARY}
							onClick={() => trigger('RESET')}
							disabled={!connected}
						/>
					</div>

					{/* ── Satellite state grid ── */}
					<div
						style={{
							padding: '6px 10px',
							borderBottom: '1px solid rgba(255,255,255,0.07)',
							display: 'flex',
							flexWrap: 'wrap',
							gap: '4px 6px',
							flexShrink: 0,
						}}
					>
						{satellites.map((s) => {
							return (
								<div
									key={s.id}
									style={{ display: 'flex', alignItems: 'center', gap: 4 }}
								>
									<span style={{ fontSize: 9, color: TEXT_DIM }}>
										{s.name || `SAT-${s.id}`}
									</span>
									<StateBadge state={s?.state ?? 'IDLE'} />
									{s && (
										<span style={{ fontSize: 9, color: TEXT_DIM }}>
											d{s.degr}
										</span>
									)}
								</div>
							);
						})}
					</div>

					{/* ── Frame trace header ── */}
					<div
						style={{
							display: 'flex',
							alignItems: 'center',
							padding: '5px 10px',
							borderBottom: '1px solid rgba(255,255,255,0.07)',
							flexShrink: 0,
						}}
					>
						<span
							style={{ fontSize: 9, color: TEXT_DIM, letterSpacing: '0.10em' }}
						>
							FRAME TRACE ({log.length})
						</span>
						<button
							onClick={clearLog}
							style={{
								marginLeft: 'auto',
								background: 'none',
								border: 'none',
								cursor: 'pointer',
								color: TEXT_DIM,
								fontSize: 9,
								fontFamily: FONT_MONO,
								letterSpacing: '0.06em',
							}}
						>
							CLR
						</button>
					</div>

					{/* ── Scrollable frame list ── */}
					<div
						className="nuwa-scroll"
						style={{
							flex: 1,
							overflowY: 'auto',
							minHeight: 0,
						}}
					>
						{log.length === 0 ? (
							<div
								style={{
									padding: '20px 12px',
									textAlign: 'center',
									color: TEXT_DIM,
									fontSize: 10,
									letterSpacing: '0.06em',
								}}
							>
								{connected
									? 'Trigger a scenario to see C++ frames'
									: connecting
										? 'Connecting to the bridge server...'
										: offlineText}
							</div>
						) : (
							log.map((entry, i) => (
								<FrameRow key={i} entry={entry} satName={satName} />
							))
						)}
					</div>
				</>
			)}
		</div>
	);
}
