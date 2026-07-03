```
   ████████ ██ ███████ ██████      ███████ ██ ███    ███
   ██       ██ ██      ██   ██     ██      ██ ████  ████
   ███████  ██ ███████ ██████  ──  ███████ ██ ██ ████ ██
        ██  ██      ██ ██               ██ ██ ██  ██  ██
   ███████  ██ ███████ ██          ███████ ██ ██      ██

   S A T E L L I T E   I N T E R - S E R V I C E   P R O T O C O L
```

Satellite Inter-Service Protocol simulator with a live 3D constellation, a JavaScript telemetry simulation, and a WebSocket bridge to the C++ SISP state machine.

The app shows an 8-satellite network around Earth, animates protocol frames between nodes, tracks health and sensor telemetry, and lets you trigger protocol scenarios from the UI. When the bridge server is running, the live C++ protocol panel and scenario controls use the C++ DLL through `server/index.js`.

## What It Shows

- A full-screen Three.js Earth with day/night lighting, clouds, night lights, stars, orbit paths, ground stations, and clickable satellite models.
- Eight configured satellites with roles such as imaging, comms, science, navigation reference, relay hub, high-latitude, and observation.
- Real-time orbital propagation from Keplerian elements in `src/sim/keplerian.js`.
- A simulation clock with pause, stepping, and speed multipliers. The renderer drives it through `requestAnimationFrame`, and simulation timers use sim time rather than wall-clock time.
- Protocol traffic as animated packet arcs between satellites and ground.
- Satellite state, DEGR integrity score, energy, uptime, orbit error, sensor readings, ground track, and per-satellite packet logs.
- Fleet dashboards for health, packet rates, link matrix, energy, and recent events.
- A live C++ SISP engine panel that shows bridge connection state, C++ satellite FSM state, C++ frame traces, and protocol trigger buttons.
- Sensor graph panels for live sensor histories and fault visibility.

## How It Works

There are two cooperating simulation paths.

1. The browser owns visualization, orbit motion, sensors, energy drift, UI panels, and packet animation.
2. The bridge server owns C++ protocol state. It loads `sisp.dll`, creates one C++ context per satellite, advances the C++ FSM on sim-time ticks, routes emitted frames, and broadcasts centralized satellite snapshots to all WebSocket clients.

The frontend bridge in `src/sim/CppProtocol.js` connects to the server at `VITE_SISP_WS_URL` or `ws://localhost:3001` by default. It does three things:

- Sends sim-time `TICK` messages so C++ timers advance with the same playback clock as the UI.
- Publishes browser telemetry such as energy, uptime, orbit data, sunlight, and sensor status back to the server with `SATELLITE_TELEMETRY`.
- Consumes server `CONTEXT`, `SATELLITES`, `STATE`, and `PACKET` messages. Server state and DEGR are applied back onto the local engine so the UI reads the server-centralized satellite state.

This means satellite state is centralized through the bridge when the server is live. If the server is offline, the UI still renders the JavaScript simulation, but the C++ panel shows offline and C++ scenarios are unavailable.

## Runtime Flow

```text
ThreeGlobe requestAnimationFrame
  -> SimClock.advance()
  -> SimulationEngine.tick() every 2 sim seconds
  -> sensor, energy, DEGR, sunlight, orbit updates
  -> CppProtocol sends TICK and telemetry to server

server/index.js
  -> loads cpp/sisp/c++ implemnetation/build/bin/Release/sisp.dll
  -> creates C++ contexts for satellites 1..8
  -> injects events, advances timers, routes emitted frames
  -> broadcasts centralized satellite snapshots and PACKET messages

CppProtocol in browser
  -> applies server state/degr to the JS engine
  -> injects C++ frames into ProtocolService packet animation
  -> notifies ProtocolLab and other UI through the shared engine snapshot
```

## Quick Start

Install dependencies for both the Vite app and the bridge server:

```bash
npm install
cd server
npm install
cd ..
```

Copy the example environment file:

```bash
copy .env.example .env
```

Start the UI and bridge together:

```bash
npm run dev
```

Open:

```text
http://localhost:5173
```

The default bridge URL is:

```text
ws://localhost:3001
```

If you change the bridge port, set both the server port and the browser WebSocket URL. On PowerShell:

```powershell
$env:SISP_PORT = "3565"
$env:VITE_SISP_WS_URL = "ws://localhost:3565"
npm run dev
```

The plain `.env` file is read by Vite for `VITE_*` variables. The Node bridge reads `SISP_PORT` from the process environment, so export it in the shell when overriding the default bridge port.

## Available Scripts

```bash
npm run dev      # run Vite and server/index.js together
npm run dev:ui   # run only the Vite frontend
npm run bridge   # run only the Node/C++ bridge
npm run build    # production build into dist/
npm run preview  # preview the production build
```

The bridge expects the C++ DLL at:

```text
cpp/sisp/c++ implemnetation/build/bin/Release/sisp.dll
```

If the bridge exits with a DLL loading error, rebuild the C++ implementation or verify that this path exists.

## UI Guide

Main view:

- Drag to rotate Earth.
- Scroll to zoom.
- Click a satellite to select it and enter track mode.
- Press `Escape` to leave tracking, then clear selection.

Panels:

- Header: packet count, scenario count, constellation health, and global app status.
- Satellites: compact list of satellite state, power, and DEGR.
- Satellite detail: selected satellite metrics, DEGR breakdown, sensor list, packet log, and minimap.
- Insights: fleet-level charts for health, energy, packet rate, and links.
- Event log: global packet and event history.
- Sensor graph: detailed live view for selected sensors.
- Playback bar: pause, resume, step, and change sim speed.
- Scenario bar: inject fault, ground link/relay, low energy, ping, and reset.
- Protocol Lab: live C++ bridge state, C++ frame trace, and C++ scenario triggers.

## Protocol Scenarios

The JavaScript `ProtocolService` provides a fallback simulation path. When the C++ bridge is connected, scenario buttons prefer the C++ bridge.

| Scenario   | Trigger                      | Behavior                                                                                                  |
| ---------- | ---------------------------- | --------------------------------------------------------------------------------------------------------- |
| Correction | Fault                        | Satellite requests correction responses from neighbors, computes, then returns to idle.                   |
| Relay      | Ground link or low energy    | Satellite requests relay help, sends downlink data through a neighbor or relay hub, then receives an ack. |
| Heartbeat  | Ping                         | Sender broadcasts heartbeat frames to peers.                                                              |
| Failure    | Protocol Lab failure trigger | Satellite enters critical failure and broadcasts failure frames.                                          |
| Status     | Protocol Lab status path     | Satellite emits status-style traffic through the C++ FSM.                                                 |
| Reset      | Reset                        | Clears scenario state and returns satellites to idle.                                                     |

## Satellite State And DEGR

Each satellite has:

- `state`: protocol FSM state such as `IDLE`, `CORR_WAIT_RSP`, `RELAY_ACTIVE`, `BORROW_WAIT_RSP`, or `CRITICAL_FAIL`.
- `degr`: a 0 to 15 integrity score.
- `energy`: battery percentage used by relay and low-energy scenarios.
- `uptime_s`: simulated uptime.
- `orbit_error_m`: simulated orbit error.
- `sensors`: active sensor set with status, units, latest reading, and graph history.
- `currentPos`: Earth-fixed position used for rendering and link calculations.

The browser computes sensor and telemetry fields, then publishes them to the bridge. The server merges those fields into its satellite store while keeping C++ FSM state and C++ DEGR authoritative.

## Project Layout

```text
SISP-SIM/
  server/
    index.js                 WebSocket gateway to sisp.dll
    package.json             bridge dependencies: koffi, ws

  src/
    SISPNetworkVisualizer.jsx top-level app shell
    main.jsx                  React entry point

    context/
      SISPContext.jsx         selection, refs, C++ bridge instance

    sim/
      SimClock.js             sim-time scheduler and playback clock
      engine.js               satellite list, sensor tick, DEGR, energy
      ProtocolService.js      JS protocol scenarios and packet queue
      CppProtocol.js          browser WebSocket client for the bridge
      keplerian.js            orbit propagation and geodetic helpers
      sensorConfig.js         per-satellite sensor definitions
      sensorSim.js            sensor readings, drift, and faults

    threejs/
      ThreeGlobe.jsx          Earth renderer, satellites, packets, camera

    hooks/
      useSatellite.js         selected satellite snapshot
      useInsights.js          fleet-level dashboard snapshot
      useHUD.js               header/playback state
      useScenarios.js         scenario action bindings
      usePlayback.js          playback action bindings

    ui/
      ProtocolLab.jsx         live C++ panel
      SatellitePanel.jsx      selected satellite inspector
      SatelliteListPanel.jsx  constellation list
      InsightsPanel.jsx       fleet charts
      EventLogDrawer.jsx      global event log
      SensorGraphPanel.jsx    sensor graph view
      PlaybackBar.jsx         sim clock controls
      ScenarioBar.jsx         scenario controls

  cpp/
    sisp/c++ implemnetation/  C++ SISP protocol implementation and tests

  docs/
    architecture.md
    protocol-service.md
```

## Bridge Protocol Summary

Browser to server:

- `GET_CONTEXT`: request current satellite context and snapshots.
- `TICK`: advance all C++ satellite contexts by sim milliseconds.
- `EVENT`: inject a C++ FSM event into one satellite.
- `HEARTBEAT`: manually route heartbeat frames.
- `STATUS`: ask the C++ FSM to emit status-style traffic.
- `RESET`: reset C++ contexts.
- `SATELLITE_TELEMETRY`: publish browser telemetry for all satellites.

Server to browser:

- `CONTEXT`: static satellite context plus latest snapshots.
- `SATELLITES`: centralized satellite snapshots.
- `STATE`: compatibility state broadcast.
- `PACKET`: decoded C++ frame emitted by the DLL.

## Environment

See `.env.example`.

Common defaults:

```env
VITE_SISP_WS_URL=ws://localhost:3001
SISP_PORT=3001
```

Use the same port in both values when overriding the bridge port.

## Notes

- This repository currently uses Three.js, not Cesium.
- The C++ implementation folder name is currently spelled `c++ implemnetation`; scripts and paths match that existing folder name.
- The app can run visually without the bridge, but live C++ protocol state and frame traces require `server/index.js` and `sisp.dll`.
- The generated `dist/` folder is build output.

## License

MIT
