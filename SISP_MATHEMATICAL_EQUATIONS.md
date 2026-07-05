# SISP Mathematical Equations Reference

This document extracts the main mathematical equations used across SISP and gives the context for each one. It consolidates equations from the protocol docs, SVD/anomaly pipeline, C++ correction layer, signal/physics simulations, energy model, sustainability dashboard, and research paper.

Source scope:

- `docs/README_02_SVD_CHI_SQUARE.md`
- `docs/README_03_CORRECTION_ALGORITHMS.md`
- `docs/README_04_SIGNAL_PHYSICS.md`
- `docs/README_05_ENERGY_STUDY.md`
- `docs/SISP_RESEARCH_PAPER.md`
- `simulation for signal and physics/sisp_unified_sim.py`
- `simulation for signal and physics/sisp_common_band_sim.py`
- `simulation for signal and physics/sisp_signal_sim.py`
- `simulation for signal and physics/sisp_value_dashboard.py`
- `simulation for signal and physics/SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md`
- `simulation for signal and physics/UHF_437_two_mode_phy_hardware_math_study.md`
- `sisp/anomaly/svd.py`
- `sisp_svd_anomaly.py`
- `c++ implemnetation/src/sisp_protocol.cpp`
- `c++ implemnetation/src/sisp_correction.cpp`
- `c++ implemnetation/src/sisp_state_machine.cpp`

## 1. Telemetry Feature Extraction

These equations are used when raw telemetry samples are converted into segment-level features for the anomaly detection pipeline.

Let a segment contain samples \(v_1, v_2, ..., v_n\).

### Mean

```math
\mu = \frac{1}{n}\sum_{i=1}^{n} v_i
```

Context: feature column `mean`; used by the SVD anomaly detector.

### Variance and Standard Deviation

```math
\sigma^2 = \frac{1}{n}\sum_{i=1}^{n}(v_i-\mu)^2
```

```math
\sigma = \sqrt{\sigma^2}
```

Context: feature columns `variance`, `var`, `std`; used to characterize telemetry volatility.

### Root Mean Square

```math
\mathrm{RMS} = \sqrt{\frac{1}{n}\sum_{i=1}^{n} v_i^2}
```

Context: feature column `rms`; captures signal magnitude independent of sign.

### Absolute Mean

```math
\mathrm{abs\_mean} = \frac{1}{n}\sum_{i=1}^{n}|v_i|
```

Context: feature column `abs_mean`; used in the monolithic SVD pipeline.

### Range

```math
\mathrm{range} = \max(v) - \min(v)
```

Context: feature column `range`; captures peak-to-peak spread.

### Interquartile Range

```math
\mathrm{IQR} = Q_{75} - Q_{25}
```

Context: feature column `iqr`; robust spread measure.

### Energy

```math
E_{\mathrm{segment}} = \sum_{i=1}^{n} v_i^2
```

Context: feature column `energy`; not spacecraft energy, but signal/segment energy.

### Linear Trend Slope

```math
v_i \approx a i + b
```

```math
\mathrm{slope} = a
```

Context: feature column `slope`; computed by linear regression/polyfit in `sisp_svd_anomaly.py`.

### Zero or Mean Crossings

```math
n_{\mathrm{cross}} =
\sum_{i=1}^{n-1}
\mathbf{1}\left[
\mathrm{sign}(v_i-\mu) \ne \mathrm{sign}(v_{i+1}-\mu)
\right]
```

Context: feature column `n_crossings`; counts oscillations around the segment mean.

### Autocorrelation at Lag \(l\)

```math
\rho_l =
\frac{\mathrm{cov}(v_{1:n-l}, v_{1+l:n})}
{\sigma(v_{1:n-l})\sigma(v_{1+l:n})}
```

Context: feature columns `autocorr_1`, `autocorr_2`; captures temporal self-similarity.

## 2. Preprocessing Equations

These equations are used before SVD fitting.

### NaN Fraction Per Row

```math
f_{\mathrm{NaN}}(x_i) =
\frac{\#\{\mathrm{NaN\ features\ in\ row}\ i\}}{\#\{\mathrm{features}\}}
```

Rows are dropped when:

```math
f_{\mathrm{NaN}}(x_i) > \theta_{\mathrm{NaN}}
```

Context: modular pipeline uses `NAN_DROP_THRESHOLD = 0.30`; monolithic script uses `0.50`.

### Median Imputation

```math
x_{ij} =
\begin{cases}
x_{ij}, & x_{ij}\ \mathrm{is\ finite} \\
\mathrm{median}(x_{\cdot j}), & x_{ij}\ \mathrm{is\ NaN}
\end{cases}
```

Context: fills missing feature values before scaling and SVD.

### Winsorization

```math
x'_{ij} = \min\left(\max(x_{ij}, q_{0.01,j}), q_{0.99,j}\right)
```

Context: clips continuous features to the 1st and 99th percentiles, fit on nominal training rows.

### Standard Scaling

```math
z_{ij} = \frac{x_{ij}-\mu_j}{\sigma_j}
```

Context: transforms continuous features to comparable scale before SVD. Parameters are fit only on nominal training rows.

### Zero-Variance Test

```math
\sigma_j \le \epsilon
```

Context: modular preprocessing treats near-zero-variance columns as constant features and converts deviations into binary indicators. `ZERO_VAR_EPSILON = 1e-8`.

### Binary Deviation Indicator

```math
b_{ij} =
\begin{cases}
0, & |x_{ij}-c_j| \le \epsilon \\
1, & |x_{ij}-c_j| > \epsilon
\end{cases}
```

Context: preserves anomaly signal from normally constant telemetry features.

## 3. SVD Anomaly Detection

### SVD Factorization

```math
X = U\Sigma V^T
```

Context: fits a low-rank representation of nominal telemetry segments.

### Rank-\(k\) Truncation

```math
X \approx X_k = U_k\Sigma_k V_k^T
```

Context: keeps only the dominant nominal subspace.

### Cumulative Explained Variance

```math
\mathrm{CEV}(k) =
\frac{\sum_{i=1}^{k}\sigma_i^2}{\sum_{i=1}^{p}\sigma_i^2}
```

Rank selection:

```math
k^* = \min\{k: \mathrm{CEV}(k) \ge 0.90\}
```

Bounded by:

```math
k = \min(\max(k^*, k_{\min}), k_{\max})
```

Context: `SVD_VARIANCE_TARGET = 0.90`, `SVD_K_MIN = 2`, `SVD_K_MAX = 15`.

### Projection and Reconstruction

For the modular sklearn implementation:

```math
y = \mathrm{SVD.transform}(x)
```

```math
\hat{x} = \mathrm{SVD.inverse\_transform}(y)
```

For the monolithic matrix implementation:

```math
\hat{x} = x V_k^T V_k
```

Context: reconstructs each row from the nominal subspace.

### Reconstruction Error

```math
\epsilon_i = \|x_i-\hat{x}_i\|_2^2
```

Expanded:

```math
\epsilon_i = \sum_{j=1}^{p}(x_{ij}-\hat{x}_{ij})^2
```

Context: primary anomaly score.

### Percentile Threshold

```math
\tau_{95} = \mathrm{quantile}_{0.95}\left(\{\epsilon_i: i \in \mathrm{fit\ rows}\}\right)
```

Prediction rule:

```math
\hat{y}_i =
\begin{cases}
1, & \epsilon_i > \tau_{95} \\
0, & \epsilon_i \le \tau_{95}
\end{cases}
```

Context: flags anomalous telemetry segments.

### Chi-Square/NIS Gate

```math
\frac{\epsilon}{\sigma_\epsilon^2} \sim \chi^2(k)
```

```math
\mathrm{NIS} = \frac{\epsilon}{\sigma_\epsilon^2}
```

Gate:

```math
\mathrm{NIS} > \chi^2_{k,0.95}
```

Context: monolithic SVD pipeline and docs use this as an additional anomaly gate.

## 4. DEGR Trust and Health Scoring

DEGR is a 4-bit degradation score in \([0,15]\). It is used in correction weighting and protocol health reporting.

### K-Factor Deviation

```math
d_k = |k_{\mathrm{factor}} - 1|
```

Bucketed contribution:

```math
s_k =
\begin{cases}
5, & d_k \ge 0.50 \\
4, & 0.40 \le d_k < 0.50 \\
3, & 0.30 \le d_k < 0.40 \\
2, & 0.20 \le d_k < 0.30 \\
1, & 0.10 \le d_k < 0.20 \\
0, & d_k < 0.10
\end{cases}
```

Context: `compute_degr()` in `sisp_protocol.cpp`.

### SVD Residual Score

```math
s_{\mathrm{svd}} =
\begin{cases}
5, & r_{\mathrm{svd}} > 0.80 \\
4, & r_{\mathrm{svd}} > 0.60 \\
3, & r_{\mathrm{svd}} > 0.40 \\
2, & r_{\mathrm{svd}} > 0.20 \\
1, & r_{\mathrm{svd}} > 0.00 \\
0, & r_{\mathrm{svd}} = 0
\end{cases}
```

Context: bucketed normalized residual contribution to DEGR.

### Mission Age Score

```math
s_{\mathrm{age}} =
\begin{cases}
3, & \mathrm{age\_days} \ge 1095 \\
2, & 730 \le \mathrm{age\_days} < 1095 \\
1, & 365 \le \mathrm{age\_days} < 730 \\
0, & \mathrm{age\_days} < 365
\end{cases}
```

Context: older satellites receive higher degradation score.

### Orbit Error Score

```math
s_{\mathrm{orbit}} =
\begin{cases}
2, & |\Delta r| \ge 500\ \mathrm{m} \\
1, & 250\ \mathrm{m} \le |\Delta r| < 500\ \mathrm{m} \\
0, & |\Delta r| < 250\ \mathrm{m}
\end{cases}
```

Context: orbit/ADCS deviation contribution.

### Final DEGR

```math
\mathrm{DEGR} = \min(15,\ s_k+s_{\mathrm{svd}}+s_{\mathrm{age}}+s_{\mathrm{orbit}})
```

Context: protocol-level health score.

### DEGR-Derived Correction Weight

```math
w_i = \max(0.05,\ 1-\mathrm{DEGR}_i/15)
```

Context: used when accepting `CORRECTION_RSP` messages. Healthy nodes dominate; failed nodes remain visible but heavily down-weighted.

## 5. Correction and Sensor Fusion

### Weighted Average Fallback

```math
\hat{r} =
\frac{\sum_i w_i r_i}{\sum_i w_i}
```

Axis-wise:

```math
\hat{x}=\frac{\sum_i w_i x_i}{\sum_i w_i},\quad
\hat{y}=\frac{\sum_i w_i y_i}{\sum_i w_i},\quad
\hat{z}=\frac{\sum_i w_i z_i}{\sum_i w_i}
```

Context: fallback when no correction filter is configured.

### Weighted Median

For one axis \(a \in \{x,y,z\}\), sort readings by value:

```math
r_{(1),a} \le r_{(2),a} \le ... \le r_{(n),a}
```

Find the first index \(m\) such that:

```math
\sum_{j=1}^{m}w_{(j)} \ge \frac{1}{2}\sum_{j=1}^{n}w_{(j)}
```

Return:

```math
\hat{r}_a = r_{(m),a}
```

Context: robust correction filter in `sisp_correction.cpp`.

### Correction Confidence

```math
\mathrm{confidence} = \min\left(1,\ \frac{\sum_i w_i}{8}\right)
```

Context: C++ correction output confidence; state machine buffers up to 8 neighbour responses.

## 6. Kalman Filter Equations

SISP uses a 6-state constant-velocity Kalman filter for 3-axis readings.

### State Vector

```math
\mathbf{x} =
[x,\ y,\ z,\ v_x,\ v_y,\ v_z]^T
```

### State Transition

```math
\mathbf{x}_{k|k-1} = F\mathbf{x}_{k-1}
```

With:

```math
F =
\begin{bmatrix}
1&0&0&dt&0&0\\
0&1&0&0&dt&0\\
0&0&1&0&0&dt\\
0&0&0&1&0&0\\
0&0&0&0&1&0\\
0&0&0&0&0&1
\end{bmatrix}
```

Context: `c++ implemnetation/src/sisp_correction.cpp`.

### Time Step Clamp

```math
dt = \mathrm{clamp}\left(\frac{t_{\mathrm{meas}}-t_{\mathrm{last}}}{1000},\ 0.01,\ 5.0\right)
```

Context: prevents unstable zero or extremely large time steps.

### Covariance Prediction

```math
P_{k|k-1} = F P_{k-1} F^T + Q
```

The implementation adds constant-velocity process noise terms per axis:

```math
Q_{pp} \mathrel{+}= 0.25\,dt^4 q
```

```math
Q_{pv} \mathrel{+}= 0.5\,dt^3 q
```

```math
Q_{vp} \mathrel{+}= 0.5\,dt^3 q
```

```math
Q_{vv} \mathrel{+}= dt^2 q
```

Context: embedded-friendly process model.

### Weighted Measurement

```math
\mathbf{z} =
\frac{\sum_i w_i \mathbf{r}_i}{\sum_i w_i}
```

Context: measurement vector derived from neighbour readings.

### Effective Measurement Noise

Implementation-backed C++ model:

```math
r_{\mathrm{eff}} = \max\left(10^{-6},\ \frac{r}{\max(\sum_i w_i,\ 0.05)}\right)
```

Docs also describe an older/declarative DEGR-average model:

```math
R_{\mathrm{eff}} =
R_{\mathrm{base}}\left(1+\frac{\bar{D}}{4}\right)
```

Use the first equation as the current C++ implementation behavior.

### Innovation

```math
\mathbf{y} = \mathbf{z} - H\mathbf{x}_{k|k-1}
```

With position-only observation:

```math
H = [I_3\ 0_3]
```

### Innovation Covariance

```math
S = HPH^T + R
```

In implementation, because \(H\) selects the first three state dimensions:

```math
S_{ij}=P_{ij},\quad i,j<3
```

then:

```math
S_{00}\mathrel{+}=r_{\mathrm{eff}},\quad
S_{11}\mathrel{+}=r_{\mathrm{eff}},\quad
S_{22}\mathrel{+}=r_{\mathrm{eff}}
```

### Kalman Gain

```math
K = P H^T S^{-1}
```

Implementation:

```math
K_{ij} = \sum_{k=0}^{2} P_{ik} S^{-1}_{kj}
```

### State Update

```math
\mathbf{x}_k = \mathbf{x}_{k|k-1} + K\mathbf{y}
```

### Joseph-Style Covariance Update

```math
P_k = (I-KH)P_{k|k-1}(I-KH)^T + K R K^T
```

Context: numerically safer covariance update used in C++.

### NIS Gate

```math
\mathrm{NIS} = \mathbf{y}^T S^{-1}\mathbf{y}
```

Reject when:

```math
\mathrm{NIS} > \chi^2_{3,0.95}=7.815
```

Context: documented NIS-gated Kalman variant for suspicious innovations.

### 3x3 Matrix Inverse

For:

```math
A =
\begin{bmatrix}
a&b&c\\
d&e&f\\
g&h&i
\end{bmatrix}
```

Determinant:

```math
\det(A)=a(ei-fh)-b(di-fg)+c(dh-eg)
```

Adjugate terms in code:

```math
A_1=ei-fh,\quad B_1=-(di-fg),\quad C_1=dh-eg
```

```math
D_1=-(bi-ch),\quad E_1=ai-cg,\quad F_1=-(ah-bg)
```

```math
G_1=bf-ce,\quad H_1=-(af-cd),\quad I_1=ae-bd
```

Inverse:

```math
A^{-1} = \frac{1}{\det(A)}
\begin{bmatrix}
A_1&D_1&G_1\\
B_1&E_1&H_1\\
C_1&F_1&I_1
\end{bmatrix}
```

Context: embedded implementation avoids external LAPACK dependency.

## 7. Geometry and Orbital Line of Sight

### Position Norms

```math
r_A = \|\mathbf{r}_A\|,\quad r_B = \|\mathbf{r}_B\|
```

### Central Angle

```math
\gamma(t) =
\arccos\left(
\frac{\mathbf{r}_A(t)\cdot\mathbf{r}_B(t)}
{r_A r_B}
\right)
```

Context: spherical Earth blockage model.

### Earth Exclusion Radius

```math
R_{\mathrm{excl}} = R_E + h_{\mathrm{clear}}
```

Context: includes optional clearance above Earth radius.

### Line-of-Sight Criterion

```math
\gamma(t) <
\arccos\left(\frac{R_{\mathrm{excl}}}{r_A}\right)
+
\arccos\left(\frac{R_{\mathrm{excl}}}{r_B}\right)
```

Context: determines whether two satellites can communicate.

### Slant Range

```math
d(t)=\|\mathbf{r}_B(t)-\mathbf{r}_A(t)\|
```

### Range Rate

```math
\dot{d}(t)=
\frac{(\mathbf{r}_B-\mathbf{r}_A)\cdot(\mathbf{v}_B-\mathbf{v}_A)}
{\|\mathbf{r}_B-\mathbf{r}_A\|}
```

### Doppler Shift

```math
\Delta f(t) \approx f_c\frac{\dot{d}(t)}{c}
```

Simplified magnitude:

```math
f_d \approx \frac{v_r}{c}f_c
```

At 437 MHz and \(v_r \approx 7.5\) km/s:

```math
f_d \approx 437\times10^6 \frac{7500}{3\times10^8} \approx 10.9\ \mathrm{kHz}
```

Context: motivates robust UHF/GMSK control profile and Doppler margin.

### Propagation Delay

```math
t_{\mathrm{prop}} = \frac{d}{c}
```

Context: included in correction snapshot timing.

## 8. Link Budget and RF Equations

### Received Power

```math
P_r(\mathrm{dBm}) =
P_t + G_t + G_r - L_{fs} - L_{misc} - L_{point}
```

Context: baseline dB link budget.

### Free-Space Path Loss

```math
L_{fs}(\mathrm{dB}) =
20\log_{10}(d) +
20\log_{10}(f) +
20\log_{10}\left(\frac{4\pi}{c}\right)
```

Context: \(d\) in meters, \(f\) in Hz.

### Receiver Noise Figure to System Temperature

```math
F = 10^{NF/10}
```

```math
T_{rx} = T_0(F-1)
```

```math
T_{sys}=T_{ant}+T_{rx}
```

With:

```math
T_0 = 290\ \mathrm{K}
```

Context: used in `nf_to_tsys()`.

### Thermal Noise Power

```math
N = kT_{sys}B
```

In dBm:

```math
N_{\mathrm{dBm}} = 10\log_{10}(kT_{sys}B)+30
```

Context: bandwidth-dependent receiver noise.

### SNR

```math
\mathrm{SNR}_{dB} =
P_{tx,dBm}+G_t+G_r
-L_{fs}-L_{point}-L_{misc}-L_{\mathrm{Doppler}}
-N_{dBm}
```

Context: `calc_link_budget()` in the unified simulator.

### \(E_b/N_0\)

Linear:

```math
\frac{E_b}{N_0} = \mathrm{SNR}\frac{B}{R_b}
```

dB:

```math
\left(\frac{E_b}{N_0}\right)_{dB}
= \mathrm{SNR}_{dB}+10\log_{10}\left(\frac{B}{R_b}\right)
```

Context: converts link budget into BER input.

### Bitrate from Spectral Efficiency

```math
R_b = B\eta
```

Context: simulator mapping. Typical \(\eta\): GMSK/BPSK \(1\), QPSK \(2\), 2-FSK \(0.5\) b/s/Hz.

## 9. BER, FEC, and PER Equations

Let:

```math
\gamma = E_b/N_0
```

### Q-Function

```math
Q(x)=\frac{1}{2}\mathrm{erfc}\left(\frac{x}{\sqrt{2}}\right)
```

Context: used for coherent modulation BER and convolutional bounds.

### BPSK / Gray-QPSK AWGN BER

```math
P_b = Q(\sqrt{2\gamma}) =
\frac{1}{2}\mathrm{erfc}(\sqrt{\gamma})
```

Context: coherent BPSK and Gray-coded QPSK.

### GMSK BT=0.3 BER

```math
P_b^{\mathrm{GMSK}} =
\frac{1}{2}\mathrm{erfc}
\left(\sqrt{\alpha_{BT}\gamma}\right)
```

With:

```math
\alpha_{BT=0.3}=0.68
```

Penalty relative to BPSK:

```math
\Delta_{\mathrm{GMSK}} =
10\log_{10}\left(\frac{1}{0.68}\right)
\approx 1.67\ \mathrm{dB}
```

Context: baseline UHF modulation in the unified simulator.

### Coherent 2-FSK BER

```math
P_b = Q(\sqrt{\gamma})
```

### Noncoherent 2-FSK BER

```math
P_b = \frac{1}{2}e^{-\gamma/2}
```

### Older Convolutional Coding Gain Proxy

```math
\left(\frac{E_b}{N_0}\right)_{\mathrm{eff}}
=
\left(\frac{E_b}{N_0}\right)+G_{\mathrm{conv}}
```

```math
G_{\mathrm{conv}} \approx 10\log_{10}(5)\approx 7\ \mathrm{dB}
```

Context: older common-band and signal simulators.

### K=7, R=1/2 Convolutional Union Bound

For BPSK/QPSK/GMSK AWGN:

```math
P_b^{\mathrm{CONV}}
\le
36\,Q\left(\sqrt{10\gamma}\right)
```

With:

```math
d_{\mathrm{free}}=10
```

Context: newer unified simulator and docs.

For FSK hard-decision approximation:

```math
P_b^{\mathrm{CONV}}
\lesssim
36\left(4p(1-p)\right)^{d_{\mathrm{free}}/2}
```

where \(p\) is channel BER.

### Reed-Solomon Byte Error Probability

```math
p_{\mathrm{byte}} = 1-(1-p_b)^8
```

Context: converts residual bit errors into byte errors.

### RS(255,223), \(t=16\) Decode Failure

```math
p_{\mathrm{fail}} =
P(N_{\mathrm{err}}>16)
=
\sum_{j=17}^{255}
\binom{255}{j}
p_{\mathrm{byte}}^j
(1-p_{\mathrm{byte}})^{255-j}
```

Equivalent code form:

```math
p_{\mathrm{fail}} = \mathrm{BinomialSF}(16,\ 255,\ p_{\mathrm{byte}})
```

Post-RS BER proxy:

```math
p_{b,\mathrm{post}} \approx 0.5\,p_{\mathrm{fail}}
```

Context: failed RS blocks are treated as random bits.

### Coding Expansion

```math
\mathrm{expansion}_{\mathrm{NONE}} = 1
```

```math
\mathrm{expansion}_{\mathrm{CONV}} = \frac{1}{R_{\mathrm{conv}}}=2
```

```math
\mathrm{expansion}_{\mathrm{CONV+RS}}
=
\frac{1}{R_{\mathrm{conv}}R_{\mathrm{RS}}}
=
\frac{1}{0.5\cdot 223/255}
\approx 2.287
```

Context: converts protocol frame bits to air bits.

### Packet Error Rate

For a packet/frame with \(n\) protected bits and residual BER \(p\):

```math
\mathrm{PER}=1-(1-p)^n
```

Numerically stable implementation:

```math
\mathrm{PER}=1-\exp\left(n\ln(1-p)\right)
```

For small \(p\):

```math
\mathrm{PER}\approx n p
```

For SISP fixed frames:

```math
n = 64\times 8 = 512\ \mathrm{bits}
```

Context: frame retransmission probability.

### PER to BER Design Rule

```math
\mathrm{BER} \lesssim \frac{\mathrm{PER}_{target}}{512}
```

Examples:

```math
\mathrm{PER}\le 10^{-2} \Rightarrow \mathrm{BER}\lesssim 2\times 10^{-5}
```

```math
\mathrm{PER}\le 10^{-3} \Rightarrow \mathrm{BER}\lesssim 2\times 10^{-6}
```

```math
\mathrm{PER}\le 10^{-4} \Rightarrow \mathrm{BER}\lesssim 2\times 10^{-7}
```

Context: protocol-level reliability target.

### Monte Carlo AWGN Noise Variance

With \(E_b=1\):

```math
\sigma^2 = \frac{N_0}{2} = \frac{1}{2(E_b/N_0)}
```

Context: `validate_bpsk_awgn.py` simulation.

## 10. Protocol Timing and Energy

### Fixed Frame Bits

```math
L = 64\ \mathrm{bytes}\times 8 = 512\ \mathrm{bits}
```

### Air Bits Per Frame

```math
N_{\mathrm{air}} = 512\times \mathrm{expansion}
```

For Conv+RS:

```math
N_{\mathrm{air}} = 512\times 2.287 \approx 1171\ \mathrm{bits}
```

### Frame Time

```math
t_{\mathrm{frame}} = \frac{N_{\mathrm{air}}}{R_b}
```

For 12.5 kbps Conv+RS:

```math
t_{\mathrm{frame}} =
\frac{512\times2.287}{12500}
\approx 93.6\ \mathrm{ms}
```

### Single-Frame Energy

```math
E_{TX}=P_{TX,DC}t_{\mathrm{frame}}
```

```math
E_{RX}=P_{RX,DC}t_{\mathrm{frame}}
```

Context: DC radio power model.

### Correction Snapshot Time

For one requester, \(N\) neighbours, and repeat factor \(R\):

```math
t_{\mathrm{snap}}
\approx
R(1+N)t_{\mathrm{frame}}+2\frac{d}{c}
```

Context: checks the 5-second correction timer.

### Detailed Correction Snapshot Energy

Requester transmits request:

```math
E_{\mathrm{req,TX}} = R\,t_{\mathrm{frame}}P_{TX}
```

Neighbours receive request:

```math
E_{\mathrm{req,RX,neigh}} = R\,N\,t_{\mathrm{frame}}P_{RX}
```

Neighbours transmit responses:

```math
E_{\mathrm{rsp,TX,neigh}} = R\,N\,t_{\mathrm{frame}}P_{TX}
```

Requester receives responses:

```math
E_{\mathrm{rsp,RX,requester}} = R\,N\,t_{\mathrm{frame}}P_{RX}
```

Total:

```math
E_{\mathrm{snap}} =
E_{\mathrm{req,TX}}+
E_{\mathrm{req,RX,neigh}}+
E_{\mathrm{rsp,TX,neigh}}+
E_{\mathrm{rsp,RX,requester}}
```

Equivalent:

```math
E_{\mathrm{snap}} =
R\,t_{\mathrm{frame}}\left(P_{TX}+N P_{RX}+N P_{TX}+N P_{RX}\right)
```

Context: detailed energy tab in the simulators.

### KPI Dashboard Correction Energy Approximation

The sustainability dashboard uses:

```math
E_{\mathrm{event}} =
(1+N)t_{\mathrm{frame}}(P_{TX}+N P_{RX})
```

Context: dashboard-level reference equation. Treat as a simplified planning model, not the detailed four-term physical exchange model.

### Daily Correction Energy

```math
E_{\mathrm{day}} =
N_{\mathrm{corrections/day}}E_{\mathrm{event}}
```

```math
E_{\mathrm{day,Wh}} =
\frac{E_{\mathrm{day,J}}}{3600}
```

### Daily Energy Budget Share

```math
\%\mathrm{budget} =
100\frac{E_{\mathrm{SISP,Wh/day}}}{E_{\mathrm{daily\ generation,Wh}}}
```

Context: sustainability/energy dashboards.

## 11. Bulk Relay and Borrow Transfer Equations

### Effective Bytes After Compression

```math
B_{\mathrm{eff}} =
\frac{B_{\mathrm{raw}}}{\rho}
```

where \(\rho\) is compression ratio.

### Required Frames

```math
N_{\mathrm{frames}} =
\left\lceil
\frac{B_{\mathrm{eff}}}{B_{\mathrm{payload/frame}}}
\right\rceil
```

Context: 1 MiB relay examples use 45 useful payload bytes per 64-byte frame.

### ARQ Expected Transmissions Per Successful Frame

```math
E[T] = \frac{1}{1-\mathrm{PER}}
```

Expected transmitted frames:

```math
N_{\mathrm{tx,expected}} =
N_{\mathrm{frames}}E[T]
```

### One-Shot File Success Without ARQ

```math
P_{\mathrm{file\ success}} =
(1-\mathrm{PER})^{N_{\mathrm{frames}}}
```

### Bulk Transfer Time

```math
t_{\mathrm{bulk}} =
N_{\mathrm{tx,expected}}t_{\mathrm{frame}}
```

### Bulk Energy

Sender:

```math
E_{\mathrm{bulk,TX}} = t_{\mathrm{bulk}}P_{TX}
```

Receiver:

```math
E_{\mathrm{bulk,RX}} = t_{\mathrm{bulk}}P_{RX}
```

Total:

```math
E_{\mathrm{bulk}} =
t_{\mathrm{bulk}}(P_{TX}+P_{RX})
```

### Line-of-Sight Feasibility

```math
t_{\mathrm{bulk}} \le t_{\mathrm{LoS\ window}}
```

Context: determines whether a dump fits in one visibility window.

### Minimum Bitrate for 5-Second Correction Window

```math
R_{b,\min} =
\frac{R(1+N)N_{\mathrm{air}}}{5-2t_{\mathrm{prop}}}
```

Context: `sisp_common_band_sim.py` correction-window tab.

## 12. Protocol Frame Capacity and Fragmentation

### Extension Length

Base extension:

```math
L_{\mathrm{ext}} = 2
```

Transport extension:

```math
L_{\mathrm{ext}} \mathrel{+}=
\begin{cases}
4, & \mathrm{PROTO}=1 \\
2, & \mathrm{PROTO}=0
\end{cases}
```

Optional relay extension:

```math
L_{\mathrm{ext}} \mathrel{+}=2\quad \mathrm{if\ RELAY}
```

Optional time-critical extension:

```math
L_{\mathrm{ext}} \mathrel{+}=2\quad \mathrm{if\ TMAX}
```

Security prefix:

```math
L_{\mathrm{ext}} \mathrel{+}=16\quad \mathrm{if\ not\ OFFGRID}
```

Context: `compute_frame_extension_len()`.

### Payload Capacity

```math
C_{\mathrm{payload}} =
64 - (L_{\mathrm{header}}+3+1+L_{\mathrm{ext}})
```

with:

```math
L_{\mathrm{header}}=5
```

Context: fixed-frame payload capacity.

### Fragment Offset

```math
\mathrm{offset} =
\mathrm{fragment\_index}\times \mathrm{MAX\_FRAGMENT\_DATA}
```

Context: relay/borrow reassembly.

### Fragment Count

```math
N_{\mathrm{frag}} =
\left\lceil
\frac{L_{\mathrm{payload}}}{\mathrm{MAX\_FRAGMENT\_DATA}}
\right\rceil
```

Context: C++ state machine uses this for borrow/relay chunking.

## 13. Sustainability and Business Impact

These equations are used in `sisp_value_dashboard.py`. They are modelled scenario equations, not flight measurements.

### Life Extension Factor

```math
F_{\mathrm{life}} = 1+\frac{p_{\mathrm{life\ extension}}}{100}
```

### Effective Satellite Life

```math
L_{\mathrm{SISP}} =
L_{\mathrm{baseline}}F_{\mathrm{life}}
```

### Annual Replacement Missions

Baseline:

```math
M_{\mathrm{baseline}} =
\frac{N_{\mathrm{sats}}}{L_{\mathrm{baseline}}}
```

With SISP:

```math
M_{\mathrm{SISP}} =
\frac{N_{\mathrm{sats}}}{L_{\mathrm{SISP}}}
```

Avoided:

```math
M_{\mathrm{avoided}} =
M_{\mathrm{baseline}}-M_{\mathrm{SISP}}
```

### Annual Sensor Failures and Recoveries

```math
F_{\mathrm{failures/yr}} =
N_{\mathrm{sats}}f_{\mathrm{annual\ failure}}
```

```math
R_{\mathrm{recoveries/yr}} =
F_{\mathrm{failures/yr}}f_{\mathrm{borrow\ recovery}}
```

### Annual Cost Saved

```math
C_{\mathrm{saved/yr}} =
M_{\mathrm{avoided}}C_{\mathrm{satellite}}
```

### Launch CO2 Avoided

```math
\mathrm{CO2}_{\mathrm{saved/yr}} =
M_{\mathrm{avoided}}\mathrm{CO2}_{\mathrm{per\ launch}}
```

### Mass Saved Per Satellite

```math
m_{\mathrm{saved/sat}} =
m_{\mathrm{sat}}\frac{p_{\mathrm{mass\ reduction}}}{100}
```

### Launch Cost Saved Per Satellite From Mass Reduction

```math
C_{\mathrm{launch,saved/sat}} =
m_{\mathrm{saved/sat}}C_{\mathrm{launch/kg}}
```

### ISL to Ground-Station Availability Ratio

```math
R_{\mathrm{ISL/GS}} =
\frac{p_{\mathrm{ISL\ contact}}}{p_{\mathrm{GS\ contact}}}
```

### Contact Minutes Per Orbit

```math
t_{\mathrm{GS}} =
\frac{p_{\mathrm{GS}}}{100}T_{\mathrm{orbit}}
```

```math
t_{\mathrm{ISL}} =
\frac{p_{\mathrm{ISL}}}{100}T_{\mathrm{orbit}}
```

Context: dashboard uses \(T_{\mathrm{orbit}}=90\) minutes.

### Fleet Growth

```math
N(t) = N_0(1+r)^t
```

Global fleet variant:

```math
N_{\mathrm{global}}(t)=N_{\mathrm{global},0}(1+r)^t
```

### Annual Replacement Missions Over Time

```math
M_b(t)=\frac{N(t)}{L_{\mathrm{baseline}}}
```

```math
M_s(t)=\frac{N(t)}{L_{\mathrm{SISP}}}
```

### Cumulative Missions Saved

```math
M_{\mathrm{saved,cum}} =
\sum_{t=0}^{T}(M_b(t)-M_s(t))
```

### Cumulative Replacement Cost

Baseline:

```math
C_b(T)=\sum_{t=0}^{T}M_b(t)C_{\mathrm{satellite}}
```

With SISP:

```math
C_s(T)=\sum_{t=0}^{T}M_s(t)C_{\mathrm{satellite}}
```

Saved:

```math
C_{\mathrm{saved}}(T)=C_b(T)-C_s(T)
```

### Cumulative Launch CO2

```math
\mathrm{CO2}_b(T)=
\sum_{t=0}^{T}M_b(t)\mathrm{CO2}_{\mathrm{per\ launch}}
```

```math
\mathrm{CO2}_s(T)=
\sum_{t=0}^{T}M_s(t)\mathrm{CO2}_{\mathrm{per\ launch}}
```

Saved:

```math
\mathrm{CO2}_{\mathrm{saved}}(T)=
\mathrm{CO2}_b(T)-\mathrm{CO2}_s(T)
```

### Cumulative Mass To Orbit

```math
m_b(T)=\sum_{t=0}^{T}M_b(t)m_{\mathrm{sat}}
```

```math
m_s(T)=\sum_{t=0}^{T}M_s(t)m_{\mathrm{sat}}
```

```math
m_{\mathrm{avoided}}(T)=m_b(T)-m_s(T)
```

### Sensor-Years / Recovered Satellite Count

```math
S_{\mathrm{recovered,cum}} =
\sum_{t=0}^{T}
N(t)f_{\mathrm{annual\ failure}}f_{\mathrm{borrow\ recovery}}
```

Some dashboard text also multiplies recoveries by effective life to express sustained sensor-years:

```math
S_{\mathrm{sensor\ years,cum}} =
\sum_{t=0}^{T}
N(t)f_{\mathrm{annual\ failure}}f_{\mathrm{borrow\ recovery}}L_{\mathrm{SISP}}
```

### Satellite Survival Probability

Baseline:

```math
P_{\mathrm{alive,baseline}}(t)
=
(1-f_{\mathrm{fail}})^t
```

With SISP borrowing:

```math
P_{\mathrm{alive,SISP}}(t)
=
\left(1-f_{\mathrm{fail}}(1-f_{\mathrm{borrow}})\right)^t
```

Context: displayed in the dashboard formulas tab.

## 14. Evaluation Metrics

These are used in the anomaly and correction test reporting.

### RMSE

```math
\mathrm{RMSE} =
\sqrt{
\frac{1}{n}
\sum_{i=1}^{n}
\|\hat{\mathbf{x}}_i-\mathbf{x}_i\|_2^2
}
```

Context: correction quality, e.g. IT-05 and IT-06.

### RMSE Improvement

```math
\mathrm{Improvement} =
100\left(1-\frac{\mathrm{RMSE}_{\mathrm{corrected}}}{\mathrm{RMSE}_{\mathrm{raw}}}\right)
```

Context: headline correction results such as 94.3% and 85.6%.

### Precision

```math
\mathrm{Precision} =
\frac{TP}{TP+FP}
```

### Recall

```math
\mathrm{Recall} =
\frac{TP}{TP+FN}
```

### F1 Score

```math
F_1 =
2\frac{\mathrm{Precision}\cdot\mathrm{Recall}}
{\mathrm{Precision}+\mathrm{Recall}}
```

### Accuracy

```math
\mathrm{Accuracy} =
\frac{TP+TN}{TP+TN+FP+FN}
```

### ROC-AUC

```math
\mathrm{AUC} =
P(s(x^+) > s(x^-))
```

Context: anomaly detector evaluation.

### Average Precision

```math
\mathrm{AP} =
\sum_n (R_n-R_{n-1})P_n
```

Context: `average_precision_score` in the monolithic SVD evaluator.

## 15. Model Discrepancy Notes

The project has evolved, so a few formula families appear in both older and newer forms:

| Area | Older / simplified form | Newer / implementation-preferred form |
|---|---|---|
| Convolutional coding | Constant \(+7\) dB coding gain | K=7, R=1/2 union bound \(36Q(\sqrt{10E_b/N_0})\) in `sisp_unified_sim.py` |
| SVD preprocessing NaN threshold | 50% in `sisp_svd_anomaly.py` | 30% in modular pipeline config |
| Zero-variance handling | Drop zero-variance feature | Modular pipeline converts constant feature into binary deviation indicator |
| Kalman measurement noise | \(R_{\mathrm{eff}}=R(1+\bar{D}/4)\) in docs | \(r_{\mathrm{eff}}=r/\max(\sum w,0.05)\) in C++ |
| Correction energy | Several scenario formulas | Detailed four-term TX/RX exchange is most physically explicit |

For technical presentations, use the implementation-backed forms when discussing current code behavior and clearly label dashboard sustainability numbers as scenario-model estimates.

