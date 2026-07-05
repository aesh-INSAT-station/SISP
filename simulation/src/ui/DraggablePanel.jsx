import React, { useEffect, useRef, useState } from 'react';
import {
  ACCENT,
  FONT_MONO,
  PANEL_BG,
  PANEL_BORDER,
  PANEL_RADIUS,
  PANEL_SHADOW,
  TEXT_SECONDARY,
} from '../constants/index.js';

let activeZ = 40;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function readRect(storageKey, fallback) {
  if (typeof window === 'undefined') return fallback;
  try {
    const saved = window.localStorage.getItem(`nuwa-panel:${storageKey}`);
    return saved ? { ...fallback, ...JSON.parse(saved) } : fallback;
  } catch {
    return fallback;
  }
}

function readCollapsed(storageKey) {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(`nuwa-panel-collapsed:${storageKey}`) === 'true';
  } catch {
    return false;
  }
}

export function DraggablePanel({
  id,
  title,
  children,
  defaultRect,
  minWidth = 220,
  minHeight = 120,
  maxHeight,
  actions = null,
  bodyStyle = {},
}) {
  const [rect, setRect] = useState(() => readRect(id, defaultRect));
  const [collapsed, setCollapsed] = useState(() => readCollapsed(id));
  const [zIndex, setZIndex] = useState(() => activeZ++);
  const dragRef = useRef(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(`nuwa-panel:${id}`, JSON.stringify(rect));
    } catch {
      // Panel placement persistence is a convenience only.
    }
  }, [id, rect]);

  useEffect(() => {
    try {
      window.localStorage.setItem(`nuwa-panel-collapsed:${id}`, String(collapsed));
    } catch {
      // Panel collapse state is a convenience only.
    }
  }, [id, collapsed]);

  useEffect(() => {
    const onMove = (event) => {
      if (!dragRef.current) return;
      const next = dragRef.current.compute(event);
      setRect(next);
    };
    const onUp = () => {
      if (dragRef.current?.type === 'move' && !dragRef.current.didMove) {
        setCollapsed((open) => !open);
      }
      dragRef.current = null;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, []);

  const focus = () => setZIndex(activeZ++);

  const beginMove = (event) => {
    if (event.button !== 0) return;
    if (event.target.closest('button')) return;
    focus();
    const start = { x: event.clientX, y: event.clientY, rect };
    dragRef.current = {
      type: 'move',
      didMove: false,
      compute: (move) => {
        if (Math.hypot(move.clientX - start.x, move.clientY - start.y) > 4) {
          dragRef.current.didMove = true;
        }
        const width = start.rect.width;
        const height = collapsed ? 34 : start.rect.height;
        return {
          ...start.rect,
          left: clamp(start.rect.left + move.clientX - start.x, 8, window.innerWidth - width - 8),
          top: clamp(start.rect.top + move.clientY - start.y, 8, window.innerHeight - height - 8),
        };
      },
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
  };

  const beginResize = (event) => {
    event.stopPropagation();
    focus();
    const start = { x: event.clientX, y: event.clientY, rect };
    dragRef.current = {
      type: 'resize',
      didMove: true,
      compute: (move) => {
        const maxWidth = window.innerWidth - start.rect.left - 8;
        const maxPanelHeight = window.innerHeight - start.rect.top - 8;
        return {
          ...start.rect,
          width: clamp(start.rect.width + move.clientX - start.x, minWidth, maxWidth),
          height: clamp(
            start.rect.height + move.clientY - start.y,
            minHeight,
            Math.min(maxHeight || maxPanelHeight, maxPanelHeight)
          ),
        };
      },
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'nwse-resize';
  };

  const reset = () => {
    focus();
    setRect(defaultRect);
  };

  return (
    <section
      onPointerDown={focus}
      style={{
        position: 'fixed',
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: collapsed ? 34 : rect.height,
        minWidth,
        minHeight: collapsed ? 34 : minHeight,
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: PANEL_RADIUS,
        boxShadow: PANEL_SHADOW,
        zIndex,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        color: '#d4eeff',
        fontFamily: FONT_MONO,
        backdropFilter: 'blur(18px) saturate(130%)',
      }}
    >
      <style>{`
        .nuwa-scroll {
          scrollbar-width: thin;
          scrollbar-color: rgba(112,211,255,0.46) rgba(3,10,24,0.18);
        }
        .nuwa-scroll::-webkit-scrollbar {
          width: 9px;
          height: 9px;
        }
        .nuwa-scroll::-webkit-scrollbar-track {
          background: linear-gradient(180deg, rgba(3,10,24,0.12), rgba(0,185,255,0.05));
          border-radius: 999px;
        }
        .nuwa-scroll::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, rgba(112,211,255,0.70), rgba(0,185,255,0.24));
          border: 2px solid rgba(3,10,24,0.72);
          border-radius: 999px;
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10), 0 0 8px rgba(0,185,255,0.22);
        }
        .nuwa-scroll::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, rgba(178,235,255,0.88), rgba(0,185,255,0.38));
        }
        .nuwa-scroll::-webkit-scrollbar-corner {
          background: transparent;
        }
      `}</style>
      <header
        onPointerDown={beginMove}
        style={{
          height: 34,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 10px 0 12px',
          borderBottom: collapsed ? 'none' : PANEL_BORDER,
          cursor: 'grab',
          background: 'linear-gradient(90deg, rgba(0,185,255,0.10), rgba(255,255,255,0.02))',
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: ACCENT,
            boxShadow: `0 0 10px ${ACCENT}`,
            flexShrink: 0,
          }}
        />
        <strong
          style={{
            minWidth: 0,
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: '#d4eeff',
          }}
        >
          {title}
        </strong>
        {actions}
        <button
          type="button"
          onClick={() => setCollapsed((open) => !open)}
          title={collapsed ? 'Expand panel' : 'Collapse panel'}
          style={{
            border: '1px solid rgba(255,255,255,0.10)',
            background: 'rgba(0,0,0,0.18)',
            color: TEXT_SECONDARY,
            width: 22,
            height: 22,
            borderRadius: 4,
            cursor: 'pointer',
            fontFamily: FONT_MONO,
            fontSize: 11,
            lineHeight: 1,
          }}
        >
          {collapsed ? '▾' : '▴'}
        </button>
        <button
          type="button"
          onClick={reset}
          title="Reset panel position"
          style={{
            border: '1px solid rgba(255,255,255,0.10)',
            background: 'rgba(0,0,0,0.18)',
            color: TEXT_SECONDARY,
            width: 22,
            height: 22,
            borderRadius: 4,
            cursor: 'pointer',
            fontFamily: FONT_MONO,
            fontSize: 12,
            lineHeight: 1,
          }}
        >
          ↺
        </button>
      </header>
      {!collapsed && (
        <>
          <div
            className="nuwa-scroll"
            style={{
              minHeight: 0,
              flex: 1,
              overflow: 'auto',
              ...bodyStyle,
            }}
          >
            {children}
          </div>
          <div
            onPointerDown={beginResize}
            title="Resize panel"
            style={{
              position: 'absolute',
              right: 0,
              bottom: 0,
              width: 18,
              height: 18,
              cursor: 'nwse-resize',
              background:
                'linear-gradient(135deg, transparent 0 45%, rgba(112,211,255,0.28) 46% 52%, transparent 53% 62%, rgba(112,211,255,0.22) 63% 69%, transparent 70%)',
            }}
          />
        </>
      )}
    </section>
  );
}
