#include "sim_hooks.hpp"
#include "sisp_decoder.hpp"
#include "sisp_state_machine.hpp"
#include <cstring>

using namespace SISP;

static sim_tx_cb g_tx_callback = nullptr;
static uint32_t g_current_time_ms = 0;

extern "C" {

void sim_inject_packet(Context* ctx, const uint8_t* buf, uint16_t len) {
    if (!ctx || !buf) return;

    Packet pkt{};
    ErrorCode err = Decoder::decode(buf, len, pkt);
    if (err != ErrorCode::OK) {
        return;  // Silently drop invalid packets
    }

    // Map service code to event
    Event evt;
    switch (pkt.header.svc) {
        case ServiceCode::CORRECTION_REQ:    evt = Event::RX_CORRECTION_REQ; break;
        case ServiceCode::CORRECTION_RSP:    evt = Event::RX_CORRECTION_RSP; break;
        case ServiceCode::RELAY_REQ:         evt = Event::RX_RELAY_REQ; break;
        case ServiceCode::RELAY_ACCEPT:      evt = Event::RX_RELAY_ACCEPT; break;
        case ServiceCode::RELAY_REJECT:      evt = Event::RX_RELAY_REJECT; break;
        case ServiceCode::DOWNLINK_DATA:     evt = Event::RX_DOWNLINK_DATA; break;
        case ServiceCode::DOWNLINK_ACK:      evt = Event::RX_DOWNLINK_ACK; break;
        case ServiceCode::STATUS_BROADCAST:  evt = Event::RX_STATUS_BROADCAST; break;
        case ServiceCode::HEARTBEAT:         evt = Event::RX_HEARTBEAT; break;
        case ServiceCode::HEARTBEAT_ACK:     evt = Event::RX_HEARTBEAT_ACK; break;
        case ServiceCode::BORROW_REQ:        evt = Event::RX_BORROW_REQ; break;
        case ServiceCode::FAILURE:           evt = Event::RX_FAILURE; break;
        default:                             return;  // Ignore reserved codes
    }

    // Check if this packet is for us (or broadcast)
    if (!pkt.is_for_me(ctx->self_id)) {
        return;
    }

    // Dispatch the packet as an event
    StateMachine::dispatch(*ctx, evt, &pkt);
}

void sim_inject_event(Context* ctx, Event evt) {
    if (!ctx) return;
    StateMachine::dispatch(*ctx, evt, nullptr);
}

State sim_get_state(const Context* ctx) {
    if (!ctx) return State::IDLE;
    return ctx->state;
}

void sim_get_corrected(const Context* ctx, float out[3]) {
    if (!ctx || !out) return;
    std::memcpy(out, ctx->corrected_value.data(), sizeof(float) * 3);
}

uint8_t sim_get_degr(const Context* ctx) {
    if (!ctx) return 0;
    return ctx->current_degr;
}

void sim_get_neighbour_degr(const Context* ctx, uint8_t out[256]) {
    if (!ctx || !out) return;
    std::memset(out, 0, 256);  // TODO: Populate from neighbour table
}

void sim_advance_time(Context* ctx, uint32_t ms) {
    if (!ctx) return;
    g_current_time_ms += ms;
    StateMachine::tick(*ctx, g_current_time_ms);
}

void sim_register_tx_callback(sim_tx_cb cb) {
    g_tx_callback = cb;
}

void sim_transmit_packet(uint8_t dst, const uint8_t* buf, uint16_t len) {
    if (!g_tx_callback || !buf) {
        return;
    }
    g_tx_callback(dst, buf, len);
}

}  // extern "C"
