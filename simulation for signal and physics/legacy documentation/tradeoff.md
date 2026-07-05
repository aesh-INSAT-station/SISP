## \# SISP RF Architecture Trade Study: Mitigating the Pointing & Energy Bottleneck

##

## \## 1. Problem Statement

## The SISP (Satellite Inter-System Protocol) requires a highly resilient Physical Layer to support its distributed fault-detection (Hybrid Kalman/SVD) and data-sharing services.

##

## Our baseline Ka-band (26 GHz) link budget at a maximum Inter-Satellite Link (ISL) distance of 1000 km requires a transmit power of $1\\text{ W}$ ($+30\\text{ dBm}$). However, due to severe Free-Space Path Loss at Ka-band ($\\approx 180.7\\text{ dB}$), the link only closes mathematically if both satellites employ high-gain \*\*$+23\\text{ dBi}$ antennas\*\*.

##

## \*\*The Bottleneck:\*\* A $+23\\text{ dBi}$ antenna produces a very narrow Half-Power Beamwidth (HPBW) of approximately \*\*$9^\\circ$\*\*. To avoid exceeding the allocated $-2\\text{ dB}$ pointing loss margin, satellites must physically align with an accuracy of $\\pm 3^\\circ$ to $4^\\circ$.

## \* \*\*Hardware Cost:\*\* This strict pointing requirement forces cheap CubeSats to run power-hungry reaction wheels (ADCS) constantly during communication.

## \* \*\*Energy Cost:\*\* Active pointing adds $\\approx 3\\text{ W}$ of continuous DC power draw, dominating the protocol's energy footprint.

##

## \---

##

## \## 2. Physics & Bandwidth Trade-Offs (Ka-Band vs. UHF)

##

## To evaluate alternatives, we compare the baseline Ka-band link against a standard UHF (437 MHz) ISL link at the same 1000 km range.

##

## | Metric | Ka-Band (26 GHz) | UHF (437 MHz) | Impact on SISP |

## | :--- | :--- | :--- | :--- |

## | \*\*Path Loss (FSPL)\*\* | $180.7\\text{ dB}$ | $145.2\\text{ dB}$ | UHF inherently gains $\\approx 35\\text{ dB}$ of physical channel advantage. |

## | \*\*Required Tx Power\*\* | $1\\text{ W}$ | $< 1\\text{ W}$ | UHF requires less raw RF power to close the link. |

## | \*\*Typical Antenna\*\* | Patch Array / Horn ($+23\\text{ dBi}$) | Dipole Wire ($+2\\text{ dBi}$) | UHF allows cheap, deployable hardware. |

## | \*\*Beamwidth / Pointing\*\* | Narrow ($\\approx 9^\\circ$) / Requires ADCS | Omnidirectional ($360^\\circ$) / Zero pointing | UHF eliminates the $\\approx 3\\text{ W}$ ADCS power draw and alignment latency. |

## | \*\*Available Bandwidth\*\* | Massive ($1\\text{ MHz}+$) | Highly Constrained ($\\approx 10\\text{ kHz}$) | \*\*The critical trade-off.\*\* |

## | \*\*Max Data Rate ($R\_b$)\*\* | $100\\text{ kbps}$ to $10+\\text{ Mbps}$ | $9.6\\text{ kbps}$ (Typical max) | Ka-Band is $10\\times$ to $100\\times$ faster. |

##

## \### The Energy Paradox ($E = P \\times t$)

## Because UHF is exceptionally slow, it requires the transmitter to stay powered on much longer, which flips the energy math depending on the payload size:

## 1. \*\*For a 64-Byte \`CORRECTION\_REQ\`:\*\* UHF takes $53\\text{ ms}$ ($\\approx 0.37\\text{ J}$). Ka-Band takes $5\\text{ ms}$ ($\\approx 0.05\\text{ J}$). Both are negligible, but UHF wins operationally because it requires zero pointing setup time.

## 2. \*\*For a 1 MB \`RELAY\_DATA\` dump:\*\* Ka-Band finishes in \*\*3 minutes\*\* ($\\approx 0.5\\text{ Wh}$). UHF takes \*\*over 30 minutes\*\* ($\\approx 3.5\\text{ Wh}$). Furthermore, the typical orbital visibility window (Module M1) closes after 15 minutes, making a 1 MB UHF transfer physically impossible without fragmentation and multiple orbital passes.

##

## \---

##

## \## 3. Alternative Single-Band Solutions Analyzed

##

## If the system must remain on a single frequency band, several mitigation strategies exist:

##

## 1. \*\*Electronically Steered Phased Arrays (Hardware):\*\* Use a flat array of antenna elements to electronically steer the Ka-band beam without moving the satellite chassis. \*Drawback: Increases CubeSat cost and thermal complexity.\*

## 2. \*\*Lowering the Bit Rate (Protocol):\*\* Drop Ka-band to $10\\text{ kbps}$. This yields $+10\\text{ dB}$ in $E\_b/N\_0$, allowing the use of wider-beam $+13\\text{ dBi}$ antennas. \*Drawback: Inherits the same 30-minute transfer limitation as UHF for bulk data.\*

## 3. \*\*Asymmetric Routing (Network):\*\* Force small CubeSats (with wide-beam antennas) to only route data through massive Telecom backbone satellites (with massive $+36\\text{ dBi}$ dishes) via the \`RELAY\` service. \*Drawback: Reduces constellation autonomy if large nodes are unavailable.\*

## 4. \*\*Shrinking the Neighborhood (Geometry):\*\* Limit SISP routing to neighbors within $250\\text{ km}$ instead of $1000\\text{ km}$, saving $12\\text{ dB}$ of path loss and widening the required beam. \*Drawback: Limits the topological reach of the Kalman consensus.\*

##

## \---

##

## \## 4. Final Recommendation: The Dual-Band SISP Architecture

##

## To achieve maximum resilience and energy efficiency without sacrificing throughput, SISP implements a \*\*Dual-Band Transport Architecture\*\*. This maps perfectly to the C++ implementation's ability to embed transport-mode flags inside the fixed 64-byte frame.

##

## \### Plane A: The Control Plane (UHF at 9.6 kbps)

## \* \*\*Used for:\*\* \`HEARTBEAT\`, \`STATUS\_BROADCAST\`, \`CORRECTION\_REQ/RSP\`, \`RELAY\_REQ\`, \`BORROW\_REQ\`.

## \* \*\*Mechanism:\*\* Omnidirectional broadcast.

## \* \*\*Advantage:\*\* Satellites can be tumbling or in safe-mode (no ADCS). The decentralized Kalman/SVD algorithm can constantly run in the background with zero pointing overhead and near-zero battery cost. SISP nodes form a continuous, low-latency awareness mesh.

##

## \### Plane B: The Data Plane (Ka-Band at 100+ kbps)

## \* \*\*Used for:\*\* \`DOWNLINK\_DATA\` and \`BORROW\_DATA\` (Bulk payloads).

## \* \*\*Mechanism:\*\* Point-to-point directional link.

## \* \*\*Advantage:\*\* Activated \*only\* when a heavy payload transfer is accepted. The state machine commands both the requesting and receiving satellites to spin up their ADCS, align their $+23\\text{ dBi}$ Ka-band antennas, blast the $1\\text{ MB}$ payload across the gap in under 3 minutes (well within the orbital visibility window), and immediately spin down to conserve power.

##

## \### Conclusion

## By decoupling the "Whisper" control plane (UHF) from the "Firehose" data plane (Ka-Band), the SISP protocol overcomes the physical pointing constraints of high-frequency RF links. It ensures that the critical fault-detection state machine never drops due to a missed alignment, while preserving the bandwidth necessary to save megabytes of diagnostic data during a mission-critical failure.