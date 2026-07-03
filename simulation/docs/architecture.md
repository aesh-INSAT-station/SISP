# Architecture

SISP-SIM runs the simulation off **Cesium's clock** and renders on a real Earth via **CesiumJS**. The app is split into four layers, each only depending on the layer(s) below it.

```
        ┌──────────────────────────────────────────────┐
  UI    │  ui/           pure presentation             │
        ├──────────────────────────────────────────────┤
  glue  │  hooks/        React adapters, polling       │
        ├──────────────────────────────────────────────┤
  state │  context/      SISPProvider, selection       │
        ├──────────────────────────────────────────────┤
  core  │  sim/          plain JS — clock, engine,     │
        │                protocol, Keplerian math      │
        │  cesium/       Viewer mount + entity         │
        │                renderers (orbit, packets,    │
        │                click)                        │
        └──────────────────────────────────────────────┘
```

## sim/

Plain JS — no React, no Cesium widgets, just data.

| Module | Responsibility |
|---|---|
| `keplerian.js` | Pure-JS circular-orbit propagator. Exposes `getPositionAtTime`, `getOrbitPoints`, `getGroundTrack`, `buildSampledPosition`, `geodeticAt`, `periodSeconds`. |
| `SimClock.js`  | Wraps `Viewer.clock`. Exposes `scheduleAfter`, `setInterval`, `step`, `setMultiplier`, `setPlaying`, `onTick`. **All scenario timing flows through this — never `setTimeout`.** |
| `engine.js`    | `SimulationEngine` — owns the 8 satellites and their orbital elements. Runs `tick()` (DEGR drift, energy drift, autonomous random scenarios). |
| `ProtocolService.js` | Every SISP request/response cycle and the `packets[]` queue the renderer reads. See [`protocol-service.md`](./protocol-service.md). |

## cesium/

Cesium-specific. Reads from `sim/`, writes entities to a `Viewer`.

| Module | Responsibility |
|---|---|
| `CesiumViewer.jsx` | React component. Builds the `Viewer`, wires the clock, instantiates `SimulationEngine`, `OrbitRenderer`, `PacketAnimator`, `ClickHandler`, fires `onReady` upward. |
| `OrbitRenderer.js` | Adds 8 satellite entities (point + label) using `SampledPositionProperty(INERTIAL)`. On selection, draws the orbit ellipse (rotated each frame from inertial to fixed) + 90-min ground track + camera fly-to. |
| `PacketAnimator.js`| Mirrors `protocol.packets[]` into Cesium polyline + point entities. Uses `CallbackProperty` with sim-time elapsed for both the moving dot and the post-arrival fade. Caps at 20 in flight. |
| `ClickHandler.js`  | `ScreenSpaceEventHandler` → `picked.id._sisp_id` → `onSelect(id)`. |

## context/

`SISPProvider` keeps two things: React selection state, and a ref bag populated by `CesiumViewer.onReady` (`viewer`, `engine`, `protocol`, `simClock`). Hooks read both from this provider.

## hooks/

| Hook | Returns |
|---|---|
| `useSatellite(satId)` | Snapshot of one satellite plus its current `lat_deg / lon_deg / alt_km / period_s`. |
| `useHUD()` | `{ packetCount, scenarios, health, multiplier, isPlaying, simTime, simTimeMs }`. |
| `useScenarios()` | Bound action creators: `injectFault`, `dropGroundLink`, `setLowEnergy`, `heartbeat`, `resetAll`. |
| `usePlayback()` | `togglePlay`, `setMultiplier`, `stepBack`, `stepForward`. |

## ui/

Pure presentation. No direct engine access — everything goes through hooks.

| Component | Role |
|---|---|
| `ConstellationHUD` | Top-left protocol/health panel. |
| `SatellitePanel`   | Right inspector — header / DEGR bar / metrics / lat-lon-alt / breakdown / log / minimap. |
| `Minimap`          | 280×140 canvas ground-track minimap; redraws every 2 sim-seconds. |
| `PlaybackBar`      | Bottom-center pill — pause/resume, `1×/60×/600×/3600×` snaps, slider, sim-time display. |
| `ScenarioBar`      | Bottom action bar wired to `useScenarios()`. |

## Data flow

```
  Cesium clock onTick ─────────────────────────────────────────┐
        │                                                      │
        ▼                                                      │
  ┌──────────────┐  scheduleAfter(s, fn)   ┌────────────────┐  │
  │  SimClock    │◄────────────────────────│ ProtocolService│  │
  └──────┬───────┘                         └───────▲────────┘  │
         │ setInterval(2, engine.tick)             │           │
         ▼                                  scenario triggers  │
  ┌──────────────┐                                 │           │
  │SimulationEng.│─────────────────────────────────┘           │
  └──────┬───────┘                                              │
         │ sat positions, state, log                            │
         ▼                                                      │
  ┌──────────────┐  packets[]  ┌────────────────┐               │
  │OrbitRenderer │──┐  ┌──────►│ PacketAnimator │◄──────────────┘
  └──────┬───────┘  │  │       └────────────────┘
         │ pick     │  │ writes currentPos
         ▼          ▼  │
  ┌──────────────┐     │
  │ ClickHandler │     │
  └──────┬───────┘     │
         │ onSelect    │
         ▼             ▼
  SISPContext (React)  ─→  hooks  ─→  ui/ components
```

## Why polling, not subscriptions?

Cesium's `clock.onTick` fires once per render frame (~60 fps). Every renderer subscribes to it directly. React panels would drop frames if they re-rendered that often, so hooks poll at 250–300 ms — well below perception threshold for status panels — while the canvas runs hot.

## Adding a new scenario

1. Add the method to `ProtocolService` (`triggerX`). Use `request()` for any req/res leg, raw `sendPacket()` for one-way packets, `simClock.scheduleAfter(s, fn)` for any timer (never `setTimeout`).
2. Optionally make `SimulationEngine._maybeTriggerRandomScenario()` fire it autonomously.
3. Optionally add a button to `ScenarioBar` and an action to `useScenarios()`.

## Adding a new service code

1. Add the code to `SERVICE_COLOR` in `constants/index.js`.
2. Add a `payloadFor()` case in `ProtocolService.js`.
3. The animator picks the color up automatically.

## Migration notes (Three.js → Cesium)

The pure simulation core (`engine`, `ProtocolService`, scenarios, state machine) is **unchanged in semantics** — it was retargeted to drive timing off `SimClock` instead of `setTimeout` / `setInterval` / `Date.now()`. The Three.js renderer was deleted and replaced with three small Cesium services. The state machine, log format, scenario flows, and DEGR computation are byte-for-byte identical.
