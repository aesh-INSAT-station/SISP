// Standalone simulation clock — no Cesium.
// The caller (ThreeGlobe) drives it each RAF frame via advance(wallMs).
// Everything in sim/ and threejs/ that needs time runs off this clock
// so the simulation correctly speeds up / slows down / pauses with
// the playback bar.
export class SimClock {
  constructor() {
    this._simTime = 0;       // seconds since sim epoch
    this._multiplier = 60;
    this._playing = true;
    this._events = [];
    this._listeners = new Set();
    this._lastWallMs = null;
  }

  get currentTime() { return this._simTime; }
  get isPlaying()   { return this._playing; }
  get multiplier()  { return this._multiplier; }

  setPlaying(p)    { this._playing = !!p; }
  setMultiplier(m) { this._multiplier = m; }

  // Jump by ±delta sim-seconds.
  step(deltaSeconds) {
    this._simTime += deltaSeconds;
    this._fireEvents();
    this._notifyListeners();
  }

  // One-shot. Returns a cancel fn.
  scheduleAfter(seconds, fn) {
    const target = this._simTime + seconds;
    const event = { time: target, fn, cancelled: false };
    this._insert(event);
    return () => { event.cancelled = true; };
  }

  // Repeating sim-time interval. Returns a cancel fn.
  setInterval(seconds, fn) {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      fn();
      if (!cancelled) this.scheduleAfter(seconds, tick);
    };
    this.scheduleAfter(seconds, tick);
    return () => { cancelled = true; };
  }

  // Subscribe to every advance() call. Returns unsub fn.
  onTick(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  // Called by ThreeGlobe each requestAnimationFrame.
  advance(wallMs) {
    const dt = this._lastWallMs == null ? 0 : (wallMs - this._lastWallMs) / 1000;
    this._lastWallMs = wallMs;
    if (this._playing && dt > 0 && dt < 0.5) {
      this._simTime += dt * this._multiplier;
    }
    this._fireEvents();
    this._notifyListeners();
  }

  _fireEvents() {
    const now = this._simTime;
    while (this._events.length > 0 && this._events[0].time <= now) {
      const ev = this._events.shift();
      if (!ev.cancelled) {
        try { ev.fn(); } catch (e) { console.error('SimClock event error', e); }
      }
    }
  }

  _notifyListeners() {
    this._listeners.forEach(fn => fn(this._simTime, this._multiplier, this._playing));
  }

  _insert(event) {
    let lo = 0, hi = this._events.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this._events[mid].time < event.time) lo = mid + 1;
      else hi = mid;
    }
    this._events.splice(lo, 0, event);
  }

  destroy() {
    this._listeners.clear();
    this._events = [];
  }
}
