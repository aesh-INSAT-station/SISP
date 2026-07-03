import React from 'react';
import { useInsights } from '../hooks/useInsights.js';
import { useSatellite } from '../hooks/useSatellite.js';
import { useSISP } from '../context/SISPContext.jsx';
import {
  PANEL_BORDER, ACCENT, TEXT_SECONDARY, TEXT_DIM,
} from '../constants/index.js';
import { DraggablePanel } from './DraggablePanel.jsx';
import { HealthGrid } from './charts/HealthGrid.jsx';
import { Sparkline } from './charts/Sparkline.jsx';
import { EnergyBars } from './charts/EnergyBars.jsx';
import { PacketRate } from './charts/PacketRate.jsx';
import { LinkMatrix } from './charts/LinkMatrix.jsx';

export function InsightsPanel() {
  const snap = useInsights();
  const { selectedId } = useSISP();
  const sel = useSatellite(selectedId);

  if (!snap) return null;
  const insightsRect = {
    left: 16,
    top: 74,
    width: 264,
    height: Math.min(620, window.innerHeight - 148),
  };

  return (
    <DraggablePanel
      id="insights"
      title="Constellation"
      defaultRect={insightsRect}
      minWidth={244}
      minHeight={260}
      bodyStyle={{ fontSize: 11, color: '#94a3b8' }}
    >
      <Section title="CONSTELLATION HEALTH">
        <HealthGrid snap={snap} />
      </Section>

      <Section title={sel ? `DEGR · ${sel.name}` : 'DEGR TREND'}>
        {sel ? (
          <Sparkline series={sel.degrHistory} width={228} height={44} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {snap.sigs.map((s) => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 8 }}>
                <span style={{ width: 60, color: TEXT_SECONDARY, letterSpacing: '0.04em' }}>{s.name}</span>
                <Sparkline series={s.degrHistory} width={152} height={16} />
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="ENERGY">
        <EnergyBars snap={snap} />
      </Section>

      <Section title="PKT RATE · LAST 10 MIN">
        <PacketRate buckets={snap.buckets} />
      </Section>

      <Section title="LINK MATRIX">
        <LinkMatrix snap={snap} />
        <div style={{ fontSize: 8, color: TEXT_DIM, marginTop: 4, lineHeight: 1.5 }}>
          cyan=LOS · grey=occluded · amber=failure
        </div>
      </Section>
    </DraggablePanel>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ padding: '10px 14px', borderBottom: PANEL_BORDER }}>
      <div
        style={{
          fontSize: 8,
          color: ACCENT,
          marginBottom: 7,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          opacity: 0.7,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}
