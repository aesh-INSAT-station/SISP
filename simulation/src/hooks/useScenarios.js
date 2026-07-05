import { useSISP } from '../context/SISPContext.jsx';

export function useScenarios() {
  const { refs, ready, getSelectedId, cppProtocol } = useSISP();

  const noop = () => {};
  if (!ready) {
    return {
      injectFault: noop,
      dropGroundLink: noop,
      setLowEnergy: noop,
      heartbeat: noop,
      resetAll: noop,
    };
  }

  const { engine, protocol } = refs.current;
  const liveCpp = cppProtocol?.connected ? cppProtocol : null;
  const firstIdle = () => engine.sats.find((sat) => sat.state === 'IDLE') || engine.sats[0];
  const firstByRole = (role) => engine.sats.find((sat) => sat.role === role && sat.state === 'IDLE') || firstIdle();
  const targetId = (fallbackSat = firstIdle()) => {
    const sid = getSelectedId();
    return sid || fallbackSat?.id;
  };

  return {
    injectFault: () => {
      const id = targetId(firstByRole('SCIENCE'));
      liveCpp ? liveCpp.triggerCorrection(id) : protocol.triggerCorrection(id);
    },
    dropGroundLink: () => {
      const id = targetId(firstByRole('COMMS'));
      liveCpp ? liveCpp.triggerRelay(id) : protocol.triggerRelay(id);
    },
    setLowEnergy: () => {
      const t = targetId(firstByRole('COMMS'));
      const s = engine.getSat(t);
      if (s) s.energy = 15;
      if (liveCpp) {
        liveCpp.publishSatelliteTelemetry();
        liveCpp.triggerRelay(t);
      } else {
        protocol.triggerRelay(t);
      }
    },
    heartbeat: () => {
      const id = targetId(engine.sats[0]);
      liveCpp ? liveCpp.triggerHeartbeat(id) : protocol.triggerHeartbeat(id);
    },
    resetAll: () => {
      liveCpp ? liveCpp.resetAll() : protocol.resetAll();
    },
  };
}
