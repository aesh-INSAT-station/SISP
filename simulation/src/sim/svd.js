/** Minimal SVD for small matrices (≤100×100) via Jacobi eigenvalues.
 *  We only need singular values, not U or V.
 *
 *  Strategy: compute HᵀH (n×n), find its eigenvalues via classic
 *  Jacobi iteration, then σ_i = √λ_i.
 *
 *  This is fast and simple for the Hankel matrices we build
 *  (typically 50×51 → HᵀH is 51×51).
 */

function matMulT(A) {
  const m = A.length, n = A[0].length;
  const out = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = i; j < n; j++) {
      let s = 0;
      for (let k = 0; k < m; k++) s += A[k][i] * A[k][j];
      out[i][j] = out[j][i] = s;
    }
  }
  return out;
}

function eigenValues(A, maxIter = 100, tol = 1e-12) {
  const n = A.length;
  const B = A.map(row => [...row]);
  let iter = 0;

  while (iter++ < maxIter) {
    let maxOff = 0, p = 0, q = 1;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const v = Math.abs(B[i][j]);
        if (v > maxOff) { maxOff = v; p = i; q = j; }
      }
    }
    if (maxOff < tol) break;

    const beta = (B[q][q] - B[p][p]) / (2 * B[p][q] + 1e-30);
    const t = Math.sign(beta) / (Math.abs(beta) + Math.sqrt(1 + beta * beta));
    const c = 1 / Math.sqrt(1 + t * t);
    const s = t * c;

    for (let i = 0; i < n; i++) {
      const bip = B[i][p], biq = B[i][q];
      B[i][p] = c * bip - s * biq;
      B[i][q] = s * bip + c * biq;
    }
    for (let i = 0; i < n; i++) {
      const bpi = B[p][i], bqi = B[q][i];
      B[p][i] = c * bpi - s * bqi;
      B[q][i] = s * bpi + c * bqi;
    }
  }

  const vals = [];
  for (let i = 0; i < n; i++) vals.push(Math.max(0, B[i][i]));
  vals.sort((a, b) => b - a);
  return vals;
}

export function singularValues(H) {
  if (!H || H.length === 0 || H[0].length === 0) return [];
  const m = H.length, n = H[0].length;
  // Always work with the smaller product to minimise cost
  if (m >= n) {
    const HtH = matMulT(H);
    return eigenValues(HtH).map(v => Math.sqrt(v));
  }
  // m < n → compute H·Hᵀ (m×m) instead
  const HHt = Array.from({ length: m }, () => new Array(m).fill(0));
  for (let i = 0; i < m; i++) {
    for (let j = i; j < m; j++) {
      let s = 0;
      for (let k = 0; k < n; k++) s += H[i][k] * H[j][k];
      HHt[i][j] = HHt[j][i] = s;
    }
  }
  const ev = eigenValues(HHt);
  // Need to pad with zeros since we only got min(m,n) values
  const full = ev.map(v => Math.sqrt(v));
  while (full.length < n) full.push(0);
  return full;
}
