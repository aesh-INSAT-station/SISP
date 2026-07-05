import React from 'react';
import { SISPProvider, useSISP } from './context/SISPContext.jsx';
import { ThreeGlobe } from './threejs/ThreeGlobe.jsx';
import { InsightsPanel } from './ui/InsightsPanel.jsx';
import { SatellitePanel } from './ui/SatellitePanel.jsx';
import { SatelliteListPanel } from './ui/SatelliteListPanel.jsx';
import { ScenarioBar } from './ui/ScenarioBar.jsx';
import { PlaybackBar } from './ui/PlaybackBar.jsx';
import { EventLogDrawer } from './ui/EventLogDrawer.jsx';
import { NuwaHeader } from './ui/NuwaHeader.jsx';
import { ProtocolLab } from './ui/ProtocolLab.jsx';
import { SensorGraphPanel } from './ui/SensorGraphPanel.jsx';
import { FONT_MONO, NUWA_BG } from './constants/index.js';

export default function SISPNetworkVisualizer() {
	return (
		<SISPProvider>
			<Shell />
		</SISPProvider>
	);
}

function Shell() {
	const { onViewerReady, setSelectedId, setCameraMode, getSelectedId, ready } =
		useSISP();

	const onSelect = (id) => {
		setSelectedId(id);
		setCameraMode(id != null ? 'TRACK' : 'FREE');
	};

	return (
		<div
			style={{
				position: 'fixed',
				inset: 0,
				background: NUWA_BG,
				color: '#d4eeff',
				fontFamily: FONT_MONO,
				overflow: 'hidden',
			}}
		>
			<ThreeGlobe
				onReady={onViewerReady}
				onSelect={onSelect}
				getSelectedId={getSelectedId}
			/>
			<NuwaHeader />
			<ProtocolLab />
			{ready && (
				<>
					<InsightsPanel />
					<SatelliteListPanel />
					<SatellitePanel />
					<SensorGraphPanel />
					<EventLogDrawer />
					<PlaybackBar />
					<ScenarioBar />
				</>
			)}
		</div>
	);
}
