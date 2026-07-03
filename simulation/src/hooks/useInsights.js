import { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { losBetween } from '../utils/los.js';

const POLL_MS = 500;

function buildSnapshot(engine, protocol, simSec) {
  const sats = engine.sats;
  const avgDegr    = sats.reduce((s, x) => s + x.degr, 0) / sats.length;
  const fleetHealth = Math.max(0, Math.min(100, 100 - (avgDegr / 15) * 100));
  const totalPkts  = protocol.packetCount || 0;
  const relayLoad  = totalPkts > 0 ? Math.round((protocol.relayCount / totalPkts) * 100) : 0;

  const sigs = sats.map((sat) => ({
    id:         sat.id,
    name:       sat.name,
    state:      sat.state,
    energy:     sat.energy,
    inSunlight: sat.inSunlight,
    degr:       sat.degr,
    pulse:      sat.pulseUntil > simSec,   // fixed: was > Date.now()
    degrHistory: sat.degrHistory ? sat.degrHistory.slice() : [],
  }));

  const N   = sats.length;
  const ids = sats.map((s) => s.id);
  const matrix   = Array.from({ length: N }, () => new Array(N).fill(false));
  const failures = Array.from({ length: N }, () => new Array(N).fill(false));
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const ok = losBetween(sats[i].currentPos, sats[j].currentPos);
      matrix[i][j] = ok; matrix[j][i] = ok;
      if (protocol.hasRecentLinkFailure(sats[i].id, sats[j].id)) {
        failures[i][j] = true; failures[j][i] = true;
      }
    }
  }

  return {
    fleetHealth, avgDegr, totalPkts,
    failureCount:   protocol.failureCount || 0,
    relayLoad,
    activeScenarios: protocol.activeScenarios || 0,
    sigs, ids, matrix, failures,
    buckets: protocol.packetBuckets ? protocol.packetBuckets.slice() : [],
  };
}

export function useInsights() {
  const { refs, ready } = useSISP();
  const [snap, setSnap] = useState(null);

  useEffect(() => {
    if (!ready) return;
    const { engine, protocol, simClock } = refs.current;
    const update = () => setSnap(buildSnapshot(engine, protocol, simClock.currentTime));
    update();
    const id = setInterval(update, POLL_MS);
    return () => clearInterval(id);
  }, [ready, refs]);

  return snap;
}
