# Contributing & Extending

This document is the practical "how do I add X" companion to [`architecture.md`](architecture.md) and [`protocol-service.md`](protocol-service.md).

## Where things live

```
src/
├── SISPNetworkVisualizer.jsx     orchestrator — mounts <SISPProvider>, viewer, panels
├── main.jsx                      React root
├── constants/index.js            colors, durations, sat count, sensor list
├── utils/format.js               hex, fmtUptime, relTime, degrColor
├── sim/                          plain JS — no React, no DOM
│   ├── SimClock.js               Cesium-clock wrapper + scheduler  ← all timing
│   ├── engine.js                 SimulationEngine, tick, autonomous scenarios
│   ├── ProtocolService.js        all req/res cycles + scenario flows
│   └── keplerian.js              circular-orbit propagator (ECI)
├── cesium/                       Cesium-side renderers — imperative classes
│   ├── CesiumViewer.jsx          mounts Viewer, instantiates services, wires teardown
│   ├── OrbitRenderer.js          sat entities, orbit ellipse, ground track, fly-to
│   ├── PacketAnimator.js         in-flight packet polylines + dots
│   └── ClickHandler.js           ScreenSpaceEventHandler → onSelect(id)
├── context/SISPContext.jsx       provider — selection state + ref bag
├── hooks/                        polling adapters between services and React
│   ├── useSatellite.js           snapshot of one sat (state, log, lat/lon/alt)
│   ├── useHUD.js                 packets, scenarios, health, sim time
│   ├── useScenarios.js           injectFault, dropGroundLink, …
│   └── usePlayback.js            togglePlay, setMultiplier, step
└── ui/                           pure presentation
    ├── ConstellationHUD.jsx
    ├── SatellitePanel.jsx        + sub-components Header, DegrBar, MetricsGrid…
    ├── PlaybackBar.jsx
    ├── ScenarioBar.jsx
    ├── Minimap.jsx
    ├── ScenarioBtn.jsx
    ├── Metric.jsx
    ├── DegrRow.jsx
    └── PacketLogRow.jsx
```

## Layer rules

```
ui/      → hooks/  → context/ → sim/   → constants, utils
                            ↘ cesium/  → sim/, constants, utils
```

- UI never imports from `sim/` or `cesium/` directly. Always through hooks.
- Hooks read engine/protocol/simClock via `useSISP().refs.current`, only after `ready === true`.
- `sim/` modules never import React or Cesium widgets. The two exceptions are `SimClock.js` (wraps `Viewer.clock`) and `keplerian.js` (uses `Cesium.Cartesian3`, `JulianDate`, `Transforms`). Even those import only `cesium`'s pure data types — never `Viewer` or entities.
- `cesium/` may import freely from `sim/` and `constants/`.

## Recipe: add a new packet service code

Three edits, in this order. Each one is necessary; skipping any produces silent breakage.

### 1. Color → `src/constants/index.js`

```js
export const SERVICE_COLOR = {
  // ...existing entries...
  HANDOVER_REQ: '#ec4899',
  HANDOVER_ACK: '#ec4899',
};
```

### 2. Decoded payload → `src/sim/ProtocolService.js`

```js
case 'HANDOVER_REQ':
  return { from_sat: sat.id, sensor: sat.sensor };
case 'HANDOVER_ACK':
  return { ok: true, takeover_in_s: 4 };
```

### 3. Use it in a scenario

```js
this.sendPacket(sat, neighbor, 'HANDOVER_REQ');
// or
await this.request(sat, neighbor, 'HANDOVER_REQ', 'HANDOVER_ACK');
```

The packet animator picks the color from `SERVICE_COLOR` automatically. The inspector panel decodes the payload via `payloadFor`.

## Recipe: add a new scenario

### 1. Optionally: a new state

If the scenario needs a state distinct from existing ones, add to `STATE_COLOR_HEX` and `STATE_COLOR_CSS` in `src/constants/index.js`. Existing states cover most cases — reuse if possible:

| State | Color | Meaning |
|---|---|---|
| `IDLE` | blue-white | nominal |
| `CORR_WAIT_RSP`, `CORR_COMPUTING` | amber | running correction |
| `RELAY_WAIT_ACCEPT`, `RELAY_ACTIVE` | cyan | relaying data |
| `CRITICAL_FAIL` | red | broken |

### 2. Trigger method on `ProtocolService`

Match the shape of an existing scenario. Skeleton:

```js
triggerHandover(satId) {
  const sat = this.engine.getSat(satId);
  if (!sat || sat.state !== 'IDLE') return;
  sat.state = 'IDLE';                          // or a new state
  sat.activeScenario = 'HANDOVER';
  this.activeScenarios++;

  const target = this.engine.findNearest(sat, 1)[0];
  if (!target) {
    this._endScenario(sat);
    return;
  }

  this.request(sat, target, 'HANDOVER_REQ', 'HANDOVER_ACK').then(() => {
    this.simClock.scheduleAfter(0.5, () => {
      this._endScenario(sat);
    });
  });

  // Always include a sim-time safety timeout
  this.simClock.scheduleAfter(8, () => {
    if (sat.activeScenario === 'HANDOVER') this._endScenario(sat);
  });
}
```

`_endScenario(sat)` resets state, clears `activeScenario`, decrements `activeScenarios`. Call it exactly once per termination path.

### 3. Optional: autonomous trigger

In `src/sim/engine.js`, `_maybeTriggerRandomScenario`:

```js
} else if (r < 0.55) {
  this.protocol.triggerHandover(this.sats[Math.floor(Math.random() * N)].id);
}
```

The probability budget is currently:

| Range | Scenario |
|---|---|
| `< 0.04` | failure |
| `< 0.22` | correction |
| `< 0.36` | relay |
| `< 0.52` | status |
| `< 1.00` | nothing fires |

Don't push the cumulative probability past ~0.7 or scenarios stack up faster than they finish.

### 4. Optional: UI button

`src/hooks/useScenarios.js`:

```js
fireHandover: () => protocol.triggerHandover(targetId()),
```

`src/ui/ScenarioBar.jsx`:

```jsx
<ScenarioBtn
  label="HANDOVER"
  onClick={fireHandover}
  enabled={enabled}
  running={running === 'HANDOVER'}
/>
```

## Recipe: add a new visualization to the globe

Anything you put on the globe lives in `src/cesium/`. Don't add Cesium calls to `sim/` or React components.

1. Build a renderer class with `init()`, optional clock-tick handler, `destroy()`.
2. Instantiate it inside `CesiumViewer.jsx` after `engine` and `simClock` are created.
3. Wire teardown into the same effect's cleanup chain.

Pattern:

```js
class HighlightRenderer {
  constructor(viewer, engine, simClock) {
    this.viewer = viewer;
    this.engine = engine;
    this.simClock = simClock;
    this.entities = [];
  }
  init() {
    this._removeTick = this.viewer.clock.onTick.addEventListener(() => this._onTick());
  }
  _onTick() { /* update entities */ }
  destroy() {
    if (this._removeTick) this._removeTick();
    this.entities.forEach((e) => this.viewer.entities.remove(e));
  }
}
```

If the entity should be pickable, set `entity._sisp_id = something` and `ClickHandler` will route clicks to `onSelect(something)`.

If positions are inertial (from `keplerian.js`), wrap them in a `CallbackProperty` that rotates via `Cesium.Transforms.computeTemeToPseudoFixedMatrix(time)` — see `OrbitRenderer._drawOrbit`.

## Recipe: surface new live data in the inspector

If the new field already exists on the satellite object:

1. Add it to the snapshot in `src/hooks/useSatellite.js` (`function snapshot(sat, engine)`).
2. Render it in `src/ui/SatellitePanel.jsx` — drop a `<Metric label="…" value={…} />` in the appropriate grid (`MetricsGrid` or `Geodetic`).

If it's a derived value from `sat.elements` and the current sim time, compute it inside `snapshot`:

```js
const period_min = sat.period_s / 60;
```

Don't compute in the component — `useSatellite` polls every 250 ms and components shouldn't recompute on every render.

## Sim-time discipline

**Inside `sim/` and `cesium/`, never use `setTimeout`, `setInterval`, `Date.now()`, `performance.now()`, or `new Date()` to drive simulation timing.** Use `simClock.scheduleAfter(seconds, fn)` and `simClock.setInterval(seconds, fn)`. The simulation must pause when the user pauses, accelerate when they slide to 600×, etc.

UI polling intervals (`setInterval` in `hooks/`) are fine — they refresh React state from the engine, they don't drive the engine.

Log entry timestamps use `Cesium.JulianDate.toDate(simClock.currentTime).getTime()` — that's still sim time, just in millisecond form for the `relTime` formatter.

## Cesium frame discipline

- Static `polyline.positions` arrays render in **FIXED** frame.
- Anything from `keplerian.js` is in **ECI**.
- Wrap ECI positions in `Cesium.CallbackProperty` and rotate per frame with `Cesium.Transforms.computeTemeToPseudoFixedMatrix(time)`. See `OrbitRenderer._drawOrbit`.
- `sat.currentPos` is FIXED, written each tick by `OrbitRenderer._onTick`.
- `Cartesian3.fromDegrees / fromRadians` are already FIXED. Don't rotate.

## Testing edits manually

There's no test suite. After a change:

1. `npm run build` must complete with no errors.
2. `npm run dev` and verify:
   - Satellites trace their orbits smoothly.
   - Click a satellite → orbit appears, panel opens, camera flies in.
   - Pause via the playback bar → sim freezes; resume → continues from where it left off.
   - Crank to 3600× → scenarios visibly speed up.
   - Click the constellation health dots → selection updates.
   - `RESET ALL` clears in-flight packets cleanly.

If the sim "drifts" after a pause-and-resume, you used a wall-clock timer somewhere.
