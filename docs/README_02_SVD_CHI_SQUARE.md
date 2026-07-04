
# On‑Board Anomaly Detection via Time‑Lagged SVD

**Source files:**

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Pipeline architecture and design rules |
| `HOW_SVD_Works.md` | Mathematical explanation and intuition |
| `data/raw/segments.csv` | OPSSAT-AD telemetry dataset (Zenodo 12588359), used only for the initial feasibility study |

---

## Purpose

Before a neighbour’s correction response is accepted into the Kalman filter, SISP screens it with an on‑board anomaly detector that works directly on the raw sensor time series. A reading that introduces a sudden structural break in the sender’s recent temporal pattern is discarded, preventing corrupted or faulty data from biasing the distributed estimate.

---

## On‑Board Method: Sliding‑Window Hankel‑SVD

### Hankel Matrix Construction

The detector operates on a single scalar telemetry channel (e.g., magnetometer X‑axis). The satellite maintains a sliding window of the last \(W\) raw samples \([s_1, s_2, \dots, s_W]\). From this window we build a Hankel matrix \(H \in \mathbb{R}^{m \times n}\) (typical size \(m = n \approx 50\)):

\[
H = \begin{bmatrix}
s_1 & s_2 & \dots & s_n \\
s_2 & s_3 & \dots & s_{n+1} \\
\vdots & \vdots & \ddots & \vdots \\
s_m & s_{m+1} & \dots & s_{m+n-1}
\end{bmatrix}
\]

Because each row is a shifted copy of the signal, the rank and singular spectrum of \(H\) capture the temporal dynamics. Under nominal conditions the signal is dominated by a few coherent modes (e.g., orbital periodicity, slow thermal drift), so the singular values decay rapidly. A structural break—a sudden fault, drift change, or noise burst—injects energy into the smaller singular values, altering the singular spectrum.

### Anomaly Score: Off‑Diagonal Singular Value Ratio

The SVD of \(H = U \Sigma V^\top\) is computed (or efficiently updated with a rank‑1 modification when the window slides). The anomaly score is the **off‑diagonal singular value energy ratio**:

\[
\rho = \frac{\sum_{i=2}^{\min(m,n)} \sigma_i}{\sum_{i=1}^{\min(m,n)} \sigma_i}
\]

- When the signal is nominal, \(\sigma_1\) dominates and \(\rho\) remains small.
- A sharp increase in \(\rho\) above a pre‑set threshold \(\tau_\rho\) indicates a structural break, triggering the internal `FAULT_DETECTED` event.

The threshold \(\tau_\rho\) is set once from a historical set of nominal windows and can be tuned per mission.

**Why this works:** Any physical change that breaks the linear dependence in successive values (e.g., a sudden offset, stuck sensor, or erratic noise) immediately increases the off‑diagonal singular value energy, because the new data can no longer be well represented by the previous low‑rank pattern.

### On‑Board Feasibility

- **Lightweight:** A 50 × 50 Hankel matrix occupies under 20 KB. The rank‑1 SVD update costs \(O(mn)\) per new sample, easily achievable on a CubeSat OBC.
- **Autonomous:** No ground‑trained model is required; the detector runs continuously on the raw sensor stream.

---

## Integration with Correction Layer

The same detector is used in two ways:

1. **Self‑monitoring:** The satellite computes \(\rho\) on its own channels. If \(\rho > \tau_\rho\) for any channel, it raises `FAULT_DETECTED` and initiates a correction request.
2. **Peer‑response screening:** For each neighbour, a small sliding window of that neighbour’s recent readings (for the same physical channel) is maintained. When a `CORRECTION_RSP` arrives, the new reading is temporarily added to the neighbour’s window, and \(\rho\) is recalculated. If adding the reading causes \(\rho\) to exceed \(\tau_\rho\), the response is considered inconsistent and discarded.

```mermaid
flowchart TD
    A[Neighbour sends CORRECTION_RSP] --> B[Update neighbour's sliding window with new reading]
    B --> C[Compute ρ from Hankel matrix of window]
    C --> D{ρ > τ_ρ?}
    D -- yes --> E[Reject anomalous reading]
    D -- no --> F[Buffer into ctx.rsp_readings[rsp_count]]
    F --> G[Set ctx.rsp_weights[rsp_count] from DEGR]
    G --> H[rsp_count++]
    H --> I[Timer expires]
    I --> J[Run correction filter on buffered readings]
```

---

## Static SVD Validation on OPS‑SAT Telemetry (Feasibility Study)

To verify that an SVD‑based approach can distinguish nominal from anomalous data, we conducted an offline feasibility study using the **OPSSAT-AD** dataset (Zenodo record 12588359). This study trained a **static** SVD model on 19 aggregate features per segment (mean, variance, etc.) and used a reconstruction‑error threshold. Key results:

- ROC‑AUC up to **0.99** on several channels (e.g., CADC0873, CADC0888).
- The nominal subspace is low‑dimensional (\(k = 5–6\) out of 19 features), confirming that normal behaviour is tightly bounded.

The on‑board sliding‑window Hankel‑SVD replaces the static multi‑feature model with a real‑time, retraining‑free detector that works directly on raw samples. The static study remains valuable as independent validation of the core idea.

---

## Tuning Parameters

| Parameter | Default | Effect |
|---|---|---|
| Window length \(W\) | 100 samples | Amount of history used for the Hankel matrix |
| Hankel rows \(m\) | 50 | Balance between frequency resolution and update cost |
| Threshold \(\tau_\rho\) | 0.15 (example) | Set from nominal data; lower = more sensitive |
| SVD update method | Rank‑1 update | Real‑time operation |

---

## Design Rules

1. **No label leakage.** Thresholds are computed exclusively from nominal historical data.
2. **Determinism.** The sliding‑window update and SVD computation are deterministic; no stochastic operations at runtime.
3. **Lightweight.** Memory per channel < 20 KB; per‑sample update < 1 ms on typical CubeSat processors.
4. **Autonomy.** Once \(\tau_\rho\) is set, the detector runs without any ground intervention.
```