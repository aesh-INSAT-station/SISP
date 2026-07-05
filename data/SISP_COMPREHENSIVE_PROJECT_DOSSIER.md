# SISP Comprehensive Project Dossier

Evidence scope: this dossier was produced only from files inside this repository folder. It consolidates the project documentation, implementation, tests, logs, and simulation notes without adding external claims beyond what the repo itself states.

## Executive Wow Factors

SISP, the Satellite Inter-Service Protocol, is presented in the codebase as a cooperative, autonomous, self-healing protocol stack for CubeSat constellations. Its core promise is unusually ambitious: satellites can correct degraded sensors, relay payloads across visibility gaps, and borrow healthy sensors from neighbours without ground intervention.

The strongest evidence-backed highlights are:

| Capability | Evidence in repo | Why it is impressive |
|---|---|---|
| Deterministic service orchestration | C++ `StateMachine` uses a static `21 x 24` transition table | Embedded-friendly O(1) transition lookup with bounded action functions; correction algorithms remain pluggable through a virtual filter interface |
| Autonomous correction | `FAULT_DETECTED` broadcasts `CORRECTION_REQ`, buffers neighbour responses, then runs a pluggable correction filter | Converts constellation neighbours into temporary sensor redundancy |
| Failure isolation | `RX_FAILURE` self-loops in every state and only records the failed peer | Prevents neighbour failure messages from cascading the constellation into `CRITICAL_FAIL` |
| Sensor borrowing | `BORROW_REQ`, `BORROW_DECISION`, and `DOWNLINK_DATA` implement a named borrow workflow | Makes sensor redundancy a protocol service rather than duplicated hardware only |
| DEGR trust model | `compute_degr()` combines k-factor deviation, SVD residual, age, and orbit error into a 0-15 score | Turns health into a continuous correction weight instead of binary good/bad status |
| Hybrid correction layer | Weighted median, Kalman, and Hybrid filters share one `CorrectionFilter` interface | The protocol does not care which correction algorithm is active |
| SVD anomaly pipeline | Per-channel `TruncatedSVD` reconstruction-error detector on OPSSAT-AD features | Provides the documented unsupervised anomaly-screening path for correction trust decisions |
| Dual-PHY 437 MHz design | `CONTROL_437_NARROW` and `BULK_437_WIDE` are encoded per frame | Keeps control robust while allowing wider bulk relay/borrow transfers |
| Fixed 512-bit frame | `FRAME_SIZE = 64`, CRC-8/MAXIM checksum, transport extensions | Compact, testable binary envelope for constrained UHF links |
| Quantified performance | Logs and docs report 273/273 C++ tests, 94.3% 30-day RMSE improvement, 85.6% improvement with 10% packet loss | The strongest claims are backed by deterministic test logs |

## What SISP Is

SISP is a protocol stack plus simulation suite for satellite constellations. The codebase contains four major layers:

| Layer | Main files/folders | Role |
|---|---|---|
| C++ protocol core | `c++ implemnetation/include`, `c++ implemnetation/src` | State machine, packet/frame codec, DEGR scoring, correction filters, simulation hooks |
| Python protocol harness | `python_satellite_sim_v2.py`, `all_tests/` | Multi-satellite scenarios, packet loss, relay/borrow/correction integration tests |
| SVD anomaly pipeline | `sisp/`, `pipelines/`, `sisp_svd_anomaly.py`, `config/settings.py` | OPSSAT-AD ingestion, preprocessing, per-channel SVD anomaly detection |
| Physics and value simulation | `simulation for signal and physics/` | Orbital geometry, link budget, BER/PER, dual-PHY timing/energy, sustainability dashboard |

The repository frames SISP around three autonomous services:

| Service | Trigger | Goal | Messages |
|---|---|---|---|
| Sensor correction | `FAULT_DETECTED` | Replace a degraded local reading with a neighbour-weighted corrected estimate | `CORRECTION_REQ`, `CORRECTION_RSP` |
| Data relay | `ENERGY_LOW` or `GS_LOST` | Move payload data through another satellite when direct downlink is unavailable | `RELAY_REQ`, `RELAY_ACCEPT`, `RELAY_REJECT`, `DOWNLINK_DATA`, `DOWNLINK_ACK` |
| Sensor borrow | `GS_VISIBLE` or a received borrow request | Temporarily use another satellite's healthy sensor/data stream | `BORROW_REQ`, `BORROW_DECISION`, `DOWNLINK_DATA` |

## Project Architecture

The repository documentation describes the architecture at a high level as:

1. Satellite nodes contain sensors, local anomaly detection, a SISP protocol node, and service buffers.
2. Degradation is summarized by DEGR, a 0-15 health/trust score that influences correction weights and service confidence.
3. Correction responses are filtered before being used.
4. Relay and borrow move data through neighbouring satellites.
5. Physical-layer feasibility is modeled with orbital line-of-sight, slant range, Doppler, BER/PER, and energy.

### Repository Layout

| Path | Contents |
|---|---|
| `README.md` | Root overview, quick start, key numbers, references |
| `docs/` | Research paper, architecture, state machine, SVD, correction, signal physics, energy, KPI snapshot, test results |
| `c++ implemnetation/` | C++ protocol implementation, tests, CMake files, protocol docs |
| `sisp/` | Importable Python data/anomaly package |
| `pipelines/` | Thin runnable ingestion/preprocessing/SVD orchestration scripts |
| `simulation for signal and physics/` | Streamlit simulations, scientific reports, RF/geometry studies |
| `all_tests/` | Python integration and scale tests |
| `data/raw/` | Raw OPSSAT-AD dataset files committed in this workspace |
| `logs/` | Captured C++ and Python test logs |

## Tech Stack

| Area | Technology |
|---|---|
| Protocol implementation | C++17-style headers/sources, CMake, fixed-size arrays, C ABI simulation hooks |
| Python pipeline | Python, pandas, pyarrow, requests, scikit-learn, joblib |
| Anomaly detection | `TruncatedSVD`, `StandardScaler`, reconstruction error, quantile thresholding |
| Simulation/math | numpy, scipy, matplotlib |
| Dashboard UI | Streamlit |
| Orbital geometry | Skyfield / SGP4 |
| Test harness | C++ test runner, Python `ctypes` DLL calls, custom integration scripts |
| Signal models | AWGN BER, GMSK BT=0.3, BPSK/QPSK/FSK, K=7 convolutional coding, RS(255,223) proxy |

The root `requirements.txt` groups dependencies into SVD pipeline packages, simulation/dashboard packages, and protocol harness dependencies. The protocol harness relies on Python stdlib `ctypes` plus numpy.

## Protocol Wire Model

The C++ protocol defines:

| Constant/type | Value/meaning |
|---|---|
| `VERSION` | 1 |
| `FRAME_SIZE` | 64 bytes, fixed 512-bit frame |
| `HEADER_SIZE` | 5 bytes |
| `SEC_PREFIX` | 16 bytes when `OFFGRID` is not set |
| `MAX_PACKET` | 128 bytes |
| `MAX_PAYLOAD` | 107 bytes |
| `BCAST_ADDR` | `0xFF` |
| `GROUND_ADDR` | `0x00` |
| `MAX_FRAGMENT_DATA` | 101 bytes in protocol constants; frame-level payload capacity can be lower after extensions |

### Header Fields

The packed 5-byte header carries:

| Field | Width |
|---|---|
| `SVC` | 4 bits |
| `SNDR` | 8 bits |
| `RCVR` | 8 bits |
| `SEQ` | 8 bits |
| `DEGR` | 4 bits |
| `FLAGS` | 4 bits |
| `CKSM` | 4 bits |

The frame adds payload length, extension length, frame control bits, an extension region, payload bytes, and a final CRC-8/MAXIM checksum over bytes 0-62.

### Service Codes

| Code | Service |
|---|---|
| `0x0` | `CORRECTION_REQ` |
| `0x1` | `CORRECTION_RSP` |
| `0x2` | `RELAY_REQ` |
| `0x3` | `RELAY_ACCEPT` |
| `0x4` | `RELAY_REJECT` |
| `0x5` | `DOWNLINK_DATA` |
| `0x6` | `DOWNLINK_ACK` |
| `0x7` | `STATUS_BROADCAST` |
| `0x8` | `HEARTBEAT` |
| `0x9` | `HEARTBEAT_ACK` |
| `0xA` | `BORROW_DECISION` |
| `0xB` | `RESERVED_B` |
| `0xC` | `RESERVED_C` |
| `0xD` | `RESERVED_D` |
| `0xE` | `BORROW_REQ` |
| `0xF` | `FAILURE` |

### Payload Types

Implemented typed payloads include:

| Payload | Key fields |
|---|---|
| `CorrectionReq` | sensor type, window seconds |
| `CorrectionRsp` | sensor type, 3-axis reading, timestamp |
| `RelayReq` | hop count, fragment count, window seconds |
| `RelayDecision` | accepted flag, reason |
| `DownlinkData` | fragment index, fragment total, data length, data bytes |
| `DownlinkAck` | 32-bit acknowledgement field currently used for ACK/fragment metadata |
| `Status` | energy percentage, ground visibility, sensor mask, uptime, PHY capabilities |
| `Heartbeat` | energy percentage, DEGR, uptime |
| `Failure` | code, detail, DEGR |
| `BorrowReq` | sensor type, duration, priority |
| `BorrowDecision` | accepted flag, duration |

## State Machine

The state machine is implemented in `c++ implemnetation/include/sisp_state_machine.hpp` and `c++ implemnetation/src/sisp_state_machine.cpp`.

Design facts from code:

| Property | Value |
|---|---|
| Dispatch table | `g_trans[STATE_COUNT][EVT_COUNT]` |
| State count | 21 |
| Event count | 24 |
| Dispatch | Lookup current state/event, call action, set next state |
| Timer semantics | Absolute deadline in `timer_deadline_ms`; `tick()` dispatches `TIMER_EXPIRED` when `now_ms >= deadline` |
| Reset behavior | Resets context but preserves `self_id` |
| Failure isolation | `RX_FAILURE` records peer failure and stays in same state |
| Local critical failure | `CRITICAL_FAILURE` sets DEGR to 15, broadcasts `FAILURE`, transitions to `CRITICAL_FAIL` |

### Enumerated States

| Code | State | Domain |
|---|---|---|
| 0 | `IDLE` | Ready/quiescent |
| 1 | `CORR_WAIT_RSP` | Correction requester waits for first response |
| 2 | `CORR_COLLECTING` | Correction requester collects neighbour responses |
| 3 | `CORR_COMPUTING` | Correction filter is run |
| 4 | `CORR_DONE` | Correction result available |
| 5 | `CORR_RESPONDING` | Correction responder sends local reading |
| 6 | `RELAY_WAIT_ACCEPT` | Relay requester waits for accept/reject |
| 7 | `RELAY_SENDING` | Relay sender transmits fragments |
| 8 | `RELAY_WAIT_ACK` | Relay sender waits for acknowledgement |
| 9 | `RELAY_DONE` | Relay complete |
| 10 | `RELAY_RECEIVING` | Relay provider accepts incoming relay |
| 11 | `RELAY_STORING` | Relay provider stores fragments |
| 12 | `RELAY_DOWNLINKING` | Relay provider forwards stored payload |
| 13 | `BORROW_WAIT_ACCEPT` | Borrow requester waits for decision |
| 14 | `BORROW_RECEIVING` | Borrow requester receives borrowed data |
| 15 | `BORROW_DONE` | Borrow complete |
| 16 | `BORROW_SAMPLING` | Borrow provider samples requested sensor |
| 17 | `BORROW_SENDING` | Borrow provider sends borrowed data |
| 18 | `TIMEOUT` | Error/failure state defined in enum |
| 19 | `ERROR` | Error/failure state defined in enum |
| 20 | `CRITICAL_FAIL` | Local critical failure |

### Enumerated Events

| Code | Event | Source |
|---|---|---|
| 0 | `RX_CORRECTION_REQ` | Packet receive |
| 1 | `RX_CORRECTION_RSP` | Packet receive |
| 2 | `RX_RELAY_REQ` | Packet receive |
| 3 | `RX_RELAY_ACCEPT` | Packet receive |
| 4 | `RX_RELAY_REJECT` | Packet receive |
| 5 | `RX_DOWNLINK_DATA` | Packet receive |
| 6 | `RX_DOWNLINK_ACK` | Packet receive |
| 7 | `RX_STATUS_BROADCAST` | Packet receive |
| 8 | `RX_HEARTBEAT` | Packet receive |
| 9 | `RX_HEARTBEAT_ACK` | Packet receive |
| 10 | `RX_BORROW_REQ` | Packet receive |
| 11 | `RX_FAILURE` | Packet receive |
| 12 | `FAULT_DETECTED` | Internal sensor/fault layer |
| 13 | `TIMER_EXPIRED` | Internal RTOS/timer tick |
| 14 | `ENERGY_LOW` | Internal power monitor |
| 15 | `GS_VISIBLE` | Orbit/ground-station predictor |
| 16 | `GS_LOST` | Orbit/ground-station predictor |
| 17 | `ALL_FRAGS_SENT` | Internal relay/borrow flow |
| 18 | `ALL_FRAGS_RCVD` | Internal relay/borrow flow |
| 19 | `SENSOR_READ_DONE` | Internal sensor layer |
| 20 | `CORRECTION_DONE` | Internal correction completion |
| 21 | `CRITICAL_FAILURE` | Internal local failure monitor |
| 22 | `RESET` | External command / recovery |
| 23 | `RX_BORROW_DECISION` | Packet receive |

### Key State Flows

#### Correction Requester Flow

1. `IDLE + FAULT_DETECTED` broadcasts `CORRECTION_REQ`, clears response count, sets a 5,000 ms deadline, enters `CORR_WAIT_RSP`.
2. `CORR_WAIT_RSP + RX_CORRECTION_RSP` buffers a valid response and enters `CORR_COLLECTING`.
3. `CORR_COLLECTING + RX_CORRECTION_RSP` keeps collecting responses up to 8 neighbours.
4. `CORR_WAIT_RSP/CORR_COLLECTING + TIMER_EXPIRED` runs the configured correction filter and enters `CORR_COMPUTING`.
5. `CORR_COMPUTING + CORRECTION_DONE` transitions to `IDLE`; the current transition table invokes the correction action again during that transition.

Correction response filtering in code rejects:

| Rejection reason | Code behavior |
|---|---|
| No packet | return |
| Response buffer already has 8 entries | return |
| Payload cannot deserialize as `CorrectionRsp` | return |
| Sensor type differs from requested sensor | return |
| Peer status says requested sensor is missing | return |

Each accepted response stores x, y, z, timestamp, and weight:

`weight = max(0.05, 1.0 - peer_degr / 15.0)`

#### Correction Responder Flow

1. `IDLE + RX_CORRECTION_REQ` enters `CORR_RESPONDING`.
2. Action parses the request and unicasts `CORRECTION_RSP` with `own_reading`.
3. `CORR_RESPONDING + SENSOR_READ_DONE` can send a response and return to `IDLE`.

#### Relay Flow

Requester:

1. `IDLE + ENERGY_LOW` or `IDLE + GS_LOST` broadcasts `RELAY_REQ`, sets a 10,000 ms deadline, enters `RELAY_WAIT_ACCEPT`.
2. `RELAY_WAIT_ACCEPT + RX_RELAY_ACCEPT` enters `RELAY_SENDING` and sends fragments.
3. `RELAY_SENDING + ALL_FRAGS_SENT` enters `RELAY_WAIT_ACK`.
4. `RELAY_WAIT_ACK + RX_DOWNLINK_ACK` enters `RELAY_DONE`.
5. Timer expiry retries relay request up to `max_retries` (default 3).

Provider:

1. `IDLE + RX_RELAY_REQ` enters `RELAY_RECEIVING`, parses relay metadata, and sends `RELAY_ACCEPT`.
2. `RELAY_RECEIVING + RX_DOWNLINK_DATA` enters `RELAY_STORING` and stores fragments.
3. `RELAY_STORING + ALL_FRAGS_RCVD` enters `RELAY_DOWNLINKING`.
4. `RELAY_DOWNLINKING + SENSOR_READ_DONE` sends an acknowledgement and returns to `IDLE`.

Fragment recovery uses a receive storage buffer, assembled length, and a bitmask for fragment indices below 32.

#### Borrow Flow

Requester:

1. `IDLE + GS_VISIBLE` broadcasts `BORROW_REQ`, sets a 15,000 ms deadline, enters `BORROW_WAIT_ACCEPT`.
2. `BORROW_WAIT_ACCEPT + RX_BORROW_DECISION` records the decision sender and decision payload, then enters `BORROW_RECEIVING`. The current transition does not block rejected decisions.
3. `BORROW_RECEIVING + RX_DOWNLINK_DATA` stores fragments.
4. `BORROW_RECEIVING + ALL_FRAGS_RCVD` enters `BORROW_DONE`.

Provider:

1. `IDLE + RX_BORROW_REQ` enters `BORROW_SAMPLING`, stores requested sensor/duration, and sends `BORROW_DECISION`.
2. Decision accepts only if local sensor mask contains the requested sensor.
3. `BORROW_SAMPLING + SENSOR_READ_DONE` enters `BORROW_SENDING` and sends data.
4. `BORROW_SENDING + ALL_FRAGS_SENT` enters `BORROW_DONE`.

### Failure Flow

| Input | Transition | Action |
|---|---|---|
| Any state + `CRITICAL_FAILURE` | `CRITICAL_FAIL` | Set local `current_degr=15`, broadcast `FAILURE` with DEGR 15 |
| Any state + `RX_FAILURE` | Same state | Mark sender in `known_failed`, set `peer_friendly=0`, store failure payload if valid |

This is a major innovation point in the repo: a node can learn that a neighbour failed without declaring itself failed.

## DEGR Trust Score

DEGR is a 4-bit degradation score in the range 0-15. The implementation computes it in `compute_degr()` using four components:

| Component | Score range | Code behavior |
|---|---|---|
| k-factor deviation | 0-5 | `abs(k_factor - 1.0)` mapped by 0.10, 0.20, 0.30, 0.40, 0.50 buckets |
| SVD residual | 0-5 | residual bucketed at `>0`, `>0.20`, `>0.40`, `>0.60`, `>0.80` |
| Mission age | 0-3 | 365, 730, 1095 day thresholds |
| Orbit error | 0-2 | 250 m and 500 m thresholds |

Final DEGR is clamped to 15.

DEGR drives correction weights:

| DEGR | Weight |
|---|---|
| 0 | 1.000 |
| 4 | 0.733 |
| 8 | 0.467 |
| 12 | 0.200 |
| 14 | 0.067 |
| 15 | 0.050 floor |

Test evidence: IT-02 logs report `bad_weight=0.067`, `dist_to_healthy=1.146`, and `dist_to_bad=51.568`, verifying that a heavily degraded satellite contributes far less than a healthy peer.

## Correction Filters

All correction algorithms implement the same C++ interface:

```cpp
class CorrectionFilter {
public:
    virtual bool apply(const CorrectionInput& input, CorrectionOutput& output) = 0;
};
```

`CorrectionInput` carries up to 8 `Vec3Reading` values plus weights. `CorrectionOutput` carries the corrected reading, confidence, and used-count. If no filter is configured, the state machine falls back to a raw weighted average.

### Weighted Median Filter

Implemented behavior:

1. For each axis x/y/z, sort readings by axis value.
2. Clamp negative weights to zero.
3. Accumulate sorted weights.
4. Return the first value where cumulative weight reaches 50% of total weight.
5. Confidence is `min(1.0, total_weight / 8.0)`.
6. Timestamp is the latest input timestamp.

Best documented use: robust outlier rejection when bad readings are sparse. Benchmarks show it can degrade under high Gaussian noise.

### Kalman Filter

Implemented behavior:

| Element | Code-backed detail |
|---|---|
| State | `[x, y, z, vx, vy, vz]` |
| Process model | Constant velocity with `dt_s` clamped to 0.01-5.0 seconds |
| Initial state | zeros |
| Initial covariance | `10.0` on the diagonal |
| Measurement | Weighted x/y/z average of neighbour readings |
| Measurement noise | `r_eff = r / max(total_w, 0.05)` |
| Process noise | Added with standard constant-velocity position/velocity terms |
| Matrix inversion | Explicit 3x3 inverse for innovation covariance |
| Covariance update | Stabilized update with symmetrization |

Default constructor values are `process_noise=0.01` and `measurement_noise=1.0`; docs and Python examples also use tuned values such as `q=0.02`, `r=0.8`.

### Hybrid Filter

Implemented behavior:

1. Run the weighted median filter.
2. Feed the median result as a single weighted measurement into the Kalman filter.
3. Return the Kalman-smoothed output.

The comparative docs recommend Hybrid for production-like mixed noise and persistent bias environments, while pure Kalman is strongest when noise is close to Gaussian.

### NIS-Gated Kalman

The docs and Python benchmarks include an NIS-gated Kalman variant based on normalized innovation squared and a chi-square threshold. In the core C++ correction source available here, the named classes are `WeightedMedianFilter`, `KalmanFilter`, and `HybridFilter`; NIS-gated behavior appears as a benchmark/harness concept rather than a separate C++ class in `sisp_correction.hpp`.

## SVD Anomaly Detection

SISP contains two related SVD implementations:

| Path | Role |
|---|---|
| `sisp_svd_anomaly.py` | Monolithic CLI/library SVD anomaly pipeline with optional chi-square gate |
| `sisp/` + `pipelines/` | Modular ingest, preprocessing, SVD, and evaluation pipeline |

### Dataset

The docs identify the dataset as OPSSAT-AD, Zenodo record `12588359`. The pipeline expects segment-level telemetry rows with metadata and 19 engineered feature columns.

Configured feature columns:

`sampling`, `duration`, `len`, `mean`, `var`, `std`, `skew`, `kurtosis`, `n_peaks`, `smooth10_n_peaks`, `smooth20_n_peaks`, `diff_peaks`, `diff2_peaks`, `diff_var`, `diff2_var`, `gaps_squared`, `len_weighted`, `var_div_duration`, `var_div_len`.

Configured metadata columns:

`segment`, `anomaly`, `train`, `channel`.

The monolithic `sisp_svd_anomaly.py` also recognizes `label` in its metadata list.

Important implementation split: the modular pipeline and the monolithic CLI are not identical. The modular `sisp/` pipeline uses the feature list from `config/settings.py`, drops rows above `NAN_DROP_THRESHOLD = 0.30`, and converts zero-variance fit-row features into binary deviation indicators. The monolithic `sisp_svd_anomaly.py` has its own configuration, recognizes `label`, uses a 50% NaN-drop threshold in that script, and has its own zero-variance behavior. This dossier treats the modular pipeline as authoritative for `pipelines/` behavior and the monolithic script as a separate CLI/library path.

### Critical Anti-Leakage Rule

The modular pipeline fits all learned quantities only on:

`train == True AND anomaly == False`

This `fit_mask` is used for medians, zero-variance checks, winsor caps, scaling, SVD rank/model fitting, and anomaly thresholds. This is one of the strongest engineering discipline points in the codebase.

### Three-Stage Pipeline

#### Stage 1: Ingest

Implemented in `pipelines/run_ingest.py`.

1. Download/load Zenodo dataset into `data/raw/`.
2. Validate required metadata and feature columns.
3. Group rows by channel.
4. Save full per-channel DataFrames.
5. Split each channel into feature parquet and metadata parquet.
6. Coerce feature dtypes to int64/float64.
7. Write sample CSVs and file summaries.

#### Stage 2: Preprocess

Implemented in `pipelines/run_preprocess.py`.

1. Discover per-channel feature parquet files.
2. Exclude channels listed in `EXCLUDED_CHANNELS` (`CADC0886`, `CADC0890`).
3. Audit NaN counts.
4. Drop rows with NaN fraction above `NAN_DROP_THRESHOLD = 0.30`.
5. Impute remaining NaNs with fit-row medians, with overall median fallback.
6. Detect zero-variance columns on fit rows using `ZERO_VAR_EPSILON = 1e-8`.
7. Convert zero-variance columns into binary deviation indicators.
8. Winsorize continuous columns using fit-row quantiles `WINSOR_LOW = 0.01` and `WINSOR_HIGH = 0.99`.
9. Fit `StandardScaler` on fit-row continuous columns.
10. Pass binary columns through unchanged.
11. Validate scaled fit/test moments and binary counts.
12. Persist clean, winsorized, scaled, scaler, feature-name, and binary-feature artifacts.

#### Stage 3: SVD and Evaluation

Implemented in `pipelines/run_svd.py`.

1. Discover scaled feature files.
2. Load scaled features and clean metadata.
3. Build `X_fit` using the fit mask.
4. Select rank with a probe `TruncatedSVD`.
5. Pick the smallest k reaching `SVD_VARIANCE_TARGET = 0.90`, clamped to `SVD_K_MIN = 2` and `SVD_K_MAX = 15`.
6. Fit final `TruncatedSVD(n_components=k, random_state=42)`.
7. Compute reconstruction error `||x - inverse_transform(transform(x))||^2`.
8. Threshold at the `ANOMALY_THRESHOLD_PCTILE = 95` percentile of fit-row errors.
9. Predict `error > threshold`.
10. Report confusion matrix, precision, recall, F1, and ROC-AUC for train and test splits.
11. Save per-channel result parquet with segment, train flag, anomaly flag, reconstruction error, threshold, and predicted anomaly.

### Chi-Square / NIS Gate

The monolithic `sisp_svd_anomaly.py` has:

| Parameter | Value |
|---|---|
| `use_chi_square` | `True` |
| `chi_square_confidence` | `0.95` |
| Threshold function | `scipy.stats.chi2.ppf(confidence, df=k)` |

The docs describe rejecting readings whose normalized reconstruction error exceeds the 95% chi-square critical value. Scope caveat: chi-square gating is implemented in the monolithic SVD script and appears in docs/benchmark concepts; the modular `sisp/anomaly` pipeline thresholds reconstruction error only, and the C++ correction classes do not expose a separate NIS-gated filter class in `sisp_correction.hpp`.

### Reported SVD Performance

Docs report channel `CADC0894` achieving ROC-AUC `0.84` with k around 4 and a 95th percentile threshold around `4.50`. This is a documented result; the current logs inspected in `logs/` do not include a fresh SVD pipeline run.

## Dual-PHY and Signal Physics

SISP's implemented PHY profile enum contains:

| Profile | Value | Meaning |
|---|---|---|
| `CONTROL_437_NARROW` | `0x00` | 10/12.5 kHz-class always-on control PHY |
| `BULK_437_WIDE` | `0x01` | 20/25 kHz-class emergency/bulk PHY |

The C++ state machine selects PHY with these rules:

1. If service is not `DOWNLINK_DATA` or `DOWNLINK_ACK`, use `CONTROL_437_NARROW`.
2. If destination is broadcast, use `CONTROL_437_NARROW`.
3. If local node supports bulk, active bulk PHY is bulk, and peer supports bulk, use `BULK_437_WIDE`.
4. Otherwise fall back to `CONTROL_437_NARROW`.

The selected PHY is encoded in frame byte 8 and exposed to Python tests.

### Frequency and Channelization

Docs describe:

| Profile | Bandwidth | Bit rate assumption | Use |
|---|---|---|---|
| Control | 12.5 kHz practical channel | 12,500 bps for GMSK-like 1 bit/s/Hz | Correction, status, heartbeat, relay/borrow control, failure |
| Bulk | 25 kHz practical channel | 25,000 bps for GMSK-like 1 bit/s/Hz | `DOWNLINK_DATA`, `DOWNLINK_ACK` when negotiated |

The hardware study also discusses a conceptual 10 kHz control + 20 kHz emergency design, mapped to practical 12.5/25 kHz COTS channelization.

### Signal Models

Implemented and documented models include:

| Model | Formula/approach |
|---|---|
| BPSK/QPSK AWGN | `0.5 * erfc(sqrt(Eb/N0))` |
| GMSK BT=0.3 | `0.5 * erfc(sqrt(0.68 * Eb/N0))` |
| 2-FSK coherent | `Q(sqrt(Eb/N0))` |
| 2-FSK noncoherent | `0.5 * exp(-Eb/(2N0))` |
| K=7 R=1/2 convolutional | Heller-Jacobs leading union bound `36 * Q(sqrt(10 * Eb/N0))` |
| RS(255,223) | Binomial byte-error tail, failure if more than 16 byte errors |
| PER | `1 - (1 - BER)^512`, implemented stably with `log1p` |
| FSPL | Friis free-space path loss |
| Noise | `N = k * T_sys * B` |
| Doppler | `delta_f = f_c * range_rate / c` |

### Key Physical Numbers

| Quantity | Repo value |
|---|---|
| UHF center | Around 437 MHz |
| UHF allocation discussed | 435-438 MHz amateur satellite range |
| UHF FSPL at 1000 km | About 145.2-145.3 dB |
| Ka FSPL at 26 GHz and 1000 km | About 180.7 dB |
| UHF path-loss advantage vs Ka at same range | About 35 dB |
| Max LEO Doppler at 437 MHz using 7.5 km/s | About 10.9 kHz |
| GMSK BT=0.3 penalty vs BPSK | 1.67 dB |
| Conv+RS expansion | About 2.287x |
| 64-byte frame with Conv+RS | About 1,171 air bits |
| Reference control frame time at 12.5 kbps | 93.6 ms |
| Reference bulk frame time at 25 kbps | 46.8 ms |

### Geometry Model

The orbital geometry docs and simulator use:

| Model | Description |
|---|---|
| ECI state vectors | Satellite position and velocity vectors from Skyfield/SGP4 |
| Earth blockage | Line-of-sight exists when central angle is less than the sum of horizon angles |
| Slant range | Norm of relative position |
| Range rate | Dot product of relative position and velocity divided by slant range |
| Doppler | Carrier-scaled range rate over speed of light |

The geometry is used to estimate LoS windows, slant range, Doppler, and ground-station contact.

## Energy Model

The energy model is a DC power model layered on top of frame timing:

| Parameter | Value |
|---|---|
| Tx DC power | 10 W |
| Rx DC power | 2.5 W |
| Frame size | 64 bytes / 512 bits |
| Control Conv+RS frame time | 93.6 ms at 12.5 kbps |
| Bulk Conv+RS frame time | 46.8 ms at 25 kbps |

### Correction Snapshot Energy

For N=8 neighbours, Conv+RS, 12.5 kHz control:

| Item | Value |
|---|---|
| On-air time | About 849 ms including propagation |
| Fits 5-second timer | Yes |
| Requester TX | 0.936 J |
| Requester RX | 1.87 J |
| Neighbour TX total | 7.49 J |
| Neighbour RX total | 1.87 J |
| Network total | About 12.2 J per correction event |
| 24 events/day | About 293 J / 0.081 Wh |

Accuracy note: `docs/SISP_KPI_SNAPSHOT.md` also presents a 6-neighbour correction-energy case with `3.90 J`, `26.0 mWh/day`, and `0.022%`. That snapshot contains an arithmetic/formula conflict under the stated power and frame-time assumptions, so this dossier does not reuse `3.90 J` as an authoritative energy result without recalculation.

### Bulk Relay / Borrow Energy

For a 1 MiB payload, 3x compression, 45 useful bytes per frame, GMSK Conv+RS:

| Channel/config | Time | Energy |
|---|---|---|
| 25 kHz bulk, 1 MiB | About 6.1 min | About 1.26 Wh total TX+RX |
| 25 kHz GMSK Conv+RS, 10 MiB | About 61 min | About 12.6 Wh |
| 25 kHz BPSK Conv+RS, 10 MiB | About 30 min | About 6.26 Wh |

Docs conclude that 1 MiB fits comfortably in a 15-minute LoS window, while 10 MiB does not fit in one window without higher-rate alternatives or multiple passes.

## KPI Snapshot

### Test-Backed Technical KPIs

| KPI | Value | Evidence |
|---|---|---|
| C++ tests | 273/273 pass | `logs/cpp_tests_20260510_200408.log` |
| Encoder/decoder tests | 70/70 pass | C++ log |
| Payload codec tests | 65/65 pass | C++ log |
| 512-bit frame pipeline tests | 21/21 pass | C++ log |
| State machine tests | 38/38 pass | C++ log |
| DEGR tests | 20/20 pass | C++ log |
| Protocol simulation tests | 25/25 pass | C++ log |
| Level-2 state-machine matrix | 34/34 pass | C++ log |
| Dual-PHY assertions | 8/8 pass | Python log |
| 30-day RMSE improvement | 94.3% | IT-05 Python log |
| Packet-loss resilience | 85.6% improvement at 10% packet loss | IT-06 Python log |
| Runtime budget | 500 rounds in 0.004 s, 0.009 ms/round | Python log |
| Relay text recovery | 109/109 bytes relinked | Python log |

### Correction Quality Results

| Scenario | Raw | Corrected | Improvement/gain |
|---|---:|---:|---:|
| IT-05, 30-day correction | RMSE 8.909 | RMSE 0.504 | 94.3% |
| IT-06, 10% packet loss, 7 days | RMSE 8.290 | RMSE 1.197 | 85.6% |
| Kalman 3-sat, sigma 2.0 | 2.502 steady-state error | 1.304 | 47.9-48.0% |
| Kalman 3-sat, sigma 25.0 | 22.705 steady-state error | 8.473 | 62.7% |
| Balanced sigma 20, Kalman | raw ss 21.725 | corr ss 9.403 | gain 12.322 |
| Balanced sigma 60, Kalman | raw ss 66.472 | corr ss 33.633 | gain 32.839 |
| Persistent bias, Hybrid | raw ss 31.204 | corr ss 9.878 | gain 21.327 |
| Mixed spike plus drift, Hybrid | raw ss 20.604 | corr ss 6.716 | gain 13.888 |

### DEGR Model Sensitivity

From `test_noise_weighting_and_algorithms.py`:

| DEGR model | Corrected ss error | Raw ss | Gain |
|---|---:|---:|---:|
| inverse_error | 19.057 | 41.600 | 22.544 |
| neutral | 22.466 | 41.600 | 19.135 |
| proportional_error | 27.851 | 41.600 | 13.749 |

The docs summarize inverse-error weighting as about 17.8% better steady-state correction quality than neutral weighting based on these errors.

### Sustainability and Business KPIs

The KPI snapshot provides a reference scenario. These are scenario assumptions or externally sourced assumptions named by the docs, not direct SISP measurements:

| Parameter | Value |
|---|---|
| Constellation size | 100 satellites |
| Baseline design life | 3 years |
| SISP life extension | +45% to 4.35 years, stated by KPI snapshot |
| Annual sensor failure rate | 12% |
| Sensor recovery via borrowing | 60% |
| Satellite mass | 5 kg |
| Launch cost | $6,000/kg |
| Satellite unit cost | $500K |
| CO2 per launch | 300 t CO2-eq |
| Ground-station contact | 10% of orbit |
| ISL contact | 45% of orbit |
| Growth rate | 12%/yr |

Reference one-year modelled outcomes in the docs:

| Metric | Baseline | With SISP | Change |
|---|---:|---:|---:|
| Replacement launches/year | 33.3 | 23.0 | -10.3/year, -31% |
| CO2 from launches/year | 10,000 t | 6,900 t | -3,100 t/year |
| Recovered via borrowing | 0 | 7.2/year | +7.2 retained missions |
| Mass launched/year | 167 kg | 115 kg | -52 kg/year |
| Mass with modular reduction | 167 kg | 86 kg | -81 kg/year, -49% |

Reference 50-year cumulative modelled scenario:

| Metric | Baseline | With SISP | Saved |
|---|---:|---:|---:|
| Replacement launches | About 75,000 | About 52,000 | About 23,000 |
| CO2 from launches | About 23 Mt | About 16 Mt | About 7 Mt |
| Satellite mass to orbit | About 375,000 t | About 260,000 t | About 115,000 t |
| Replacement cost | About $38B | About $26B | About $12B |
| Satellites recovered | Not baseline-listed | About 28,000 | Sensor-years sustained |

Important evidence note: these sustainability numbers are modelled reference-scenario values from the KPI dashboard/snapshot, not direct mission measurements. The repo does not provide a formula tying the +45% life-extension assumption directly to IT-05; it presents that value as part of the reference scenario.

### SDG Evidence

The repository does not explicitly enumerate United Nations Sustainable Development Goal numbers. It does include sustainability-linked metrics: launch CO2 reduction, replacement launch reduction, mass-to-orbit reduction, recovered satellites, and energy budget. No SDG target numbers, formal SDG mapping, or orbital-debris risk calculations are implemented in the repo.

## Research and Reference Base Mentioned in Docs

The docs cite or name:

| Reference | Used for |
|---|---|
| Murota & Hirade (1981) | GMSK BT=0.3 BER and alpha factor |
| Heller & Jacobs (1971) | K=7 R=1/2 Viterbi union bound |
| Proakis, Digital Communications | Communications theory reference |
| Wold (1987) | PCA/SVD conceptual basis |
| Vallado & Crawford (2008) | SGP4 / orbital mechanics context |
| OPSSAT-AD, Zenodo record 12588359 | Telemetry anomaly detection dataset |
| ITU-R SM.1045 | Frequency tolerance context |
| IARU band plans | Amateur satellite UHF band context |
| Dallas et al. (2020) | Launch emissions reference in KPI snapshot |
| UCS Satellite Database | Satellite growth assumptions in KPI snapshot |

The UHF hardware study also discusses representative CubeSat-class UHF radios and concludes that FSK/GFSK/GMSK/AFSK are the common easier operational modes, while BPSK/QPSK are mathematically attractive but imply SDR/custom modem risk in many cases.

## Solution Path to the "Perfect SISP"

Based strictly on the implemented and documented flows, SISP establishes its goal through these steps:

1. Maintain a compact satellite context per node: state, IDs, timers, neighbour DEGR, PHY capability masks, sensor health masks, correction buffers, relay buffers, borrow request state, and failure tables.
2. Exchange lightweight control messages over `CONTROL_437_NARROW`.
3. Record neighbour health through heartbeat/status/failure messages.
4. Convert multi-source health into a DEGR score.
5. On local sensor fault, broadcast `CORRECTION_REQ`.
6. Neighbours respond with typed `CORRECTION_RSP` readings and their own DEGR in the header.
7. Requester accepts only matching, decodable, sensor-compatible responses.
8. Requester maps each peer DEGR into a bounded trust weight.
9. Timer expiry closes the collection window deterministically.
10. Correction filter runs: raw weighted average fallback, weighted median, Kalman, or Hybrid.
11. Corrected value becomes available in the context.
12. If direct delivery is unavailable or energy/visibility requires help, relay service fragments payloads and sends them through a selected peer.
13. If a sensor is missing locally, borrow service broadcasts a request, records the provider decision payload, and proceeds into the borrow receive path for unicast data transfer.
14. PHY selection keeps all control messages on narrow control and upgrades only bulk data/ACK frames when peer capability supports it.
15. Foreign failures are recorded without cascading local critical state.
16. All message-level behavior stays bounded by timers, retry limits, fixed frame sizes, and static transition rules.

## Validation and Test Surface

The C++ log from `2026-05-10 20:04:08 WCAST` reports:

| Group | Pass |
|---|---:|
| Encode/Decode | 70/70 |
| Payload Codec | 65/65 |
| Frame Pipeline | 21/21 |
| State Machine | 38/38 |
| DEGR Computation | 20/20 |
| Protocol Simulation | 25/25 |
| Level 2 State Machine | 34/34 |
| Total | 273/273 |

Python log evidence includes:

| Test/script | Outcome in inspected log |
|---|---|
| `validate_bpsk_awgn.py` | Completed with expected theory/simulation agreement |
| `test_dual_phy_437.py` | 8 pass, 0 fail |
| `test_borrow_addressing_flow.py` | Completed two cases |
| `test_relay_text_resilience.py` | PASS |
| `test_kalman_gaussian_3sat.py` | Kalman improves nominal and large-fault profiles |
| `test_noise_weighting_and_algorithms.py` | Completed benchmark matrix |
| `test_full_message_propagation_sensor_correction.py` | PASS |
| `test_integration_matrix_it02_it03_it05_it06.py` | ALL MATRIX TESTS PASSED |
| `test_no_cascade.py` | Checked-in log failed due to Windows console Unicode encoding of a checkmark; rerun with `PYTHONIOENCODING=utf-8` passes |

Because the no-cascade Python run in the inspected log hit a `UnicodeEncodeError`, this dossier treats that log entry as an encoding artifact rather than a protocol failure. A local rerun with `PYTHONIOENCODING=utf-8` passed, and no-cascade behavior is also supported by the C++ transition table, C++ test coverage, README/test-result summaries, and the implemented `RX_FAILURE` self-loop.

## Internal Discrepancies and Accuracy Notes

The repo is strong, but several docs are not perfectly synchronized:

| Topic | Discrepancy | Conservative treatment in this dossier |
|---|---|---|
| C++ test count | `QUICK_REFERENCE.md` contains older 246/older protocol simulation counts, while root README, test results, and current log show 273/273 | Use 273/273 as current logged evidence; note older quick-reference drift |
| Python test suite | Docs say all Python tests pass; inspected log has `test_no_cascade.py` encoding failure, while UTF-8 rerun passes | Report specific passing scripts, the checked-in log artifact, and the UTF-8 rerun result |
| SVD preprocessing threshold | `README_02_SVD_CHI_SQUARE.md` says drop rows with >50% NaN; code and architecture config use 30% | Use code-backed `NAN_DROP_THRESHOLD = 0.30` |
| Zero-variance handling | Some docs say drop zero-variance features; code converts them to binary deviation indicators | Use code-backed binary transform |
| Kalman measurement noise | Some docs describe DEGR-average inflation; current C++ code uses total-weight scaling `r / max(total_w, 0.05)` | Use implementation behavior |
| Energy per correction | Research paper has a smaller per-correction estimate than energy README/KPI snapshot scenarios | Present scenario-specific values and avoid one universal number |
| Service names in Streamlit | One mapping in `sisp_unified_sim.py` appears inconsistent with C++ service enum for some numeric labels | Use C++ `sisp_protocol.hpp` as authoritative |
| NIS-gated Kalman | Docs/benchmarks discuss it; C++ header exposes weighted median, Kalman, and Hybrid classes | Describe NIS as documented/benchmark variant unless a separate implementation is located |

## Innovation Assessment From Repo Evidence

The project's strongest innovation story is the integration, not just any single algorithm:

1. A deterministic embedded state machine coordinates correction, relay, borrow, failure, and reset behavior.
2. The protocol treats neighbours as a distributed redundancy layer.
3. DEGR turns health into continuous trust and directly changes correction weights.
4. SVD anomaly detection is positioned in the docs as a pre-correction screen; the live C++ correction path currently filters by protocol fields, sensor mask, and DEGR only.
5. The correction layer is pluggable and decoupled from protocol flow.
6. The PHY profile is negotiated and encoded per frame, allowing control and bulk traffic to use different robustness/throughput assumptions.
7. Energy and sustainability are first-class, with frame-level power accounting linked to constellation-scale KPIs.
8. The repo includes deterministic tests, physical-layer validation, and dashboard tooling instead of only conceptual documentation.

## Current Limitations

These limitations are stated or implied by repo files:

| Limitation | Evidence |
|---|---|
| AWGN models are simplified | Scientific report notes no fading/interference/adjacent-channel model |
| RS model is a proxy | Docs call it a binomial byte-error approximation |
| Some signal studies are design guidance | UHF hardware study says later PHY switch control messages are design-only |
| Some docs are stale | Quick reference and architecture sub-doc names differ from current files |
| Checked-in test evidence needs rebuild caveat | The 273/273 result is valid for the checked-in/prebuilt test runner log; some source/log details, such as `Status` payload size after `phy_cap_mask`, are not fully synchronized, so rebuild before claiming current-source validation |
| Sustainability values are scenario-derived | KPI snapshot provides assumptions and formulas rather than measured mission data |
| SVD integration into live C++ correction path is conceptual/documented | C++ state machine currently filters correction responses by protocol fields and DEGR; SVD model lives in Python pipeline/CLI |

## One-Screen Summary

SISP is a compact autonomous satellite service protocol. It uses a 21-state, 24-event C++ state machine and a 64-byte fixed frame to coordinate correction, relay, borrowing, heartbeat/status, and failure handling. Its strongest technical chain is: detect local fault, ask neighbours for readings, reject incompatible inputs, weight responses by DEGR, run a pluggable correction filter, and preserve constellation stability through no-cascade failure isolation. Around that core, the repo adds an OPSSAT-AD SVD anomaly pipeline, a dual-profile 437 MHz PHY model, BER/PER validation, energy accounting, and sustainability KPIs. The standout measured results are 273/273 C++ tests, 94.3% RMSE improvement over a 30-day correction scenario, 85.6% improvement with 10% packet loss, 8/8 dual-PHY assertions, and relay recovery of a 109-byte multi-fragment text payload through corruption, out-of-order delivery, and duplicate replay.
