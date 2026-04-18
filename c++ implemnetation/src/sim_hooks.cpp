#include "sim_hooks.hpp"
#include "sisp_decoder.hpp"
#include "sisp_state_machine.hpp"
#include "sisp_correction.hpp"
#include <algorithm>
#include <cstring>
#include <memory>
#include <unordered_map>

using namespace SISP;

static sim_tx_cb g_tx_callback = nullptr;
uint32_t g_current_time_ms = 0;
static std::unordered_map<Context*, sim_tx_cb> g_ctx_tx_callbacks;
static std::unordered_map<Context*, std::unique_ptr<CorrectionFilter>> g_filters;

static bool is_duplicate(Context* ctx, const Packet& pkt, uint32_t now_ms) {
    const uint8_t src = pkt.header.sndr;
    const uint8_t seq = pkt.header.seq;
    if (ctx->last_seen_valid[src] != 0U &&
        ctx->last_seen_seq[src] == seq &&
        (now_ms - ctx->last_seen_ts[src]) < 30000U) {
        return true;
    }

    ctx->last_seen_valid[src] = 1U;
    ctx->last_seen_seq[src] = seq;
    ctx->last_seen_ts[src] = now_ms;
    return false;
}

extern "C" {

Context* sim_create_context(uint8_t my_id) {
    Context* ctx = new Context{};
    StateMachine::init_context(*ctx, my_id);
    return ctx;
}

void sim_destroy_context(Context* ctx) {
    g_filters.erase(ctx);
    g_ctx_tx_callbacks.erase(ctx);
    delete ctx;
}

void sim_use_kalman_filter(Context* ctx, float process_noise, float measurement_noise) {
    if (!ctx) return;
    auto filter = std::make_unique<KalmanFilter>(process_noise, measurement_noise);
    StateMachine::set_correction_filter(*ctx, filter.get());
    g_filters[ctx] = std::move(filter);
}

void sim_use_weighted_median_filter(Context* ctx) {
    if (!ctx) return;
    auto filter = std::make_unique<WeightedMedianFilter>();
    StateMachine::set_correction_filter(*ctx, filter.get());
    g_filters[ctx] = std::move(filter);
}

void sim_use_hybrid_filter(Context* ctx, float process_noise, float measurement_noise) {
    if (!ctx) return;
    auto filter = std::make_unique<HybridFilter>(process_noise, measurement_noise);
    StateMachine::set_correction_filter(*ctx, filter.get());
    g_filters[ctx] = std::move(filter);
}

void sim_clear_correction_filter(Context* ctx) {
    if (!ctx) return;
    g_filters.erase(ctx);
    StateMachine::set_correction_filter(*ctx, nullptr);
}

void sim_inject_correction_rsp(
    Context* ctx,
    uint8_t sndr,
    uint8_t seq,
    uint8_t degr,
    uint8_t sensor_type,
    float x,
    float y,
    float z,
    uint32_t ts_ms
) {
    if (!ctx) return;

    Packet pkt{};
    pkt.header.svc = ServiceCode::CORRECTION_RSP;
    pkt.header.sndr = sndr;
    pkt.header.rcvr = ctx->self_id;
    pkt.header.seq = seq;
    pkt.header.degr = degr;
    pkt.header.flags = FLAG_OFFGRID;

    CorrectionRsp rsp{};
    rsp.sensor_type = static_cast<SensorType>(sensor_type);
    rsp.reading.x = x;
    rsp.reading.y = y;
    rsp.reading.z = z;
    rsp.reading.ts_ms = ts_ms;
    if (serialize_payload(rsp, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len) != ErrorCode::OK) {
        return;
    }

    // Keep neighbour table coherent for weighting/telemetry.
    ctx->neighbour_degr[sndr] = degr;
    ctx->neighbour_last_seen[sndr] = g_current_time_ms;
    ctx->peer_friendly[sndr] = 1U;

    StateMachine::dispatch(*ctx, Event::RX_CORRECTION_RSP, &pkt);
}

void sim_inject_packet(Context* ctx, const uint8_t* buf, uint16_t len) {
    if (!ctx || !buf) return;

    Packet pkt{};
    ErrorCode err = ErrorCode::ERR_LEN;
    if (len == FRAME_SIZE) {
        FrameInfo info{};
        err = Decoder::decode_frame(buf, pkt, info);
    } else {
        err = Decoder::decode(buf, len, pkt);
    }
    if (err != ErrorCode::OK) {
        return;  // Silently drop invalid packets
    }

    // Drop replay packets inside a 30s sliding window.
    if (is_duplicate(ctx, pkt, g_current_time_ms)) {
        return;
    }

    // Update neighbour trust table on every received packet.
    const uint8_t peer = pkt.header.sndr;
    ctx->neighbour_degr[peer] = pkt.header.degr;
    ctx->neighbour_last_seen[peer] = g_current_time_ms;
    ctx->peer_friendly[peer] = 1U;

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
        case ServiceCode::BORROW_DECISION:   evt = Event::RX_BORROW_DECISION; break;
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
    std::memcpy(out, ctx->neighbour_degr.data(), 256);
}

void sim_set_relay_payload(Context* ctx, const uint8_t* data, uint16_t len) {
    if (!ctx) return;

    ctx->relay_tx_storage.fill(0);
    ctx->relay_tx_len = 0;
    ctx->relay_buf = nullptr;
    ctx->relay_buf_len = 0;
    ctx->frag_sent = 0;

    if (!data || len == 0) {
        ctx->frag_total = 1;
        return;
    }

    uint16_t copy_len = std::min<uint16_t>(len, static_cast<uint16_t>(ctx->relay_tx_storage.size()));
    std::memcpy(ctx->relay_tx_storage.data(), data, copy_len);
    ctx->relay_tx_len = copy_len;
    ctx->relay_buf = ctx->relay_tx_storage.data();
    ctx->relay_buf_len = copy_len;

    uint16_t frag_total = static_cast<uint16_t>((copy_len + MAX_FRAGMENT_DATA - 1U) / MAX_FRAGMENT_DATA);
    if (frag_total == 0) {
        frag_total = 1;
    }
    if (frag_total > 255U) {
        frag_total = 255U;
    }
    ctx->frag_total = static_cast<uint8_t>(frag_total);
}

void sim_set_own_reading(Context* ctx, float x, float y, float z, uint32_t ts_ms) {
    if (!ctx) return;
    ctx->own_reading.x = x;
    ctx->own_reading.y = y;
    ctx->own_reading.z = z;
    ctx->own_reading.ts_ms = ts_ms;
}

uint16_t sim_get_relay_rx_len(const Context* ctx) {
    if (!ctx) return 0;
    return ctx->relay_rx_len;
}

uint16_t sim_copy_relay_rx_payload(const Context* ctx, uint8_t* out, uint16_t capacity) {
    if (!ctx || !out || capacity == 0) {
        return 0;
    }

    uint16_t copy_len = std::min<uint16_t>(ctx->relay_rx_len, capacity);
    if (copy_len == 0) {
        return 0;
    }

    std::memcpy(out, ctx->relay_rx_storage.data(), copy_len);
    return copy_len;
}

void sim_get_known_failures(const Context* ctx, uint8_t out[256]) {
    if (!ctx || !out) return;
    std::memcpy(out, ctx->known_failed.data(), 256);
}

uint8_t sim_get_last_failed_satellite(const Context* ctx) {
    if (!ctx) return 0;
    return ctx->last_failed_satellite_id;
}

uint8_t sim_decode_header(
    const uint8_t* buf,
    uint16_t len,
    uint8_t* svc,
    uint8_t* sndr,
    uint8_t* rcvr,
    uint8_t* seq,
    uint8_t* degr,
    uint8_t* flags
) {
    if (!buf || !svc || !sndr || !rcvr || !seq || !degr || !flags) {
        return 0;
    }

    Packet pkt{};
    ErrorCode err = ErrorCode::ERR_LEN;
    if (len == FRAME_SIZE) {
        FrameInfo info{};
        err = Decoder::decode_frame(buf, pkt, info);
    } else {
        err = Decoder::decode(buf, len, pkt);
    }
    if (err != ErrorCode::OK) {
        return 0;
    }

    *svc = static_cast<uint8_t>(pkt.header.svc);
    *sndr = pkt.header.sndr;
    *rcvr = pkt.header.rcvr;
    *seq = pkt.header.seq;
    *degr = pkt.header.degr;
    *flags = pkt.header.flags;
    return 1;
}

void sim_advance_time(Context* ctx, uint32_t ms) {
    if (!ctx) return;
    g_current_time_ms += ms;
    StateMachine::tick(*ctx, g_current_time_ms);
}

void sim_register_tx_callback(sim_tx_cb cb) {
    g_tx_callback = cb;
}

void sim_register_tx_callback_for(Context* ctx, sim_tx_cb cb) {
    if (!ctx) {
        return;
    }
    if (!cb) {
        g_ctx_tx_callbacks.erase(ctx);
        return;
    }
    g_ctx_tx_callbacks[ctx] = cb;
}

void sim_transmit_packet_ctx(const Context& ctx, uint8_t dst, const uint8_t* buf, uint16_t len) {
    if (!buf) {
        return;
    }

    sim_tx_cb cb = g_tx_callback;
    auto it = g_ctx_tx_callbacks.find(const_cast<Context*>(&ctx));
    if (it != g_ctx_tx_callbacks.end() && it->second) {
        cb = it->second;
    }

    if (!cb) {
        return;
    }
    cb(dst, buf, len);
}

void sim_transmit_packet(uint8_t dst, const uint8_t* buf, uint16_t len) {
    if (!buf || !g_tx_callback) return;
    g_tx_callback(dst, buf, len);
}

}  // extern "C"
