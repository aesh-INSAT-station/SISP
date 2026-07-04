---
name: sim-clock-discipline
description: Use whenever editing any code under src/sim/ or src/cesium/ that involves timing, delays, intervals, the current time, scheduling, or "fire later". Enforces sim-clock discipline so the playback bar can pause and fast-forward the simulation without timing drift. Trigger on edits that touch ProtocolService scenarios, the SimulationEngine tick, packet flight timing, or anything in OrbitRenderer / PacketAnimator that asks "how much time has passed".
---

# Sim-clock discipline

The simulation runs off `SimClock`, a thin wrapper over `Cesium.Viewer.clock`. The clock can pause, run at 1×, or fast-forward to 3600×. **All simulation timing must follow.** Wall-clock timers break that the moment a user pauses or changes speed.

## Forbidden in `src/sim/` and `src/cesium/`

```js
setTimeout(fn, 200);        // ❌ fires regardless of pause / multiplier
setInterval(fn, 2000);      // ❌ same
Date.now();                 // ❌ wall clock
performance.now();          // ❌ wall clock (for sim time — log timestamps are different, see below)
new Date();                 // ❌ wall clock
```

## Use instead

```js
simClock.scheduleAfter(0.2, fn);   // one-shot, delay in SIM seconds
simClock.setInterval(2, fn);       // repeating, interval in SIM seconds
simClock.currentTime;              // Cesium.JulianDate of "now" in sim time
simClock.step(±n);                 // jump the clock by n sim-seconds
Cesium.JulianDate.secondsDifference(t1, t0);  // sim-time elapsed
Cesium.JulianDate.toDate(t).getTime();        // ms snapshot — only for log row keys
```

## Where exemptions are allowed

- **`src/hooks/`** — React hooks may use real `setInterval` for **polling** the engine (e.g. 250 ms). They're reading state for the UI, not driving the simulation.
- **`src/ui/`** — same reasoning. UI animations (CSS transitions, blink keyframes) run on real time and that's correct.
- **Log entry timestamps** in `ProtocolService._log` use `simClock.currentTime` converted to ms via `JulianDate.toDate().getTime()`. That's still sim time.

## Why

Suppose a scenario uses `setTimeout(fn, 200)` to send a response 200 ms after a request arrives:

- Pause the sim → the timer still fires → state machine advances while the visual is frozen.
- Run at 600× → packet flight takes 0.002 sim-seconds (visible as one frame), but the response timer still waits 200 ms wall — packet appears, then the response sits idle for 199 ms, then fires.
- Run at 0.1× → packets are slow but the response still fires fast — they overlap.

`simClock.scheduleAfter(0.2, fn)` schedules at `currentTime + 0.2 sim-seconds`. Cesium's tick loop fires events when sim time crosses their threshold. Pause freezes them. 600× fires them ~3.3 ms later in real time. Always coherent with the visual.

## Pattern: scenario step

```js
triggerSomething(satId) {
  const sat = this.engine.getSat(satId);
  if (!sat || sat.state !== 'IDLE') return;
  sat.state = 'BUSY';
  sat.activeScenario = 'X';
  this.activeScenarios++;

  this.request(sat, neighbor, 'REQ', 'RSP').then(() => {
    this.simClock.scheduleAfter(0.5, () => {
      this.sendPacket(sat, null, 'NEXT_STEP', () => this._endScenario(sat));
    });
  });

  // Always add a safety timeout in sim seconds, never wall seconds
  this.simClock.scheduleAfter(8, () => {
    if (sat.activeScenario === 'X') this._endScenario(sat);
  });
}
```

## Pattern: packet flight

Packets store `startSimTime` (a `JulianDate`) and `duration_s` (a number). `PacketAnimator` computes:

```js
const elapsed = Cesium.JulianDate.secondsDifference(time, pkt.startSimTime);
if (elapsed >= pkt.duration_s) protocol.onPacketArrive(pkt);
```

Never compare `Date.now()` to a `pkt.startTime` set with `performance.now()`.

## Quick sanity check

After editing scenario timing, mentally test these three cases:
1. Pause the sim mid-scenario → does the scenario freeze?
2. Slow to 1× → does the scenario take its full sim-duration?
3. Fast-forward to 3600× → does the scenario finish in (sim-duration / 3600) seconds wall?

If any answer is "no", you used the wall clock somewhere.
