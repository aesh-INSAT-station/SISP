#pragma once

#include "sisp_protocol.hpp"
#include "sisp_state_machine.hpp"

#ifdef __cplusplus
extern "C" {
#endif

/* ■■ C-Compatible Simulation Interface ■■■■■■■■■■■■■■■■■■■■■■■■■■ */
/* These are the only functions the Python simulation calls via ctypes */

/**
 * Inject a received packet (as if the radio delivered it).
 */
void sim_inject_packet(SISP::Context* ctx, const uint8_t* buf, uint16_t len);

/**
 * Inject an internal event (fault detected, timer, energy).
 */
void sim_inject_event(SISP::Context* ctx, SISP::Event evt);

/**
 * Observe current state (for assertion in tests).
 */
SISP::State sim_get_state(const SISP::Context* ctx);

/**
 * Get last corrected sensor reading.
 */
void sim_get_corrected(const SISP::Context* ctx, float out[3]);

/**
 * Get current DEGR.
 */
uint8_t sim_get_degr(const SISP::Context* ctx);

/**
 * Get neighbour table (for visualising trust weights).
 */
void sim_get_neighbour_degr(const SISP::Context* ctx, uint8_t out[256]);

/**
 * Tick the timer by N milliseconds.
 */
void sim_advance_time(SISP::Context* ctx, uint32_t ms);

/**
 * Register a TX callback: called whenever a packet is sent.
 */
typedef void (*sim_tx_cb)(uint8_t dst, const uint8_t* buf, uint16_t len);
void sim_register_tx_callback(sim_tx_cb cb);

#ifdef __cplusplus
}
#endif
