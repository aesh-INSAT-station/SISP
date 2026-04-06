#include "sisp_state_machine.hpp"
#include <cstring>

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
static void action_reset(Context& ctx, const Packet* pkt);

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
    g_trans[s][static_cast<size_t>(Event::CRITICAL_FAILURE)] = { State::CRITICAL_FAIL, action_idle_nop };
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

    g_trans_initialized = true;
}

static void action_idle_nop(Context&, const Packet*) {
}

static void action_send_correction_req(Context& ctx, const Packet*) {
    ctx.service = ServiceCode::CORRECTION_REQ;
    ctx.timer_deadline_ms = 5000;
    ctx.rsp_count = 0;
}

static void action_send_correction_rsp(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;
    CorrectionReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_correction_req = req;
        ctx.borrow_sensor = req.sensor_type;
        ctx.borrow_duration_s = req.window_s;
    }
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
    ctx.rsp_weights[ctx.rsp_count] = 1.0f;
    ctx.rsp_count++;
}

static void action_run_kalman(Context&, const Packet*) {
}

static void action_send_relay_req(Context& ctx, const Packet*) {
    ctx.service = ServiceCode::RELAY_REQ;
    ctx.timer_deadline_ms = 10000;
}

static void action_send_relay_accept(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    ctx.peer_id = pkt->header.sndr;
    RelayReq req{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, req) == ErrorCode::OK) {
        ctx.last_relay_req = req;
    }
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
}

static void action_store_frag(Context& ctx, const Packet* pkt) {
    if (!pkt) {
        return;
    }
    DownlinkData data{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, data) == ErrorCode::OK) {
        ctx.last_downlink_data = data;
    }
}

static void action_send_frag(Context&, const Packet*) {
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

static void action_send_borrow_data(Context&, const Packet*) {
}

static void action_send_ack(Context& ctx, const Packet* pkt) {
    (void)ctx;
    if (!pkt) {
        return;
    }
    DownlinkAck ack{};
    if (deserialize_payload(pkt->payload.data(), pkt->payload_len, ack) == ErrorCode::OK) {
        (void)ack;
    }
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

void StateMachine::tick(Context& ctx, uint32_t now_ms) {
    if (ctx.timer_deadline_ms > 0 && now_ms >= ctx.timer_deadline_ms) {
        ctx.timer_deadline_ms = 0;
        dispatch(ctx, Event::TIMER_EXPIRED);
    }
}

}  // namespace SISP
