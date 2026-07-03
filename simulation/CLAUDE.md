# SISP-SIM — Project instructions for Claude

CesiumJS + React satellite-mesh protocol simulator. Before any non-trivial change, read [`docs/architecture.md`](docs/architecture.md) and [`docs/protocol-service.md`](docs/protocol-service.md). For extension recipes see [`docs/contributing.md`](docs/contributing.md).

## The five rules

1. **Sim time, not wall time.** Inside `src/sim/` and `src/cesium/`, never use `setTimeout` / `setInterval` / `Date.now()` / `performance.now()` for "when should this happen". Use `simClock.scheduleAfter(seconds, fn)` and `simClock.setInterval(seconds, fn)`. The simulation must pause and fast-forward with the playback bar — wall-clock timers break that. Polling intervals in `src/hooks/` and `src/ui/` are fine because they're for UI refresh, not simulation timing.

2. **Layer discipline.** Imports flow downward only:
   ```
   ui/    → hooks/  → context/ → sim/  → constants, utils
                              ↘ cesium/ → sim/, constants, utils
   ```
   UI components never call `protocol.sendPacket` directly. They go through `useScenarios()`. Hooks read `engine` / `protocol` / `simClock` via `useSISP().refs.current` and only after `ready === true`.

3. **Cesium positions: static `positions` arrays render in FIXED (Earth-fixed) frame.** Anything you computed in inertial space — orbit ellipses, ECI points from `keplerian.js` — must be wrapped in a `CallbackProperty` that rotates with `Cesium.Transforms.computeTemeToPseudoFixedMatrix(time)`. See `OrbitRenderer._drawOrbit` for the pattern. Satellite entities themselves use `SampledPositionProperty(INERTIAL)` and Cesium auto-rotates those — leave them alone.

4. **`sat.elements` is the source of truth.** `sat.currentPos` is a FIXED-frame cache populated by `OrbitRenderer._onTick` for `findNearest` and packet endpoints. Don't mutate `elements` after construction; don't treat `currentPos` as ECI.

5. **Adding a service code = three edits.** `SERVICE_COLOR` in `constants/index.js` + `payloadFor()` case in `ProtocolService.js` + the scenario that calls it. Skipping any of the three produces silent visual or log breakage.

## Layout

```
src/sim/        plain JS — SimClock, SimulationEngine, ProtocolService, keplerian
src/cesium/     CesiumViewer, OrbitRenderer, PacketAnimator, ClickHandler
src/context/    SISPProvider, useSISP, useSISPRefs
src/hooks/      useSatellite, useHUD, useScenarios, usePlayback (poll at 250 ms)
src/ui/         presentation — pulls from hooks only
```

## Anti-patterns to reject

- Subscribing a React panel to `clock.onTick` (60 fps re-renders)
- Calling `protocol.sendPacket` from a UI component
- Mutating `sat.elements` to "move" a satellite (mutate scenario state instead)
- Importing Cesium into anything in `sim/` other than `keplerian.js` and `SimClock.js`
- Adding a Cesium widget without disabling its default in `CesiumViewer`'s viewer options
- Treating the test for "is sim ready" as anything other than `useSISP().ready`

## When in doubt

Open [`src/sim/ProtocolService.js`](src/sim/ProtocolService.js) and copy the shape of an existing scenario. They're all written the same way on purpose.

## Skills

Targeted skills live in `.claude/skills/`. They auto-trigger on descriptions:

- `sim-clock-discipline` — fires on any timing/delay/interval edit in `sim/` or `cesium/`
- `extend-sisp` — fires on "add scenario" / "new service code" / state machine changes
- `cesium-frames` — fires on Cesium entity / polyline / coordinate work
