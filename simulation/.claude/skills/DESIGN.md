# NUWA Design System

> IEEE AESS Sustainability Hackathon · Theme 4: Sustainable Space Systems & Orbital Lifecycle  
> Team **Les Talelas** · Project **NUWA**

---

## Brand Identity

**NUWA** is a satellite mesh protocol simulator with a deep-space aesthetic.  
The visual language is inspired by mission control interfaces: dark, precise, data-dense but calm.

The NUWA logo is a dual-spiral swirl rendered in the primary accent (`#00b9ff`) on a dark background.
Both SVG paths from `Logo .svg` are used — place them at 28–40 px for headers, 20 px for compact contexts.

---

## Colour Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `NUWA_BG` | `#00040c` | Full-page background (near-black space) |
| `PANEL_BG` | `rgba(4,12,28,0.90)` | Frosted panel backgrounds |
| `PANEL_BORDER` | `rgba(0,185,255,0.10)` | All panel/section borders |
| `ACCENT` | `#00b9ff` | Electric cyan — primary interactive colour |
| `ACCENT_DIM` | `rgba(0,185,255,0.18)` | Hover/active state fills |
| `TEXT_PRIMARY` | `#d4eeff` | Readable body text |
| `TEXT_SECONDARY` | `#4a7a9b` | Muted labels and metadata |
| `TEXT_DIM` | `#1c3550` | Disabled or decorative text |
| `STATUS_GREEN` | `#00ff88` | Success, LOS contact, healthy |
| `STATUS_AMBER` | `#f5c518` | Warning, active scenario |
| `STATUS_RED` | `#ff3d5a` | Failure, critical state |

### State colours (satellite protocol states)

| State | CSS |
|-------|-----|
| `IDLE` | `#00b9ff` |
| `CORR_*` | `#f5c518` |
| `RELAY_*` | `#22d3ee` |
| `BORROW_*` | `#a78bfa` |
| `CRITICAL_FAIL` | `#ff3d5a` |

---

## Typography

Single typeface throughout:

```
FONT_MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
```

| Role | Size | Weight | Letter-spacing |
|------|------|--------|----------------|
| Panel title (NUWA header) | 15 px | 700 | 0.22 em |
| Section header | 8 px | 400 | 0.18 em, UPPERCASE |
| Metric value | 12 px | 600 | 0.05 em |
| Metric label | 8 px | 400 | 0.12 em, UPPERCASE |
| Log rows | 9–10 px | 400 | 0.05 em |
| Subtitle / dim | 10 px | 400 | 0.15 em |

---

## Layout Grid

```
┌────────────────────────────────────────────────────────┐
│  NuwaHeader (h=48, zIndex=30)                          │
├──────────┬─────────────────────────────┬───────────────┤
│ Insights │                             │   Satellite   │
│  Panel   │      Three.js Globe         │    Panel      │
│ (264 px) │                             │   (300 px)    │
│          │                             │               │
│ top: 48  │   position: fixed, inset:0  │   top: 48     │
│ bottom:48│                             │   bottom: 48  │
├──────────┴──────────────────────────────┴──────────────┤
│  ScenarioBar (h=48, bottom=0, zIndex=22)               │
└────────────────────────────────────────────────────────┘

PlaybackBar: floating pill, bottom=56, centered, zIndex=22
EventLogDrawer: slides up from bottom, height=240, zIndex=5 (behind bars)
```

**z-index stack:**
- `5` — EventLogDrawer body
- `18` — InsightsPanel
- `20` — SatellitePanel
- `22` — ScenarioBar, PlaybackBar
- `30` — NuwaHeader

---

## Panel Rules

1. **All panels**: `backdropFilter: blur(8px)`, `PANEL_BG`, `PANEL_BORDER`
2. **Side panels** bound to `top: 48` (below header) and `bottom: 48` (above scenario bar)
3. **Section headers**: 8 px, `ACCENT` at `opacity: 0.7`, `letterSpacing: 0.18em`, UPPERCASE
4. **No inline emojis** in data labels — use coloured dots or text codes instead
5. **Border accents**: use `1px solid PANEL_BORDER` between sections, never heavy separators

---

## Three.js Globe Visual Language

| Element | Style |
|---------|-------|
| Earth sphere | `#041830` with specular `#004488` |
| Lat/lon grid | `#072848` at 50% opacity, 0.5 px lines |
| Atmosphere | `#0055bb` at 7% opacity, BackSide sphere |
| Stars | `#88bbff`, 2800 points, size 0.055 |
| Orbit path (idle) | `#0d2a4a` at 28% opacity |
| Orbit path (selected) | `#00b9ff` at 80% opacity |
| Satellite dot | Sphere r=0.013, coloured by STATE_COLOR_HEX |
| Satellite glow | Sphere r=0.028, same colour, 15% → 50% when selected |
| Ground station | `#00ff88` sphere r=0.009 |
| Packet dot | Sphere r=0.018, SERVICE_COLOR, bezier arc trajectory |

---

## Component Inventory

- `NuwaHeader` — brand bar with NUWA logo + tagline
- `InsightsPanel` — left panel: constellation health, DEGR trends, energy, link matrix
- `SatellitePanel` — right panel: single-sat detail, DEGR bar, geodetic, packet log, minimap
- `PlaybackBar` — floating transport + speed controls + ground station indicators
- `ScenarioBar` — bottom bar: scenario trigger buttons + hint text
- `EventLogDrawer` — slide-up protocol log with family filter tabs
- `ThreeGlobe` — Three.js canvas with GlobeScene renderer

---

## Do / Don't

| Do | Don't |
|----|-------|
| Use `ACCENT` for interactive highlights | Use white for interactive elements |
| Use `TEXT_DIM` for disabled/placeholder text | Use grey (`#888`) — keep it in the blue family |
| Keep section headers short: `DEGR TREND`, `LINK MATRIX` | Write full sentences in section headers |
| Use `degrColor()` for DEGR values | Hard-code green/yellow/red |
| Group related metrics in a 2-column grid | Stack every metric vertically |
| Keep panels within `top:48 → bottom:48` | Overlap the NuwaHeader or ScenarioBar |
