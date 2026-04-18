#pragma once

#include "sisp_protocol.hpp"
#include "sisp_state_machine.hpp"

#ifdef __cplusplus
extern uint32_t g_current_time_ms;
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ■■ C-Compatible Simulation Interface ■■■■■■■■■■■■■■■■■■■■■■■■■■ */
/* These are the only functions the Python simulation calls via ctypes */

/**
 * Allocate/destroy a protocol context for Python simulation.
 */
__declspec(dllexport) SISP::Context* sim_create_context(uint8_t my_id);
__declspec(dllexport) void sim_destroy_context(SISP::Context* ctx);

/**
 * Inject a received packet (as if the radio delivered it).
 */
__declspec(dllexport) void sim_inject_packet(SISP::Context* ctx, const uint8_t* buf, uint16_t len);

/**
 * Inject an internal event (fault detected, timer, energy).
 */
__declspec(dllexport) void sim_inject_event(SISP::Context* ctx, SISP::Event evt);

/**
 * Observe current state (for assertion in tests).
 */
__declspec(dllexport) SISP::State sim_get_state(const SISP::Context* ctx);

/**
 * Get last corrected sensor reading.
 */
__declspec(dllexport) void sim_get_corrected(const SISP::Context* ctx, float out[3]);

/**
 * Get current DEGR.
 */
__declspec(dllexport) uint8_t sim_get_degr(const SISP::Context* ctx);

/**
 * Get neighbour table (for visualising trust weights).
 */
__declspec(dllexport) void sim_get_neighbour_degr(const SISP::Context* ctx, uint8_t out[256]);

/**
 * Configure relay payload bytes to be fragmented and sent by this context.
 */
__declspec(dllexport) void sim_set_relay_payload(SISP::Context* ctx, const uint8_t* data, uint16_t len);

/**
 * Get assembled relay payload length received by this context.
 */
__declspec(dllexport) uint16_t sim_get_relay_rx_len(const SISP::Context* ctx);

/**
 * Copy assembled relay payload bytes received by this context.
 * Returns number of bytes copied into out.
 */
__declspec(dllexport) uint16_t sim_copy_relay_rx_payload(const SISP::Context* ctx, uint8_t* out, uint16_t capacity);

/**
 * Get known failed satellites (1 if failed, 0 if not).
 */
__declspec(dllexport) void sim_get_known_failures(const SISP::Context* ctx, uint8_t out[256]);

/**
 * Get most recent failed satellite ID.
 */
__declspec(dllexport) uint8_t sim_get_last_failed_satellite(const SISP::Context* ctx);

/**
 * Attach a Kalman correction filter to a context.
 */
__declspec(dllexport) void sim_use_kalman_filter(SISP::Context* ctx, float process_noise, float measurement_noise);

/**
 * Attach a weighted median correction filter to a context.
 */
__declspec(dllexport) void sim_use_weighted_median_filter(SISP::Context* ctx);

/**
 * Attach a hybrid (weighted median + kalman smoothing) correction filter.
 */
__declspec(dllexport) void sim_use_hybrid_filter(SISP::Context* ctx, float process_noise, float measurement_noise);

/**
 * Remove any attached correction filter and use raw weighted average fallback.
 */
__declspec(dllexport) void sim_clear_correction_filter(SISP::Context* ctx);

/**
 * Inject a populated correction response directly into a context.
 * This is useful for simulation with synthetic noisy measurements.
 */
__declspec(dllexport) void sim_inject_correction_rsp(
	SISP::Context* ctx,
	uint8_t sndr,
	uint8_t seq,
	uint8_t degr,
	uint8_t sensor_type,
	float x,
	float y,
	float z,
	uint32_t ts_ms
);

/**
 * Decode frame header using native C++ decoder for reliable Python logging.
 * Returns 1 on success, 0 on decode failure.
 */
__declspec(dllexport) uint8_t sim_decode_header(
	const uint8_t* buf,
	uint16_t len,
	uint8_t* svc,
	uint8_t* sndr,
	uint8_t* rcvr,
	uint8_t* seq,
	uint8_t* degr,
	uint8_t* flags
);

/**
 * Tick the timer by N milliseconds.
 */
__declspec(dllexport) void sim_advance_time(SISP::Context* ctx, uint32_t ms);

/**
 * Register a TX callback: called whenever a packet is sent.
 */
typedef void (*sim_tx_cb)(uint8_t dst, const uint8_t* buf, uint16_t len);
__declspec(dllexport) void sim_register_tx_callback(sim_tx_cb cb);
__declspec(dllexport) void sim_register_tx_callback_for(SISP::Context* ctx, sim_tx_cb cb);

/**
 * Provide a node-local sensor reading used for CORRECTION_RSP payloads.
 */
__declspec(dllexport) void sim_set_own_reading(SISP::Context* ctx, float x, float y, float z, uint32_t ts_ms);

/**
 * Send a frame through the registered callback.
 */
__declspec(dllexport) void sim_transmit_packet(uint8_t dst, const uint8_t* buf, uint16_t len);

#ifdef __cplusplus
void sim_transmit_packet_ctx(const SISP::Context& ctx, uint8_t dst, const uint8_t* buf, uint16_t len);
}
#endif
