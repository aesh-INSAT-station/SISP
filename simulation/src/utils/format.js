export const hex = (n) => '0x' + n.toString(16).toUpperCase().padStart(2, '0');

export const fmtUptime = (s) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

export const relTime = (now, ts) => {
  const d = (now - ts) / 1000;
  if (d < 1) return 'now';
  if (d < 60) return `${Math.floor(d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  return `${Math.floor(d / 3600)}h ago`;
};

export const degrColor = (d) => {
  if (d <= 5) return '#4ade80';
  if (d <= 10) return '#f5c518';
  return '#ef4444';
};
