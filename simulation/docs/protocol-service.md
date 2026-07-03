# ProtocolService

`src/sim/ProtocolService.js`

Owns every packet that flies between satellites and the ground station. UI components never call `sendPacket` directly — they call scenario-level methods (`triggerCorrection`, `triggerRelay`, …) which orchestrate one or more request/response cycles.

All timing inside this module flows through the injected `SimClock` — never `setTimeout` — so scenarios speed up, slow down, and pause with the playback bar.

## Surface

```ts
class ProtocolService {
  constructor(engine: SimulationEngine, simClock: SimClock)

  // raw transport
  sendPacket(from: Sat | null, to: Sat | null, service: ServiceCode, onArrive?: (pkt) => void): Packet
  onPacketArrive(pkt: Packet): void  // called by PacketAnimator when sim-time elapsed >= duration_s

  // req/res primitive
  request(from: Sat, to: Sat, reqService: string, rspService: string, processingMs?: number): Promise<void>

  // scenarios
  triggerCorrection(satId: number): void
  triggerRelay(satId: number): void
  triggerHeartbeat(senderId?: number): void
  triggerFailure(satId: number): void
  triggerStatus(satId: number): void
  resetAll(): void

  // observable state (read-only from UI)
  packets: Packet[]              // in-flight packets the renderer animates
  packetCount: number            // total sent this session
  activeScenarios: number        // count of in-progress scenarios
}
```

`from === null` means the ground station; same for `to === null`. Ground appears as `0x00` in logs.

## Packet shape

```js
{
  id: number,                    // monotonic
  from: Sat | null,
  to: Sat | null,
  service: 'CORRECTION_REQ' | …,
  startTime: number,             // performance.now() at dispatch
  duration: 1200,                // ms — packet flight time (PACKET_DURATION_MS)
  onArrive: (pkt) => void,       // optional callback fired on arrival
  seq: number,                   // sender's per-sat sequence number
}
```

## Service codes

| Code               | Color     | Direction                |
|--------------------|-----------|--------------------------|
| `CORRECTION_REQ`   | `#f5c518` | sat → neighbor           |
| `CORRECTION_RSP`   | `#f5c518` | neighbor → sat           |
| `RELAY_REQ`        | `#22d3ee` | sat → relay neighbor     |
| `RELAY_ACCEPT`     | `#22d3ee` | neighbor → sat           |
| `RELAY_REJECT`     | `#22d3ee` | neighbor → sat           |
| `DOWNLINK_DATA`    | `#a855f7` | sat → neighbor → ground  |
| `DOWNLINK_ACK`     | `#a855f7` | ground → neighbor → sat  |
| `HEARTBEAT`        | `#4ade80` | sender → all             |
| `FAILURE`          | `#ef4444` | failing sat → neighbors  |
| `STATUS_BROADCAST` | `#94a3b8` | sat → 2 nearest          |

## Request/response cycle

`request(from, to, reqService, rspService)` is the single primitive used by every scenario that needs a reply.

1. `from` sends `reqService` to `to`. Sender logs a TX entry.
2. The packet's `onArrive` fires when the bezier flight completes (the renderer calls `onPacketArrive` at `t = 1`). The receiving satellite logs an RX entry.
3. After a peer "processing" delay (default 200 ms), `to` sends `rspService` back to `from`.
4. The promise resolves once that response arrives.

Correlation is implicit — the response is the next packet the peer sends in reply, not a separately tracked transaction ID. That's good enough for a visualizer; a real protocol would key correlations by `(seq, peer)`.

## State machine

The state lives on each satellite (`sat.state`). Transitions are driven by scenario methods.

```
              ┌─────┐
              │IDLE │◄───────────────────────────────┐
              └──┬──┘                                │
        FAULT_DETECTED                               │
                 │                                   │
         ┌───────▼────────┐ all RSPs    ┌──────────────────┐
         │ CORR_WAIT_RSP  │────────────►│ CORR_COMPUTING   │
         └────────────────┘             └────────┬─────────┘
                                                 │ done (800 ms)
                                                 └─► IDLE

              ┌─────┐
              │IDLE │◄───────────────────────────────┐
              └──┬──┘                                │
         ENERGY_LOW                                  │
                 │                                   │
         ┌───────▼────────┐  ACCEPT     ┌────────────────┐
         │RELAY_WAIT_ACCEPT│────────────►│ RELAY_ACTIVE  │
         └────────────────┘             └────────┬─────────┘
                                                 │ ack chain
                                                 └─► IDLE

         CRITICAL_FAILURE  ──►  CRITICAL_FAIL  ──(4 s)──► IDLE
```

Heartbeat and Status are stateless — they fire packets without changing `sat.state`.

## Scenario flows

### Correction (`triggerCorrection`)

`IDLE → CORR_WAIT_RSP → CORR_COMPUTING → IDLE` (~5 s total)

1. Pick 2–3 nearest neighbors by 3D distance.
2. For each, fire `request(sat, neighbor, 'CORRECTION_REQ', 'CORRECTION_RSP')` staggered by 120 ms.
3. When the last response arrives, transition to `CORR_COMPUTING`.
4. After 800 ms of "compute", transition back to `IDLE`.
5. Hard 6.5 s safety timeout in case anything stalls.

### Relay (`triggerRelay`)

`IDLE → RELAY_WAIT_ACCEPT → RELAY_ACTIVE → IDLE` (~6–8 s total)

1. Pick the single nearest neighbor.
2. `request(sat, neighbor, 'RELAY_REQ', 'RELAY_ACCEPT')`.
3. On accept, transition to `RELAY_ACTIVE`.
4. `sat → neighbor` `DOWNLINK_DATA`.
5. `neighbor → ground` `DOWNLINK_DATA`.
6. After 200 ms, `ground → neighbor` `DOWNLINK_ACK`.
7. `neighbor → sat` `DOWNLINK_ACK`.
8. Energy +20%, transition back to `IDLE`.
9. Hard 9 s safety timeout.

### Heartbeat (`triggerHeartbeat`)

Stateless. The sender pulses green for 600 ms; every receiver pulses green for 500 ms when its `HEARTBEAT` arrives. Fired manually from the bar and globally every 10 s by the context's interval.

### Failure (`triggerFailure`)

`IDLE → CRITICAL_FAIL → IDLE` (4 s)

1. State immediately becomes `CRITICAL_FAIL` (red).
2. Broadcast `FAILURE` to 3 nearest neighbors (one-way, no response).
3. After 4 s, auto-reset to `IDLE`.

### Status (`triggerStatus`)

Stateless. Fires `STATUS_BROADCAST` to the 2 nearest neighbors. No state change.

### Reset (`resetAll`)

Forces every satellite back to `IDLE`, clears scenario flags, drops all in-flight packets. The renderer's reconciliation pass disposes orphaned packet meshes on the next animation frame.

## Coupling to the renderer

`PacketAnimator` is the ground truth for packet arrival. On every Cesium clock tick, it computes
`elapsed = JulianDate.secondsDifference(now, pkt.startSimTime)` and calls `onPacketArrive(pkt)` once `elapsed >= pkt.duration_s`. If you swap animators, the new one must drive arrivals from sim-time elapsed (not real time).

The protocol service does not own a clock of its own — every delay it schedules goes through `simClock.scheduleAfter(seconds, fn)`. That means a paused viewer freezes scenarios in flight, and a 600× viewer fast-forwards them.

## Logging

Every `sendPacket` writes a TX entry on the sender. Every `onPacketArrive` writes an RX entry on the receiver. Each entry includes:

- `ts` (`Date.now()`), `dir`, `service`, `peer`, `seq`, `flags`
- `src`, `dst` (resolved from the dir)
- `length` (random 16–63 bytes), `checksum` (random 16-bit hex)
- `payload` — service-specific decoded fields, see `payloadFor()` in the source.

The log is capped to 50 entries per satellite (FIFO, newest-first). The side panel reads it via `useSatellite`.

## Extending

### Add a one-way service
1. Add the code to `SERVICE_COLOR` in `constants/index.js`.
2. Add a `payloadFor()` case.
3. Call `sendPacket(from, to, 'NEW_SERVICE', onArrive)` from your scenario.

### Add a request/response service
1. Same as above for both REQ and RSP codes.
2. In your scenario, call `await this.request(from, to, 'NEW_REQ', 'NEW_RSP')`.

### Add an event emitter
The current implementation is poll-based. To switch to push-based UI updates, add a simple emitter (`on`, `off`, `emit`) to `ProtocolService`, emit `packet:sent` / `packet:arrived` / `state:changed`, and replace the polling in `useSatellite` / `useHUD` with `useEffect` subscriptions.
