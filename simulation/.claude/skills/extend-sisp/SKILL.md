---
name: extend-sisp
description: Use when adding a new SISP scenario, packet service code, or extending the protocol state machine. Walks through the exact files to edit (constants, ProtocolService, engine, useScenarios, ScenarioBar) and provides templates that match existing patterns. Trigger on requests like "add a scenario", "new packet type", "another service code", or any change that introduces a new packet color or state name.
---

# Extending SISP

## Add a new packet service code

Three edits, in this order. Skipping any of the three causes silent breakage.

### 1. `src/constants/index.js` — add the color

```js
export const SERVICE_COLOR = {
  // ...existing entries...
  NEW_SERVICE_REQ: '#ff8800',
  NEW_SERVICE_RSP: '#ff8800',
};
```

The `PacketAnimator` looks up the color by service name and falls back to white.

### 2. `src/sim/ProtocolService.js` — add a `payloadFor` case

```js
case 'NEW_SERVICE_REQ':
  return { reason: 'WHATEVER', some_value: 42 };
case 'NEW_SERVICE_RSP':
  return { ok: true };
```

This is what the inspector panel decodes when the user expands a log row.

### 3. The scenario that uses it

One-way:
```js
this.sendPacket(sat, neighbor, 'NEW_SERVICE_REQ');
```

Request/response:
```js
await this.request(sat, neighbor, 'NEW_SERVICE_REQ', 'NEW_SERVICE_RSP');
```

## Add a new scenario

### 1. State (only if needed)

If the scenario introduces a new sat state, add to `STATE_COLOR_HEX` **and** `STATE_COLOR_CSS` in `src/constants/index.js`. Existing states: `IDLE`, `CORR_WAIT_RSP`, `CORR_COMPUTING`, `RELAY_WAIT_ACCEPT`, `RELAY_ACTIVE`, `CRITICAL_FAIL`. Reuse one if it fits.

### 2. Trigger method on `ProtocolService`

```js
triggerWhatever(satId) {
  const sat = this.engine.getSat(satId);
  if (!sat || sat.state !== 'IDLE') return;          // gate on IDLE
  sat.state = 'NEW_STATE';
  sat.activeScenario = 'WHATEVER';                    // any short tag
  this.activeScenarios++;

  const neighbor = this.engine.findNearest(sat, 1)[0];
  if (!neighbor) {
    this._endScenario(sat);
    return;
  }

  this.request(sat, neighbor, 'NEW_SERVICE_REQ', 'NEW_SERVICE_RSP').then(() => {
    // further steps — use simClock.scheduleAfter for any delay
    this._endScenario(sat);
  });

  // Safety timeout in SIM seconds — never setTimeout
  this.simClock.scheduleAfter(8, () => {
    if (sat.activeScenario === 'WHATEVER') this._endScenario(sat);
  });
}
```

`_endScenario(sat)` resets state, activeScenario, and decrements `activeScenarios`. Call it exactly once at every termination path (success, timeout, early bail).

### 3. Autonomous trigger (optional)

In `src/sim/engine.js`, `_maybeTriggerRandomScenario`:

```js
} else if (r < 0.6) {
  this.protocol.triggerWhatever(this.sats[Math.floor(Math.random() * N)].id);
}
```

Pick a probability that doesn't crowd existing scenarios. The current budget:
- `< 0.04` failure
- `< 0.22` correction
- `< 0.36` relay
- `< 0.52` status
- `< 1.00` nothing

Don't blow past 0.7 in total.

### 4. UI button (optional)

`src/hooks/useScenarios.js` — add an action:

```js
fireWhatever: () => protocol.triggerWhatever(targetId()),
```

`src/ui/ScenarioBar.jsx` — add a button:

```jsx
<ScenarioBtn
  label="WHATEVER"
  onClick={fireWhatever}
  enabled={enabled}
  running={running === 'WHATEVER'}
/>
```

`enabled` is `!sat || sat.state === 'IDLE'`. The blinking dot lights up when `running === <tag>` matches `sat.activeScenario`.

## Reference patterns

The five existing scenarios in [`src/sim/ProtocolService.js`](../../src/sim/ProtocolService.js) cover all the shapes you'll need:

| Scenario | Shape |
|---|---|
| `triggerCorrection` | fan-out request to N neighbors, wait for all responses, transition to compute, end |
| `triggerRelay` | linear req/res then a chained one-way packet flow |
| `triggerHeartbeat` | stateless broadcast to all peers |
| `triggerFailure` | state change + one-way fan-out + timed auto-reset |
| `triggerStatus` | stateless fan-out to N nearest |

Match the closest one's shape rather than inventing a new pattern.
