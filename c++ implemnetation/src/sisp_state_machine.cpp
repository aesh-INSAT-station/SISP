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
static void action_receive_borrow_req(Context& ctx, const Packet* pkt);
static void action_send_borrow_data(Context& ctx, const Packet* pkt);
static void action_send_ack(Context& ctx, const Packet* pkt);
static void action_broadcast_failure(Context& ctx, const Packet* pkt);
static void action_reset(Context& ctx, const Packet* pkt);

static void transmit_packet(const Packet& pkt, uint8_t dst, const TransportMeta& meta) {
    uint8_t frame[FRAME_SIZE];
    if (Encoder::encode_frame(pkt, meta, frame) != ErrorCode::OK) {
        return;
    }
    sim_transmit_packet(dst, frame, FRAME_SIZE);
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
    g_trans[s][static_cast<size_t>(Event::ENERGY_LOW)] = { State::RELAY_WAIT_ACCEPT, action_send_relay_req };
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
    g_trans[s][static_cast<size_t>(Event::RX_RELAY_REJECT)] = { State::IDLE, action_send_relay_reject };
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
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_RCVD)] = { State::RELAY_DOWNLINKING, action_store_frag };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::RELAY_DOWNLINKING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::IDLE, action_send_ack };

    s = static_cast<size_t>(State::BORROW_SAMPLING);
    g_trans[s][static_cast<size_t>(Event::SENSOR_READ_DONE)] = { State::BORROW_SENDING, action_send_borrow_data };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    s = static_cast<size_t>(State::BORROW_SENDING);
    g_trans[s][static_cast<size_t>(Event::ALL_FRAGS_SENT)] = { State::BORROW_DONE, action_send_borrow_data };
    g_trans[s][static_cast<size_t>(Event::RESET)] = { State::IDLE, action_reset };

    for (size_t state_index = 0; state_index < static_cast<size_t>(State::STATE_COUNT); ++state_index) {
        g_trans[state_index][static_cast<size_t>(Event::CRITICAL_FAILURE)] = { State::CRITICAL_FAIL, action_broadcast_failure };
        g_trans[state_index][static_cast<size_t>(Event::RX_FAILURE)] = { State::CRITICAL_FAIL, action_broadcast_failure };
    }

    g_trans_initialized = true;
}

static void action_idle_nop(Context&, const Packet*) {
}

static void action_send_correction_req(Context& ctx, const Packet*) {
    ctx.service = ServiceCode::CORRECTION_REQ;
    ctx.timer_deadline_ms = 5000;
    ctx.rsp_count = 0;

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
    transmit_packet(out, BCAST_ADDR, meta);
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
    rsp.reading = ctx.last_correction_rsp.reading;
    serialize_payload(rsp, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.session_id = static_cast<uint16_t>(ctx.out_seq);
    meta.ack_seq = pkt->header.seq;
    meta.window = 1;
    transmit_packet(out, pkt->header.sndr, meta);
}

static void action_collect_rsp(Context& ctx, const Packet* pkt) {
    if (!pkt || ctx.rsp_count >= 8) {
        return;
    }

    CorrectionRsp rsp{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, rsp) != ErrorCode::OK) {
        return;
    }

    ctx.last_correction_rsp = rsp;
    ctx.rsp_readings[ctx.rsp_count][0] = rsp.reading.x;
    ctx.rsp_readings[ctx.rsp_count][1] = rsp.reading.y;
    ctx.rsp_readings[ctx.rsp_count][2] = rsp.reading.z;
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
    ctx.service = ServiceCode::RELAY_REQ;
    ctx.timer_deadline_ms = 10000;

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
    transmit_packet(out, BCAST_ADDR, meta);
}

static void action_send_relay_accept(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;

    RelayReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_relay_req = req;
        ctx.frag_total = static_cast<uint8_t>(req.fragment_count);
        ctx.frag_sent = 0;
        ctx.frag_rcvd_mask = 0;
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
    transmit_packet(out, pkt->header.sndr, meta);
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
    transmit_packet(out, pkt->header.sndr, meta);
}

static void action_store_frag(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    DownlinkData data{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, data) == ErrorCode::OK) {
        ctx.last_downlink_data = data;
        if (data.fragment_index < 32U) {
            ctx.frag_rcvd_mask |= (1u << data.fragment_index);
        }

        if (data.fragment_total > 0U) {
            uint32_t expected = (data.fragment_total >= 32U) ? 0xFFFFFFFFu : ((1u << data.fragment_total) - 1u);
            if ((ctx.frag_rcvd_mask & expected) == expected) {
                StateMachine::dispatch(ctx, Event::ALL_FRAGS_RCVD, nullptr);
            }
        }
    }
}

static void action_send_frag(Context& ctx, const Packet* pkt) {
    (void)pkt;

    uint16_t offset = static_cast<uint16_t>(ctx.frag_sent) * MAX_FRAGMENT_DATA;
    if (ctx.relay_buf && ctx.relay_buf_len > 0 && offset < ctx.relay_buf_len) {
        uint16_t remaining = static_cast<uint16_t>(ctx.relay_buf_len - offset);
        uint16_t chunk_len = std::min<uint16_t>(remaining, MAX_FRAGMENT_DATA);

        Packet out{};
        out.header.svc = ServiceCode::DOWNLINK_DATA;
        out.header.sndr = ctx.self_id;
        out.header.rcvr = ctx.peer_id;
        out.header.seq = ++ctx.out_seq;
        ctx.seq = ctx.out_seq;
        out.header.degr = ctx.current_degr;
        out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);

        DownlinkData data{};
        data.fragment_index = ctx.frag_sent;
        data.fragment_total = ctx.frag_total;
        data.data_len = chunk_len;
        std::memcpy(data.data.data(), ctx.relay_buf + offset, chunk_len);
        serialize_payload(data, out.payload.data(), MAX_PAYLOAD, out.payload_len);

        TransportMeta meta{};
        meta.datagram_tag = 6;
        meta.hop_limit = 8;
        meta.relay_hops_remaining = 3;
        meta.relay_path_id = 1;
        transmit_packet(out, ctx.peer_id, meta);

        ++ctx.frag_sent;
        return;
    }

    Packet out{};
    out.header.svc = ServiceCode::DOWNLINK_DATA;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = ctx.peer_id;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);

    DownlinkData data{};
    data.fragment_index = ctx.frag_sent;
    data.fragment_total = ctx.frag_total;
    data.data_len = 0;
    serialize_payload(data, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 6;
    meta.hop_limit = 8;
    meta.relay_hops_remaining = 3;
    meta.relay_path_id = 1;
    transmit_packet(out, ctx.peer_id, meta);
}

static void action_store_status(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    Status status{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, status) == ErrorCode::OK) {
        ctx.last_status = status;
    }
}

static void action_store_heartbeat(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    Heartbeat heartbeat{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, heartbeat) == ErrorCode::OK) {
        ctx.last_heartbeat = heartbeat;
    }
}

static void action_receive_borrow_req(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    BorrowReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_borrow_req = req;
        ctx.borrow_sensor = req.sensor_type;
        ctx.borrow_duration_s = req.duration_s;
    }
}

static void action_send_borrow_data(Context& ctx, const Packet* pkt) {
    Packet out{};
    out.header.svc = ServiceCode::BORROW_REQ;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = pkt ? pkt->header.sndr : ctx.peer_id;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    BorrowDecision decision{};
    decision.accepted = 1;
    decision.duration_s = ctx.borrow_duration_s;
    serialize_payload(decision, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 7;
    meta.hop_limit = 1;
    transmit_packet(out, out.header.rcvr, meta);
}

static void action_send_ack(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }

    Packet out{};
    out.header.svc = ServiceCode::DOWNLINK_ACK;
    out.header.sndr = ctx.self_id;
    out.header.rcvr = pkt->header.sndr;
    out.header.seq = ++ctx.out_seq;
    ctx.seq = ctx.out_seq;
    out.header.degr = ctx.current_degr;
    out.header.flags = FLAG_OFFGRID;

    DownlinkAck ack{};
    ack.crc32 = static_cast<uint32_t>(pkt->header.seq) | (static_cast<uint32_t>(ctx.frag_sent) << 8);
    serialize_payload(ack, out.payload.data(), MAX_PAYLOAD, out.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 8;
    meta.hop_limit = 1;
    transmit_packet(out, pkt->header.sndr, meta);
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
    transmit_packet(out, BCAST_ADDR, meta);
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
