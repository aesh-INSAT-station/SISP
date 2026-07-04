import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { CppProtocol } from '../sim/CppProtocol.js';

const SISPContext = createContext(null);

export function SISPProvider({ children }) {
  const [selectedId, setSelectedId] = useState(null);
  const [cameraMode, setCameraMode] = useState('FREE'); // 'TRACK' | 'FREE'
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [logFilter, setLogFilter] = useState('ALL');

  // { satelliteId, sensorId } | null — drives the sensor graph panel
  const [selectedSensor, setSelectedSensor] = useState(null);

  const selectedIdRef = useRef(null);
  const cameraModeRef = useRef('FREE');
  const refsRef = useRef({ globe: null, engine: null, protocol: null, simClock: null });
  const [ready, setReady] = useState(false);

  // C++ protocol bridge — created once, lives for the session
  const cppProtocolRef = useRef(null);
  if (!cppProtocolRef.current) cppProtocolRef.current = new CppProtocol();

  useEffect(() => () => cppProtocolRef.current?.destroy(), []);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);
  useEffect(() => { cameraModeRef.current = cameraMode; }, [cameraMode]);

  // When entering TRACK mode (or while in TRACK and selection changes), lock
  // the Three.js camera on the selected satellite.
  useEffect(() => {
    if (!ready) return;
    const { globe } = refsRef.current;
    if (!globe) return;
    globe.setTracked(cameraMode === 'TRACK' && selectedId != null ? selectedId : null);
  }, [cameraMode, selectedId, ready]);

  // Escape: exit tracking first, then clear selection.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (cameraModeRef.current === 'TRACK') setCameraMode('FREE');
        else setSelectedId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Called once by ThreeGlobe when the scene is ready.
  const onViewerReady = ({ simClock, engine, globe }) => {
    refsRef.current.globe    = globe;
    refsRef.current.engine   = engine;
    refsRef.current.protocol = engine.protocol;
    refsRef.current.simClock = simClock;

    // Wire C++ bridge to sim clock (drives C++ timers) and JS protocol (for animation)
    const cpp = cppProtocolRef.current;
    cpp.attachClock(simClock);
    cpp.attachProtocol(engine.protocol);

    setReady(true);
  };

  const value = {
    selectedId, setSelectedId,
    selectedIdRef,
    getSelectedId: () => selectedIdRef.current,
    cameraMode, setCameraMode,
    drawerOpen, setDrawerOpen,
    logFilter, setLogFilter,
    selectedSensor, setSelectedSensor,
    ready,
    onViewerReady,
    refs: refsRef,
    cppProtocol: cppProtocolRef.current,
  };

  return <SISPContext.Provider value={value}>{children}</SISPContext.Provider>;
}

export function useSISP() {
  const ctx = useContext(SISPContext);
  if (!ctx) throw new Error('useSISP must be used within <SISPProvider>');
  return ctx;
}

export function useSISPRefs() {
  const { refs, ready } = useSISP();
  return ready ? refs.current : null;
}
