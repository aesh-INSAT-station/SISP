#include "sisp_state_machine.hpp"
#include "sisp_encoder.hpp"
#include "sim_hooks.hpp"
#include <cstring>
#include <algorithm>

namespace SISP {

static void action_idle_nop(Context& ctx, const Packet* pkt);
static void action_send_correction_req(Context& ctx, const Packet* pkt);
static void action_send_correction_rsp(Context& ctx, const Packet* pkt);
static void action_collect_rsp(Context& ctx, const Packet* pkt);
static void action_run_kalman(Context& ctx, const Packet* pkt);
static void action_send_relay_req(Context& ctx, const Packet* pkt);
static void action_send_relay_accept(Context& ctx, const Packet* pkt);
static void action_send_relay_reject(Context& ctx, const Packet* pkt);
static void action_store_frag(Context& ctx, const Packet* pkt);
static void action_send_frag(Context& ctx, const Packet* pkt);
static void action_store_status(Context& ctx, const Packet* pkt);
static void action_store_heartbeat(Context& ctx, const Packet* pkt);
static void action_send_borrow_req(Context& ctx, const Packet* pkt);
static void action_receive_borrow_req(Context& ctx, const Packet* pkt);
static void action_store_borrow_decision(Context& ctx, const Packet* pkt);
static void action_send_borrow_data(Context& ctx, const Packet* pkt);
static void action_send_ack(Context& ctx, const Packet* pkt);
static void action_broadcast_failure(Context& ctx, const Packet* pkt);
static void action_record_foreign_failure(Context& ctx, const Packet* pkt);
static void action_reset(Context& ctx, const Packet* pkt);

static bool sensor_known_missing(const Context& ctx, uint8_t peer, SensorType sensor) {
    const uint8_t mask = ctx.peer_sensor_mask[peer];
    return mask != 0U && (mask & sensor_mask_for(sensor)) == 0U;
}

static bool peer_supports_phy(const Context& ctx, uint8_t peer, PhyProfile phy) {
    const uint8_t mask = ctx.peer_phy_cap_mask[peer];
    return mask != 0U && (mask & phy_cap_for(phy)) != 0U;
}

static PhyProfile select_tx_phy(const Context& ctx, const Packet& pkt, uint8_t dst) {
    const bool bulk_service = pkt.header.svc == ServiceCode::DOWNLINK_DATA ||
                              pkt.header.svc == ServiceCode::DOWNLINK_ACK;
    if (!bulk_service || dst == BCAST_ADDR) {
        return PhyProfile::CONTROL_437_NARROW;
    }

    if ((ctx.local_phy_cap_mask & PHY_CAP_BULK_437_WIDE) != 0U &&
        ctx.active_bulk_phy == PhyProfile::BULK_437_WIDE &&
        peer_supports_phy(ctx, dst, PhyProfile::BULK_437_WIDE)) {
        return PhyProfile::BULK_437_WIDE;
    }

    return PhyProfile::CONTROL_437_NARROW;
}

static void transmit_packet(Context& ctx, const Packet& pkt, uint8_t dst, const TransportMeta& meta) {
    TransportMeta tx_meta = meta;
    tx_meta.phy_profile = select_tx_phy(ctx, pkt, dst);
    tx_meta.phy_cap_mask = ctx.local_phy_cap_mask;
    ctx.last_tx_phy = tx_meta.phy_profile;

    uint8_t frame[FRAME_SIZE];
    if (Encoder::encode_frame(pkt, tx_meta, frame) != ErrorCode::OK) {
        return;
    }
    sim_transmit_packet_ctx(ctx, dst, frame, FRAME_SIZE);
}

static Transition g_trans[static_cast<size_t>(State::STATE_COUNT)]
                         [static_cast<size_t>(Event::EVT_COUNT)];
static bool g_trans_initialized = false;

static void init_transitions() {
    if (g_trans_initialized) return;

    for (size_t s = 0; s < static_cast<size_t>(State::STATE_COUNT); ++s) {
        for (size_t e = 0; e < static_cast<size_t>(Event::EVT_COUNT); ++e) {
            g_trans[s][e].action = nullptr;
            g_trans[s][e].next_state = State::IDLE;
        }
    }

    size_t s = static_cast<size_t>(State::IDLE);
    g_trans[s][static_cast<size_t>(Event::FAULT_DETECTED)] = { State::CORR_WAIT_RSP, action_send_correction_req };
    g_trans[s][static_cast<size_t>(Event::RX_CORRECTION_REQ)] = { State::CORR_RESPONDING, action_send_correction_rsp };
    g_trans[s][static_cast<size_t>(Event::RX_RELAY_REQ)] = { State::RELAY_RECEIVING, action_send_relay_accept };
    g_trans[s][static_cast<size_t>(Event::RX_STATUS_BROADCAST)] = { State::IDLE, action_store_status };
    g_trans[s][static_cast<size_t>(Event::RX_HEARTBEAT)] = { State::IDLE, action_store_heartbeat };
    g_trans[s][static_cast<size_t>(Event::RX_BORROW_REQ)] = { State::BORROW_SAMPLING, action_receive_borrow_req };
    g_trans[s][static_cast<size_t>(Event::RX_BORROW_DECISION)] = { State::IDLE, action_store_borrow_decision };
    g_trans[s][static_cast<size_t>(Event::ENERGY_LOW)] = { State::RELAY_WAIT_ACCEPT, action_send_relay_req };
    g_trans[s][static_cast<size_t>(Event::GS_VISIBLE)] = { State::BORROW_WAIT_ACCEPT, action_send_borrow_req };
    g_trans[s][static_cast<size_t>(Event::GS_LOST)] = { State::RELAY_WAIT_ACCEPT, action_send_relay_req };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::CORR_WAIT_RSP);
    g_trans[s][static_cast<size_t>(Event::RX_CORRECTION_RSP)] = { State::CORR_COLLECTING, action_collect_rsp };
    g_trans[s][static_cast<size_t>(Event::RX_HEARTBEAT)] = { State::CORR_WAIT_RSP, action_store_heartbeat };
    g_trans[s][static_cast<size_t>(Event::TIMER_EXPIRED)] = { State::CORR_COMPUTING, action_run_kalman };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::CORR_COLLECTING);
    g_trans[s][static_cast<size_t>(Event::RX_CORRECTION_RSP)] = { State::CORR_COLLECTING, action_collect_rsp };
    g_trans[s][static_cast<size_t>(Event::RX_HEARTBEAT)] = { State::CORR_COLLECTING, action_store_heartbeat };
    g_trans[s][static_cast<size_t>(Event::TIMER_EXPIRED)] = { State::CORR_COMPUTING, action_run_kalman };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::CORR_COMPUTING);
    g_trans[s][static_cast<size_t>(Event::CORRECTION_DONE)] = { State::IDLE, action_run_kalman };

    s = static_cast<size_t>(State::CORR_RESPONDING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::IDLE, action_send_correction_rsp };

    s = static_cast<size_t>(State::RELAY_WAIT_ACCEPT);
    g_trans[s][static_cast<size_t>(Event::RX_RELAY_ACCEPT)] = { State::RELAY_SENDING, action_send_frag };
    g_trans[s][static_cast<size_t>(Event::RX_RELAY_REJECT)] = { State::IDLE, action_idle_nop };
    g_trans[s][static_cast<size_t>(Event::TIMER_EXPIRED)] = { State::RELAY_WAIT_ACCEPT, action_send_relay_req };

    s = static_cast<size_t>(State::RELAY_SENDING);
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_SENT)] = { State::RELAY_WAIT_ACK, action_send_frag };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::RELAY_WAIT_ACK);
    g_trans[s][static_cast<size_t>(Event::RX_DOWNLINK_ACK)] = { State::RELAY_DONE, action_send_ack };
    g_trans[s][static_cast<size_t>(Event::TIMER_EXPIRED)] = { State::RELAY_WAIT_ACCEPT, action_send_relay_req };

    s = static_cast<size_t>(State::RELAY_RECEIVING);
    g_trans[s][static_cast<size_t>(Event::RX_DOWNLINK_DATA)] = { State::RELAY_STORING, action_store_frag };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::RELAY_STORING);
    g_trans[s][static_cast<size_t>(Event::RX_DOWNLINK_DATA)] = { State::RELAY_STORING, action_store_frag };
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_RCVD)] = { State::RELAY_DOWNLINKING, action_store_frag };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::RELAY_DOWNLINKING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::IDLE, action_send_ack };

    s = static_cast<size_t>(State::BORROW_SAMPLING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::BORROW_SENDING, action_send_borrow_data };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::BORROW_WAIT_ACCEPT);
    g_trans[s][static_cast<size_t>(Event::RX_BORROW_DECISION)] = { State::BORROW_RECEIVING, action_store_borrow_decision };
    g_trans[s][static_cast<size_t>(Event::TIMER_EXPIRED)] = { State::BORROW_WAIT_ACCEPT, action_send_borrow_req };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::BORROW_RECEIVING);
    g_trans[s][static_cast<size_t>(Event::RX_DOWNLINK_DATA)] = { State::BORROW_RECEIVING, action_store_frag };
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_RCVD)] = { State::BORROW_DONE, action_idle_nop };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::BORROW_SENDING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::BORROW_SENDING, action_send_borrow_data };
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_SENT)] = { State::BORROW_DONE, action_idle_nop };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    for (size_t state_index = 0; state_index < static_cast<size_t>(State::STATE_COUNT); ++state_index) {
        // Internal critical failure (this satellite detected its own failure) → go critical
        g_trans[state_index][static_cast<size_t>(Event::CRITICAL_FAILURE)] = { State::CRITICAL_FAIL, action_broadcast_failure };
        // External failure (another satellite failed) → record but stay in current state
        State current_state = static_cast<State>(state_index);
        g_trans[state_index][static_cast<size_t>(Event::RX_FAILURE)] = { current_state, action_record_foreign_failure };
        // RESET should always provide an escape hatch back to IDLE.
        g_trans[state_index][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };
    }

    g_trans_initialized = true;
}

static void action_idle_nop(Context&, const Packet*) {
}

static void action_send_correction_req(Context& ctx, const Packet*) {
    ctx.service = ServiceCode::CORRECTION_REQ;
    ctx.timer_deadline_ms = g_current_time_ms + 5000;
    ctx.rsp_count = 0;
    ctx.rsp_timestamps_ms.fill(0);

    // Ensure correction requests always target a valid sensor type.
    if (ctx.last_correction_req.sensor_type != SensorType::MAGNETOMETER &&
        ctx.last_correction_req.sensor_type != SensorType::SUN_SENSOR &&
        ctx.last_correction_req.sensor_type != SensorType::GYROSCOPE &&
        ctx.last_correction_req.sensor_type != SensorType::STAR_TRACKER &&
        ctx.last_correction_req.sensor_type != SensorType::THERMAL &&
        ctx.last_correction_req.sensor_type != SensorType::OPTICAL) {
        ctx.last_correction_req.sensor_type = SensorType::MAGNETOMETER;
    }

    Packet out{};
    out.header.svc = ServiceCode::CORRECTION_REQ;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = BCAST_ADDR;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    CorrectionReq req{ctx.last_correction_req.sensor_type, 30};
    serialize_payload(req, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 1;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, BCAST_ADDR, meta);
}

static void action_send_correction_rsp(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;

    CorrectionReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_correction_req = req;
    }

    Packet out{};
    out.header.svc = ServiceCode::CORRECTION_RSP;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = pkt->header.sndr;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID | FLAG_PROTO;

    CorrectionRsp rsp{};
    rsp.sensor_type = ctx.last_correction_req.sensor_type;
    rsp.reading = ctx.own_reading;
    serialize_payload(rsp, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.session_id = static_cast<uint16_t>(ctx.out_seq);
    meta.ack_seq = pkt->header.seq;
    meta.window = 1;
    transmit_packet(ctx, out, pkt->header.sndr, meta);
}

static void action_collect_rsp(Context& ctx, const Packet* pkt) {
    if (!pkt || ctx.rsp_count >= 8) {
        return;
    }

    CorrectionRsp rsp{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, rsp) != ErrorCode::OK) {
        return;
    }

    // Correction weighting must use the correction message stream itself.
    // Ignore responses for a different sensor type.
    if (rsp.sensor_type != ctx.last_correction_req.sensor_type) {
        return;
    }
    if (sensor_known_missing(ctx, pkt->header.sndr, rsp.sensor_type)) {
        return;
    }

    ctx.last_correction_rsp = rsp;
    ctx.rsp_readings[ctx.rsp_count][0] = rsp.reading.x;
    ctx.rsp_readings[ctx.rsp_count][1] = rsp.reading.y;
    ctx.rsp_readings[ctx.rsp_count][2] = rsp.reading.z;
    ctx.rsp_timestamps_ms[ctx.rsp_count] = rsp.reading.ts_ms;
    float peer_degr = static_cast<float>(pkt->header.degr);
    ctx.rsp_weights[ctx.rsp_count] = std::max(0.05f, 1.0f - peer_degr / 15.0f);
    ctx.rsp_count++;
}


static void action_run_kalman(Context& ctx, const Packet*) {
    if (!ctx.correction_filter) {
        // No correction filter configured; use raw weighted average as fallback
        if (ctx.rsp_count == 0) {
            ctx.corrected_value.fill(0.0f);
            return;
        }

        ctx.corrected_value[0] = 0.0f;
        ctx.corrected_value[1] = 0.0f;
        ctx.corrected_value[2] = 0.0f;
        float total_w = 0.0f;
        for (uint8_t i = 0; i < ctx.rsp_count; ++i) {
            float w = ctx.rsp_weights[i];
            ctx.corrected_value[0] += ctx.rsp_readings[i][0] * w;
            ctx.corrected_value[1] += ctx.rsp_readings[i][1] * w;
            ctx.corrected_value[2] += ctx.rsp_readings[i][2] * w;
            total_w += w;
        }
        if (total_w > 0.0f) {
            ctx.corrected_value[0] /= total_w;
            ctx.corrected_value[1] /= total_w;
            ctx.corrected_value[2] /= total_w;
        }
        return;
    }

    // Use the configured correction filter
    CorrectionInput filter_input{};
    for (uint8_t i = 0; i < ctx.rsp_count && i < 8; ++i) {
        filter_input.readings[i].x = ctx.rsp_readings[i][0];
        filter_input.readings[i].y = ctx.rsp_readings[i][1];
        filter_input.readings[i].z = ctx.rsp_readings[i][2];
        filter_input.readings[i].ts_ms = ctx.rsp_timestamps_ms[i];
        filter_input.weights[i] = ctx.rsp_weights[i];
    }
    filter_input.count = ctx.rsp_count;

    CorrectionOutput filter_output{};
    if (ctx.correction_filter->apply(filter_input, filter_output)) {
        ctx.corrected_value[0] = filter_output.corrected.x;
        ctx.corrected_value[1] = filter_output.corrected.y;
        ctx.corrected_value[2] = filter_output.corrected.z;
    } else {
        ctx.corrected_value.fill(0.0f);
    }
}

static void action_send_relay_req(Context& ctx, const Packet*) {
    const bool is_retry = (ctx.state == State::RELAY_WAIT_ACCEPT || ctx.state == State::RELAY_WAIT_ACK);
    if (!is_retry) {
        ctx.retry_count = 0;
    } else {
        if (ctx.retry_count >= ctx.max_retries) {
            // Retry budget exhausted: stop scheduling new relay retries.
            ctx.timer_deadline_ms = 0;
            return;
        }
        ++ctx.retry_count;
    }

    ctx.service = ServiceCode::RELAY_REQ;
    ctx.timer_deadline_ms = g_current_time_ms + 10000;
    ctx.frag_sent = 0;
    ctx.frag_rcvd_mask = 0;

    if (ctx.relay_buf && ctx.relay_buf_len > 0) {
        uint16_t total = static_cast<uint16_t>((ctx.relay_buf_len + MAX_FRAGMENT_DATA - 1U) / MAX_FRAGMENT_DATA);
        if (total == 0) {
            total = 1;
        }
        if (total > 255U) {
            total = 255U;
        }
        ctx.frag_total = static_cast<uint8_t>(total);
    }
    if (ctx.frag_total == 0) {
        ctx.frag_total = 1;
    }

    Packet out{};
    out.header.svc = ServiceCode::RELAY_REQ;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = BCAST_ADDR;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);

    RelayReq req{};
    req.hop_count = 1;
    req.fragment_count = ctx.frag_total;
    req.window_s = 60;
    serialize_payload(req, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 2;
    meta.hop_limit = 8;
    meta.relay_hops_remaining = 3;
    meta.relay_path_id = 1;
    transmit_packet(ctx, out, BCAST_ADDR, meta);
}

static void action_send_relay_accept(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;
    ctx.active_bulk_phy = peer_supports_phy(ctx, ctx.peer_id, PhyProfile::BULK_437_WIDE)
                              ? PhyProfile::BULK_437_WIDE
                              : PhyProfile::CONTROL_437_NARROW;

    RelayReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_relay_req = req;
        ctx.frag_total = static_cast<uint8_t>(req.fragment_count);
        if (ctx.frag_total == 0) {
            ctx.frag_total = 1;
        }
        ctx.frag_sent = 0;
        ctx.frag_rcvd_mask = 0;
        ctx.relay_rx_len = 0;
        ctx.relay_rx_storage.fill(0);
    }

    Packet out{};
    out.header.svc = ServiceCode::RELAY_ACCEPT;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = pkt->header.sndr;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);

    RelayDecision decision{};
    decision.accepted = 1;
    decision.reason = 0;
    serialize_payload(decision, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 3;
    meta.hop_limit = 8;
    meta.relay_hops_remaining = 3;
    meta.relay_path_id = 1;
    transmit_packet(ctx, out, pkt->header.sndr, meta);
}

static void action_send_relay_reject(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;
    RelayDecision decision{};
    decision.accepted = 0;
    decision.reason = 1;
    ctx.last_relay_decision = decision;

    Packet out{};
    out.header.svc = ServiceCode::RELAY_REJECT;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = pkt->header.sndr;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);
    serialize_payload(decision, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 4;
    meta.hop_limit = 8;
    meta.relay_hops_remaining = 1;
    meta.relay_path_id = 1;
    transmit_packet(ctx, out, pkt->header.sndr, meta);
}

static void action_store_frag(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    DownlinkData data{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, data) == ErrorCode::OK) {
        ctx.last_downlink_data = data;

        uint16_t offset = static_cast<uint16_t>(data.fragment_index) * MAX_FRAGMENT_DATA;
        if (data.data_len > 0 && offset < ctx.relay_rx_storage.size()) {
            uint16_t available = static_cast<uint16_t>(ctx.relay_rx_storage.size() - offset);
            uint16_t copy_len = std::min<uint16_t>(data.data_len, available);
            std::memcpy(ctx.relay_rx_storage.data() + offset, data.data.data(), copy_len);

            uint16_t assembled = static_cast<uint16_t>(offset + copy_len);
            if (assembled > ctx.relay_rx_len) {
                ctx.relay_rx_len = assembled;
            }
        }

        if (data.fragment_index < 32U) {
            ctx.frag_rcvd_mask |= (1u << data.fragment_index);
        }
    }
}

static void action_send_frag(Context& ctx, const Packet* pkt) {
    if (pkt) {
        ctx.peer_id = pkt->header.sndr;
        ctx.retry_count = 0;
        ctx.active_bulk_phy = peer_supports_phy(ctx, ctx.peer_id, PhyProfile::BULK_437_WIDE)
                                  ? PhyProfile::BULK_437_WIDE
                                  : PhyProfile::CONTROL_437_NARROW;
    }

    if (ctx.peer_id == 0) {
        return;
    }

    if (ctx.frag_total == 0) {
        ctx.frag_total = 1;
    }

    while (ctx.frag_sent < ctx.frag_total) {
        uint16_t offset = static_cast<uint16_t>(ctx.frag_sent) * MAX_FRAGMENT_DATA;
        uint16_t chunk_len = 0;
        DownlinkData data{};
        data.fragment_index = ctx.frag_sent;
        data.fragment_total = ctx.frag_total;
        if (ctx.relay_buf && ctx.relay_buf_len > 0 && offset < ctx.relay_buf_len) {
            uint16_t remaining = static_cast<uint16_t>(ctx.relay_buf_len - offset);
            chunk_len = std::min<uint16_t>(remaining, MAX_FRAGMENT_DATA);
            std::memcpy(data.data.data(), ctx.relay_buf + offset, chunk_len);
        }
        data.data_len = chunk_len;

        Packet out{};
        out.header.svc = ServiceCode::DOWNLINK_DATA;
        out.header.sndr = ctx.self_id;
        out.header.rcvr = ctx.peer_id;
        out.header.seq = ++ctx.out_seq;
        ctx.seq = ctx.out_seq;
        out.header.degr = ctx.current_degr;
        out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);
        serialize_payload(data, out.payload.data(), MAX_PAYLOAD, out.payload_len);

        TransportMeta meta{};
        meta.datagram_tag = 6;
        meta.hop_limit = 8;
        meta.relay_hops_remaining = 3;
        meta.relay_path_id = 1;
        transmit_packet(ctx, out, ctx.peer_id, meta);

        ++ctx.frag_sent;
    }
}

static void action_store_status(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    Status status{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, status) == ErrorCode::OK) {
        ctx.last_status = status;
        const uint8_t peer = pkt->header.sndr;
        ctx.peer_friendly[peer] = 1U;
        ctx.peer_sensor_mask[peer] = status.sensor_mask;
        ctx.peer_energy_pct[peer] = status.energy_pct;
        ctx.peer_phy_cap_mask[peer] = status.phy_cap_mask;
    }
}

static void action_store_heartbeat(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    Heartbeat heartbeat{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, heartbeat) == ErrorCode::OK) {
        ctx.last_heartbeat = heartbeat;
        const uint8_t peer = pkt->header.sndr;
        ctx.peer_friendly[peer] = 1U;
        ctx.peer_energy_pct[peer] = heartbeat.energy_pct;
        if (ctx.peer_phy_cap_mask[peer] == 0U) {
            ctx.peer_phy_cap_mask[peer] = PHY_CAP_CONTROL_437_NARROW;
        }
    }
}

static void action_send_borrow_req(Context& ctx, const Packet*) {
    const bool is_retry = (ctx.state == State::BORROW_WAIT_ACCEPT);
    if (!is_retry) {
        ctx.retry_count = 0;
    } else {
        if (ctx.retry_count >= ctx.max_retries) {
            // Retry budget exhausted: stop scheduling new borrow retries.
            ctx.timer_deadline_ms = 0;
            return;
        }
        ++ctx.retry_count;
    }

    ctx.service = ServiceCode::BORROW_REQ;
    ctx.timer_deadline_ms = g_current_time_ms + 15000;

    if (ctx.borrow_duration_s == 0) {
        ctx.borrow_duration_s = 60;
    }

    Packet out{};
    out.header.svc = ServiceCode::BORROW_REQ;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = BCAST_ADDR;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    BorrowReq req{};
    req.sensor_type = ctx.borrow_sensor;
    req.duration_s = ctx.borrow_duration_s;
    req.priority = 1;
    serialize_payload(req, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 9;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, BCAST_ADDR, meta);
}

static void action_receive_borrow_req(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;

    BorrowReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_borrow_req = req;
        ctx.borrow_sensor = req.sensor_type;
        ctx.borrow_duration_s = req.duration_s;
    }

    if (ctx.relay_buf && ctx.relay_buf_len > 0) {
        uint16_t total = static_cast<uint16_t>((ctx.relay_buf_len + MAX_FRAGMENT_DATA - 1U) / MAX_FRAGMENT_DATA);
        if (total == 0) {
            total = 1;
        }
        if (total > 255U) {
            total = 255U;
        }
        ctx.frag_total = static_cast<uint8_t>(total);
    }
    if (ctx.frag_total == 0) {
        ctx.frag_total = 1;
    }
    ctx.frag_sent = 0;

    Packet out{};
    out.header.svc = ServiceCode::BORROW_DECISION;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = ctx.peer_id;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    BorrowDecision decision{};
    decision.accepted = ((ctx.local_sensor_mask & sensor_mask_for(ctx.borrow_sensor)) != 0U) ? 1U : 0U;
    decision.duration_s = ctx.borrow_duration_s;
    ctx.last_borrow_decision = decision;
    serialize_payload(decision, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 10;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, out.header.rcvr, meta);
}

static void action_store_borrow_decision(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }

    BorrowDecision decision{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, decision) != ErrorCode::OK) {
        return;
    }

    ctx.peer_id = pkt->header.sndr;
    ctx.retry_count = 0;
    ctx.last_borrow_decision = decision;
    if (decision.accepted != 0U && peer_supports_phy(ctx, ctx.peer_id, PhyProfile::BULK_437_WIDE)) {
        ctx.active_bulk_phy = PhyProfile::BULK_437_WIDE;
    } else {
        ctx.active_bulk_phy = PhyProfile::CONTROL_437_NARROW;
    }
    if (decision.duration_s > 0) {
        ctx.borrow_duration_s = decision.duration_s;
    }
}

static void action_send_borrow_data(Context& ctx, const Packet* pkt) {
    (void)pkt;

    if (ctx.frag_total == 0) {
        ctx.frag_total = 1;
    }
    if (ctx.frag_sent >= ctx.frag_total) {
        return;
    }

    uint16_t offset = static_cast<uint16_t>(ctx.frag_sent) * MAX_FRAGMENT_DATA;
    uint16_t chunk_len = 0;
    DownlinkData data{};
    data.fragment_index = ctx.frag_sent;
    data.fragment_total = ctx.frag_total;
    if (ctx.relay_buf && ctx.relay_buf_len > 0 && offset < ctx.relay_buf_len) {
        uint16_t remaining = static_cast<uint16_t>(ctx.relay_buf_len - offset);
        chunk_len = std::min<uint16_t>(remaining, MAX_FRAGMENT_DATA);
        std::memcpy(data.data.data(), ctx.relay_buf + offset, chunk_len);
    }
    data.data_len = chunk_len;

    Packet out{};
    out.header.svc = ServiceCode::DOWNLINK_DATA;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = ctx.peer_id;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    serialize_payload(data, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 11;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, out.header.rcvr, meta);

    ++ctx.frag_sent;
}

static void action_send_ack(Context& ctx, const Packet* pkt) {
    uint8_t rcvr = pkt ? pkt->header.sndr : ctx.peer_id;
    if (rcvr == 0) {
        return;
    }

    Packet out{};
    out.header.svc = ServiceCode::DOWNLINK_ACK;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = rcvr;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    DownlinkAck ack{};
    uint8_t ack_seq = pkt ? pkt->header.seq : 0;
    ack.crc32 = static_cast<uint32_t>(ack_seq) | (static_cast<uint32_t>(ctx.frag_sent) << 8);
    serialize_payload(ack, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 8;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, rcvr, meta);
}

static void action_broadcast_failure(Context& ctx, const Packet*) {
    ctx.current_degr = 15;

    Packet out{};
    out.header.svc = ServiceCode::FAILURE;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = BCAST_ADDR;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = 15;
    out.header.flags = FLAG_OFFGRID;

    Failure failure{};
    failure.code = 1;
    failure.detail = 0;
    failure.degr = 15;
    serialize_payload(failure, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 5;
    meta.hop_limit = 1;
    transmit_packet(ctx, out, BCAST_ADDR, meta);
}

static void action_record_foreign_failure(Context& ctx, const Packet* pkt) {
    // Record that another satellite has failed, but don't cascade critical failure
    if (pkt) {
        uint8_t failed_sat_id = pkt->header.sndr;
        ctx.known_failed[failed_sat_id] = 1;
        ctx.last_failed_satellite_id = failed_sat_id;
        ctx.peer_friendly[failed_sat_id] = 0U;
        // Parse failure reason if available
        Failure failure{};
        if (deserialize_payload(pkt->payload.data(), pkt->payload_len, failure) == ErrorCode::OK) {
            // Store for logging/monitoring
            ctx.last_failure = failure;
        }
    }
    // Don't transition state - just record and continue
}

static void action_reset(Context& ctx, const Packet*) {
    uint8_t self_id = ctx.self_id;
    ctx = Context{};
    ctx.self_id = self_id;
}

void StateMachine::dispatch(Context& ctx, Event evt, const Packet* pkt) {
    init_transitions();

    size_t state_idx = static_cast<size_t>(ctx.state);
    size_t evt_idx = static_cast<size_t>(evt);
    if (state_idx >= static_cast<size_t>(State::STATE_COUNT) || evt_idx >= static_cast<size_t>(Event::EVT_COUNT)) {
        return;
    }

    const Transition& tr = g_trans[state_idx][evt_idx];
    if (!tr.action) {
        return;
    }

    tr.action(ctx, pkt);
    ctx.state = tr.next_state;
}

void StateMachine::init_context(Context& ctx, uint8_t my_id) {
    ctx = Context{};
    ctx.self_id = my_id;
}

void StateMachine::set_correction_filter(Context& ctx, CorrectionFilter* filter) {
    ctx.correction_filter = filter;
}

void StateMachine::tick(Context& ctx, uint32_t now_ms) {
    if (ctx.timer_deadline_ms > 0 && now_ms >= ctx.timer_deadline_ms) {
        ctx.timer_deadline_ms = 0;
        dispatch(ctx, Event::TIMER_EXPIRED);
    }
}

}  // namespace SISP
