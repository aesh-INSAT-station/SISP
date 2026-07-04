/** Hankel-SVD anomaly detector — the on-board method from the SISP paper.
 *
 *  Maintains a sliding window of raw sensor samples.
 *  When the window is full, embeds into a Hankel matrix,
 *  computes SVD, and extracts the off-diagonal ratio:
 *
 *      ρ = Σ_{i=2}^{min(m,n)} σ_i  /  Σ_{i=1} σ_i
 *
 *  A sudden increase in ρ indicates a structural break
 *  in the time series (sensor fault, drift, noise burst).
 *
 *  Paper reference: SISP Section 3.2 — Time-Lagged SVD Detector
 */

import { singularValues } from './svd.js';

const DEFAULT_WINDOW_LEN = 100;
const DEFAULT_HANKEL_ROWS = 50;
const DEFAULT_THRESHOLD = 0.15;

export class HankelSVDDetector {
  constructor(opts = {}) {
    this.windowLen = opts.windowLen || DEFAULT_WINDOW_LEN;
    this.hankelRows = opts.hankelRows || DEFAULT_HANKEL_ROWS;
    this.threshold = opts.threshold != null ? opts.threshold : DEFAULT_THRESHOLD;

    this._buffer = [];
    this._rho = 0;
    this._rhoHistory = [];
    this._anomalyCount = 0;
    this._sampleCount = 0;
  }

  /** Push one raw sample. Returns current ρ (0 if window not yet full). */
  push(value) {
    this._sampleCount++;
    this._buffer.push(value);
    if (this._buffer.length > this.windowLen) {
      this._buffer.shift();
    }
    if (this._buffer.length < this.windowLen) {
      return 0;
    }
    this._rho = this._computeRho();
    this._rhoHistory.push(this._rho);
    return this._rho;
  }

  get rho() { return this._rho; }
  get rhoHistory() { return this._rhoHistory; }
  get isAnomalous() { return this._rho > this.threshold; }
  get sampleCount() { return this._sampleCount; }
  get bufferSize() { return this._buffer.length; }
  get windowFull() { return this._buffer.length >= this.windowLen; }

  /** Reset the detector (call when switching channels or after a fault clears). */
  reset() {
    this._buffer = [];
    this._rho = 0;
    this._anomalyCount = 0;
  }

  _computeRho() {
    const window = this._buffer;

    // Mean-centre the window
    const mean = window.reduce((a, b) => a + b, 0) / window.length;
    const centred = window.map(v => v - mean);

    // Build Hankel matrix: m rows × n columns, where m = hankelRows, n = windowLen - hankelRows + 1
    const m = this.hankelRows;
    const n = centred.length - m + 1;
    if (n < 2) return 0;

    const H = [];
    for (let i = 0; i < m; i++) {
      const row = [];
      for (let j = 0; j < n; j++) {
        row.push(centred[i + j]);
      }
      H.push(row);
    }

    // Singular values via our minimal SVD
    const sv = singularValues(H);
    if (sv.length < 2) return 0;

    const total = sv.reduce((a, b) => a + b, 0);
    if (total < 1e-30) return 0;

    const offDiagonal = sv.slice(1).reduce((a, b) => a + b, 0);
    return offDiagonal / total;
  }
}
