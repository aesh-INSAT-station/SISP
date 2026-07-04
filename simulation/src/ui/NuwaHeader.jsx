import React from 'react';
import { FONT_MONO, PANEL_BG, PANEL_BORDER, ACCENT, PANEL_SHADOW, PANEL_RADIUS } from '../constants/index.js';

// NUWA logo — the spiral/swirl SVG path, white on transparent
const LogoSvg = () => (
  <svg
    viewBox="0 0 702 698"
    width={32}
    height={32}
    style={{ display: 'block', flexShrink: 0 }}
  >
    <path
      fill={ACCENT}
      d="M21.9,655,313.09,363,488.29,184.7a64.1,64.1,0,0,0,18.25-26.09c6.75-18.41,1.79-36.86-1.83-51a144.66,144.66,0,0,0-13.22-33.43c44.56,26.91,88.58,25.7,133.88.56a125,125,0,0,0-19.09,59.37c-2.11,37.09,13.21,64.24,19.33,73.94a128.42,128.42,0,0,0-39.71-15.19c-12.37-2.47-30.92-5.84-49.43,2.77-3.51,1.63-6.61,3.51-18.54,13.55-24.09,20.29-42.37,38.66-52.48,48.88C449,274.67,441,283.17,436,287.91L338.26,381.3C274.32,437.24,231,482.7,223.35,499.35a90.59,90.59,0,0,0-5.28,15.39c-6.88,27.44,1.81,50.07,22.8,68.12,35.17,30.25,77.34,42.27,122.48,41.85,99.72-.91,183.23-38.21,244.85-117.92,35.46-45.88,48.22-89.66,54.17-110.51,36.44-127.7-16.24-250.94-31.79-284.6,19.51,27.43,74.58,112.33,71.47,232.64-.78,29.85-6.91,134.75-82.33,227.05C559,645.75,479.4,686.38,383.8,696c-81,8.15-155-11.44-223.21-54.72-12.1-7.69-23.17-17-34.54-25.85a35.37,35.37,0,0,0-19.37-7.64c-11.3-1.07-20.3,3.81-26.56,7.39C55.78,629.09,33.22,646.14,21.9,655Z"
    />
    <path
      fill={ACCENT}
      d="M580.8,72.36c-23.39-12.24-162.66-82.5-302.25-26.78-24.81,9.9-92,36.7-136.37,105.46a237.15,237.15,0,0,0-32.42,77c-3.81,17.35-19.21,87.39,20.11,151.5a175.29,175.29,0,0,0,32.71,39c-32.82,29.62-66.44,70.55-85.53,125.11-1.82,5.2-3.44,10.35-4.9,15.45C50.36,531.06,12.92,474.06,2.57,393.74a322.9,322.9,0,0,1,1-88.64c10.65-72.36,36.38-132.79,76.54-181,64.44-77.32,144.69-102.38,170.4-110C415.75-34.64,558.13,57.22,580.8,72.36Z"
    />
  </svg>
);

export function NuwaHeader() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 14,
        left: 18,
        right: 'auto',
        width: 'min(720px, calc(100vw - 36px))',
        height: 46,
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: PANEL_RADIUS,
        boxShadow: PANEL_SHADOW,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: 12,
        zIndex: 30,
        backdropFilter: 'blur(18px) saturate(130%)',
        fontFamily: FONT_MONO,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <LogoSvg />
      <span
        style={{
          fontSize: 15,
          fontWeight: 700,
          color: ACCENT,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          flexShrink: 0,
        }}
      >
        NUWA
      </span>
      <div
        style={{
          width: 1,
          height: 20,
          background: 'rgba(0,185,255,0.18)',
          margin: '0 4px',
        }}
      />
      <span
        style={{
          fontSize: 10,
          color: '#2a5a7a',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        Sustainable Space Systems · Orbital Lifecycle Simulator
      </span>
    </div>
  );
}
