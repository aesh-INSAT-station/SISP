---
name: cesium-frames
description: Use when working on Cesium entities, polylines, primitives, orbit rendering, ground tracks, packet animations, or anything involving 3D positions and coordinate frames. Covers ICRF / inertial vs FIXED frame, when to wrap positions in CallbackProperty, the sat.currentPos cache, and the _sisp_id picking convention. Trigger on edits in src/cesium/, the Keplerian propagator, or any new visualization that puts positions on the globe.
---

# Cesium frames in SISP-SIM

Cesium displays everything in **FIXED** frame (Earth-fixed, ECEF). Anything you compute in inertial space (J2000 / ICRF / ECI) must be rotated each frame. Pure-JS Keplerian math in `src/sim/keplerian.js` always returns ECI Cartesian3.

## What's already handled — don't change

- **Satellite entity positions** use `SampledPositionProperty(Cesium.ReferenceFrame.INERTIAL)` (see `OrbitRenderer.init` and `keplerian.buildSampledPosition`). Cesium auto-rotates. Adding an FIXED-frame `position` for a sat would break this.
- **`VelocityOrientationProperty`** orients each sat along its velocity vector for free.
- **`sat.currentPos`** is the **FIXED-frame** snapshot at the current tick, written by `OrbitRenderer._onTick` via `entity.position.getValue(time)`. Use it for distance comparisons (`findNearest`) and packet endpoints. Do **not** treat it as ECI.

## What you must rotate manually

### Static polylines whose positions are conceptually inertial

Canonical case: the orbit ellipse. Pattern in `OrbitRenderer._drawOrbit`:

```js
const eciPoints = getOrbitPoints(sat.elements, 360);
const scratchMatrix = new Cesium.Matrix3();
const rotatedCache = eciPoints.map(() => new Cesium.Cartesian3());

const positionsProp = new Cesium.CallbackProperty((time) => {
  const m = Cesium.Transforms.computeTemeToPseudoFixedMatrix(time, scratchMatrix);
  if (!m) return eciPoints;
  for (let i = 0; i < eciPoints.length; i++) {
    Cesium.Matrix3.multiplyByVector(m, eciPoints[i], rotatedCache[i]);
  }
  return rotatedCache;
}, false);
```

`computeTemeToPseudoFixedMatrix` is always available — no Earth-orientation data required. `computeIcrfToFixedMatrix` is more accurate but requires preloaded EOP, which we don't load. Visual difference is sub-pixel for this app.

The `false` argument to `CallbackProperty` means "not constant" — Cesium re-evaluates every frame, which is what we want.

### Orbits and elements

Compute orbit points from `sat.elements` (always ECI). Don't try to derive an orbit from `sat.currentPos`.

## Things that are already in FIXED frame — don't rotate

- `Cesium.Cartesian3.fromDegrees(lon, lat, height)` — direct FIXED.
- `Cesium.Cartesian3.fromRadians(lon, lat, height)` — direct FIXED.
- Ground tracks built from `Cartographic` then `fromRadians` — FIXED. Use `clampToGround: true` on the polyline.
- `sat.currentPos` — already FIXED.

## Packet endpoint drift

`PacketAnimator` snapshots `from.currentPos` and `to.currentPos` at packet creation (FIXED frame, that instant). For 1.2 sim-second flights at 60×, real-time drift from Earth rotation is ≈ one frame — invisible. At 3600× it becomes ≈ 18°. If you need accurate inertial-frame packets at high multipliers, store ECI endpoints (`sat.elements` + `getPositionAtTime` at start time) and rotate via `CallbackProperty`. Not currently necessary.

## Picking selection

Click selection routes through a tag on the entity. `OrbitRenderer.init` sets:

```js
entity._sisp_id = sat.id;
```

`ClickHandler` then reads `picked.id._sisp_id` and forwards the id. **Any new pickable entity needs this tag** or it won't open the inspector.

## Common mistakes

- **Putting `getOrbitPoints(...)` straight into `polyline.positions`.** The orbit drifts off the satellite over minutes. Always wrap in `CallbackProperty` (see pattern above).
- **Using `sat.currentPos` before the first clock tick.** It's `null` at engine construction. `findNearest` already handles this with an id-order fallback. New code that reads `currentPos` should null-check.
- **Forgetting to disable a Cesium widget.** `CesiumViewer.buildViewer` lists every default widget set to `false`. Don't enable any unless you're rebuilding the chrome.
- **Mutating shared scratch Cartesian3 / Matrix3.** Always create a fresh result object or use the explicit out-param — Cesium APIs are explicit about this and reusing the wrong scratch will silently corrupt other entities.
- **Calling `viewer.entities.add` from React render.** Entity creation belongs in the renderer classes (`OrbitRenderer`, `PacketAnimator`). React only mounts the viewer once and never touches entities directly.

## Cleanup discipline

Every entity added in `OrbitRenderer` or `PacketAnimator` must be removed in their respective `destroy()` methods. The orchestrator's `useEffect` cleanup chains call `destroy()` on viewer unmount. New renderers should follow the same shape (init, start/animate via `clock.onTick`, destroy).
