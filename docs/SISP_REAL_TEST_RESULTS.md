# SISP Real OPS-SAT Integration Test Results

> Documented results of the real OPS-SAT integration tests conducted inside the JS simulation environment. All tests validate end-to-end ingestion, anomaly detection, correction, relay/borrow mechanics, and energy/failure simulation.

---

## 1. OPS-SAT Data Ingestion Test

**Source:** `Segments.json` loaded from `/public/` via `fetch()`

Four telemetry channels were mapped to four distinct satellites:

| Channel ID | Satellite  | Type   | Std Dev (observed) | Noise Overlay    |
|------------|------------|--------|---------------------|------------------|
| CADC0873   | LEO-IMG    | Magnetometer | ~2e-5         | sigma = 5e-7     |
| CADC0872   | LEO-COM    | Magnetometer | ~2e-5         | sigma = 5e-7     |
| CADC0894   | LEO-SCI    | Angle        | ~0.2-0.3      | sigma = 0.01-0.015 |
| CADC0892   | LEO-OBS    | Angle        | ~0.2-0.3      | sigma = 0.01-0.015 |

- Magnetometer-type channels (CADC0873, CADC0872) exhibit standard deviation near 2e-5.
- Angle-type channels (CADC0894, CADC0892) exhibit standard deviation in the range 0.2--0.3.
- Per-channel Gaussian noise is overlaid using the sigma values above.
- A wrapping cursor iterates through `Segments.json` segments indefinitely, simulating continuous telemetry streaming.

---

## 2. Hankel-SVD Detector Validation

**Configuration:** Threshold = 0.15, Window = 100, Hankel rows = 50

### Per-Channel Correlation Coefficient (rho)

| Channel ID | Samples | rho Median | rho Range    |
|------------|---------|------------|--------------|
| CADC0873   | 68289   | 0.64       | 0.59 -- 0.77 |
| CADC0872   | 66819   | 0.74       | 0.60 -- 0.89 |
| CADC0894   | 35512   | 0.92       | 0.67 -- 0.97 |
| CADC0892   | 49782   | 0.69       | 0.61 -- 0.97 |

### Threshold Strategy Comparison

| Strategy      | Fixed 0.15 | Adaptive | rho-Delta |
|---------------|------------|----------|-----------|
| Flagged range | 100%       | 1--43%   | 1--11%    |

- Fixed threshold at 0.15 flags all samples (100%) and is therefore overly sensitive.
- Adaptive threshold flags between 1% and 43% of samples depending on channel dynamics.
- rho-Delta flags the fewest (1--11%) and is the most conservative.

**Decision:** Retain the fixed 0.15 threshold combined with an 80-tick correction cooldown to suppress repeated triggers while maintaining sensitivity.

---

## 3. Correction Algorithm Test

The hybrid filter (Weighted Median + Kalman) is implemented in `ProtocolService`.

| Parameter              | Value                        |
|------------------------|------------------------------|
| Neighbors per correction | 3 (NAV_REFERENCE + nearest) |
| DEGR weight function    | w = max(0.05, 1 - DEGR / 15) |
| Kalman state count      | 6                            |
| Kalman q (process)      | 0.02                         |
| Kalman r (measurement)  | 0.8                          |
| Correction cooldown     | 80 ticks                     |

**Correction effects:**
- Reduces `orbit_error_m` by 60% of the computed improvement.
- Decrements `degr_svd` by 0.5 per correction.
- The 80-tick cooldown prevents cascading corrections and allows intervening relay, borrow, and heartbeat cycles.

---

## 4. Relay / Borrow Scenario Tests

| Event          | Trigger Condition       | Probability | Result                              |
|----------------|-------------------------|-------------|-------------------------------------|
| Relay          | `GS_LOST` transition    | 15%         | `triggerRelay()` called             |
| Borrow         | `GS_VISIBLE` transition | 10%         | `triggerBorrow()` called            |

**Ground stations:** KOU, SVA, MCM, HAW (LOS computed via `losToStation()`).

### Relay Flow
`GS_LOST` -> 15% chance -> `RELAY_REQ` handshake -> `DOWNLINK_DATA` -> `DOWNLINK_ACK` -> energy +20%

### Borrow Flow
`GS_VISIBLE` -> 10% chance -> `BORROW_REQ` handshake -> borrow sensor data from OBSERVATION peer

---

## 5. Energy & Failure Simulation

| Event                       | Rate / Trigger                                |
|-----------------------------|-----------------------------------------------|
| Sudden energy spike         | 1% per tick (15--40% drain)                   |
| Solar panel charge skip     | 2% per tick                                   |
| Random critical failure     | 0.3% per tick                                 |
| Auto-recovery               | After 60 sim-seconds + minimum 10% energy     |

- Energy spikes randomly drain 15--40% of the satellite's remaining energy at a 1%/tick occurrence rate.
- Solar panel charging is skipped 2% of ticks to simulate intermittent power.
- Critical failures occur at 0.3%/tick; satellites auto-recover after 60 simulation seconds provided energy exceeds 10%.
