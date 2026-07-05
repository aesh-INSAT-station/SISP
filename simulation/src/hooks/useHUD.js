import { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';

// Sim epoch as UTC ms — matches ProtocolService._simNowMs().
const SIM_EPOCH_MS = 1735689600000;

function fmtSimTime(simSec) {
  if (simSec == null) return '— UTC';
  const d = new Date(SIM_EPOCH_MS + simSec * 1000);
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

export function useHUD(intervalMs = 300) {
  const { refs, ready } = useSISP();
  const [hud, setHud] = useState({
    packetCount: 0,
    scenarios: 0,
    health: [],
    multiplier: 60,
    isPlaying: true,
    simTime: '',
    simTimeMs: 0,
  });

  useEffect(() => {
    if (!ready) return;
    const { engine, protocol, simClock } = refs.current;
    const update = () => {
      const simSec = simClock.currentTime;
      const nowMs  = SIM_EPOCH_MS + simSec * 1000;
      setHud({
        packetCount: protocol.packetCount,
        scenarios:   protocol.activeScenarios,
        health: engine.sats.map((s) => ({
          id:    s.id,
          state: s.state,
          pulse: s.pulseUntil > simSec,
        })),
        multiplier: simClock.multiplier,
        isPlaying:  simClock.isPlaying,
        simTime:    fmtSimTime(simSec),
        simTimeMs:  nowMs,
      });
    };
    update();
    const id = setInterval(update, intervalMs);
    return () => clearInterval(id);
  }, [ready, refs, intervalMs]);

  return hud;
}
