import React from 'react';
import { SERVICE_COLOR } from '../constants/index.js';
import { hex, relTime } from '../utils/format.js';

export function PacketLogRow({ entry, now, expanded, onClick }) {
  const dirArrow = entry.dir === 'TX' ? '↑' : '↓';
  const dirColor = entry.dir === 'TX' ? '#4ade80' : '#a855f7';
  const svcColor = SERVICE_COLOR[entry.service] || '#94a3b8';

  return (
    <div
      onClick={onClick}
      style={{
        padding: '4px 8px',
        margin: '2px 0',
        background: expanded ? 'rgba(255,255,255,0.04)' : 'transparent',
        borderLeft: `2px solid ${expanded ? svcColor : 'transparent'}`,
        cursor: 'pointer',
        fontSize: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: '#475569', width: 50, fontSize: 9 }}>{relTime(now, entry.ts)}</span>
        <span style={{ color: dirColor, width: 14 }}>
          {dirArrow}
          {entry.dir}
        </span>
        <span
          style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: svcColor,
          }}
        />
        <span
          style={{
            color: '#cbd5e1',
            flex: 1,
            fontSize: 9,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {entry.service}
        </span>
        <span style={{ color: '#64748b', fontSize: 9 }}>{hex(entry.peer)}</span>
        <span style={{ color: '#475569', fontSize: 9 }}>#{entry.seq}</span>
        {entry.flags.length > 0 && (
          <span style={{ color: '#f5c518', fontSize: 9 }}>[{entry.flags.join('')}]</span>
        )}
      </div>
      {expanded && (
        <div
          style={{
            marginTop: 6,
            padding: '6px 8px',
            background: 'rgba(0,0,0,0.4)',
            border: '1px solid rgba(255,255,255,0.05)',
            display: 'grid',
            gridTemplateColumns: '60px 1fr',
            gap: '2px 8px',
            fontSize: 9,
            color: '#94a3b8',
          }}
        >
          <span style={{ color: '#475569' }}>SRC</span>
          <span style={{ color: '#cbd5e1' }}>{hex(entry.src)}</span>
          <span style={{ color: '#475569' }}>DST</span>
          <span style={{ color: '#cbd5e1' }}>{hex(entry.dst)}</span>
          <span style={{ color: '#475569' }}>SVC</span>
          <span style={{ color: svcColor }}>{entry.service}</span>
          <span style={{ color: '#475569' }}>SEQ</span>
          <span style={{ color: '#cbd5e1' }}>{entry.seq}</span>
          <span style={{ color: '#475569' }}>LEN</span>
          <span style={{ color: '#cbd5e1' }}>{entry.length}b</span>
          <span style={{ color: '#475569' }}>CRC</span>
          <span style={{ color: '#cbd5e1' }}>{entry.checksum}</span>
          <span style={{ color: '#475569' }}>FLAGS</span>
          <span style={{ color: '#f5c518' }}>
            {entry.flags.length ? entry.flags.join(' ') : '—'}
          </span>
          <div
            style={{
              gridColumn: '1 / 3',
              height: 1,
              background: 'rgba(255,255,255,0.05)',
              margin: '2px 0',
            }}
          />
          <span
            style={{
              color: '#475569',
              gridColumn: '1 / 3',
              fontSize: 8,
              letterSpacing: '0.1em',
            }}
          >
            PAYLOAD
          </span>
          {Object.entries(entry.payload).map(([k, v]) => (
            <React.Fragment key={k}>
              <span style={{ color: '#475569' }}>{k}</span>
              <span style={{ color: '#cbd5e1' }}>{String(v)}</span>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
