import React from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { useSatellite } from '../hooks/useSatellite.js';
import { useScenarios } from '../hooks/useScenarios.js';
import { ScenarioBtn } from './ScenarioBtn.jsx';
import { PANEL_BG, PANEL_BORDER, FONT_MONO, TEXT_SECONDARY, PANEL_SHADOW, PANEL_RADIUS } from '../constants/index.js';

export function ScenarioBar() {
  const { selectedId } = useSISP();
  const sat = useSatellite(selectedId);
  const { injectFault, dropGroundLink, setLowEnergy, heartbeat, resetAll } = useScenarios();

  const enabled = !sat || sat.state === 'IDLE';
  const running = sat && sat.activeScenario;

	return (
		<div
			className="nuwa-scroll"
			style={{
        position: 'fixed',
        left: '50%',
        bottom: 14,
        transform: 'translateX(-50%)',
        width: 'min(980px, calc(100vw - 32px))',
        minHeight: 46,
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: PANEL_RADIUS,
        boxShadow: PANEL_SHADOW,
        display: 'flex',
        alignItems: 'center',
        padding: '0 14px',
        gap: 6,
        zIndex: 22,
        backdropFilter: 'blur(18px) saturate(130%)',
        overflowX: 'auto',
        overflowY: 'hidden',
        scrollbarWidth: 'thin',
      }}
    >
      <ScenarioBtn label="FAULT"     onClick={injectFault}    enabled={enabled} running={running === 'CORR'} />
      <ScenarioBtn label="GROUND LINK" onClick={dropGroundLink} enabled={enabled} running={running === 'RELAY'} />
      <ScenarioBtn label="LOW ENERGY" onClick={setLowEnergy}   enabled={enabled} running={running === 'RELAY'} />
      <ScenarioBtn label="PING"       onClick={heartbeat}      enabled={true}    running={false} />
      <ScenarioBtn label="RESET"      onClick={resetAll}       enabled={true}    running={false} />
      <div style={{ flex: 1 }} />
      <span style={{ fontSize: 9, color: TEXT_SECONDARY, letterSpacing: '0.10em', fontFamily: FONT_MONO, whiteSpace: 'nowrap', flexShrink: 0 }}>
        DRAG · ROTATE &nbsp;|&nbsp; CLICK · SELECT SAT
      </span>
    </div>
  );
}
