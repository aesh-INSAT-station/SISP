#include "sisp_state_machine.hpp"
#include "sisp_encoder.hpp"
#include "sisp_decoder.hpp"
#include "sisp_protocol.hpp"
#include <iostream>
#include <cstring>
#include <cassert>
#include <string>

using namespace SISP;

static int g_test_count = 0;
static int g_passed_count = 0;

#define ASSERT(cond, msg) \
    do { \
        g_test_count++; \
        if (!(cond)) { \
            std::cerr << "FAIL: " << msg << std::endl; \
        } else { \
            g_passed_count++; \
            std::cout << "PASS: " << msg << std::endl; \
        } \
    } while(0)

void test_correction_happy_path() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    ASSERT(ctx.state == State::IDLE, "Initial state is IDLE");

    // Inject fault detection event
    StateMachine::dispatch(ctx, Event::FAULT_DETECTED);
    ASSERT(ctx.state == State::CORR_WAIT_RSP, "Fault detected → CORR_WAIT_RSP");

    // Simulate 2 neighbour responses
    CorrectionRsp rsp1_payload{};
    rsp1_payload.sensor_type = SensorType::MAGNETOMETER;
    rsp1_payload.reading.x = 100.0f;
    rsp1_payload.reading.y = 200.0f;
    rsp1_payload.reading.z = 300.0f;
    rsp1_payload.reading.ts_ms = 10;

    Packet rsp1{};
    rsp1.header.svc = ServiceCode::CORRECTION_RSP;
    rsp1.header.sndr = 0x05;
    rsp1.header.rcvr = 0x03;
    rsp1.header.seq = 0x01;
    rsp1.header.degr = 2;
    rsp1.header.flags = FLAG_OFFGRID;
    serialize_payload(rsp1_payload, rsp1.payload.data(), MAX_PAYLOAD, rsp1.payload_len);

    StateMachine::dispatch(ctx, Event::RX_CORRECTION_RSP, &rsp1);
    ASSERT(ctx.state == State::CORR_COLLECTING, "Received first response → CORR_COLLECTING");

    CorrectionRsp rsp2_payload{};
    rsp2_payload.sensor_type = SensorType::MAGNETOMETER;
    rsp2_payload.reading.x = 110.0f;
    rsp2_payload.reading.y = 210.0f;
    rsp2_payload.reading.z = 310.0f;
    rsp2_payload.reading.ts_ms = 11;

    Packet rsp2{};
    rsp2.header.svc = ServiceCode::CORRECTION_RSP;
    rsp2.header.sndr = 0x06;
    rsp2.header.rcvr = 0x03;
    rsp2.header.seq = 0x02;
    rsp2.header.degr = 3;
    rsp2.header.flags = FLAG_OFFGRID;
    serialize_payload(rsp2_payload, rsp2.payload.data(), MAX_PAYLOAD, rsp2.payload_len);

    StateMachine::dispatch(ctx, Event::RX_CORRECTION_RSP, &rsp2);
    ASSERT(ctx.state == State::CORR_COLLECTING, "Collecting second response");

    // Advance time past collection window (5.1s > 5s timer)
    StateMachine::tick(ctx, 5100);
    ASSERT(ctx.state == State::CORR_COMPUTING, "Timer expired → CORR_COMPUTING");

    StateMachine::dispatch(ctx, Event::CORRECTION_DONE);
    ASSERT(ctx.state == State::IDLE, "Correction done → IDLE");

    ASSERT(ctx.rsp_count == 2, "Collected 2 responses");
    ASSERT(ctx.last_correction_rsp.reading.z == 310.0f, "Last correction response parsed");
    ASSERT(ctx.rsp_timestamps_ms[1] == 11, "Correction response timestamp buffered");
}

void test_timeout_no_neighbours() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    // Send CORRECTION_REQ
    StateMachine::dispatch(ctx, Event::FAULT_DETECTED);
    ASSERT(ctx.state == State::CORR_WAIT_RSP, "Sent CORRECTION_REQ");

    // Advance time 5s with no responses
    StateMachine::tick(ctx, 5100);
    ASSERT(ctx.state == State::CORR_COMPUTING, "Timer expired, no responses → CORR_COMPUTING");

    StateMachine::dispatch(ctx, Event::CORRECTION_DONE);
    ASSERT(ctx.state == State::IDLE, "Return to IDLE");
}

void test_heartbeat_in_any_state() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    // Send CORRECTION_REQ
    StateMachine::dispatch(ctx, Event::FAULT_DETECTED);
    ASSERT(ctx.state == State::CORR_WAIT_RSP, "Now in CORR_WAIT_RSP");

    // Receive HEARTBEAT (should still be in CORR_WAIT_RSP, action sends ACK)
    Heartbeat hb_payload{};
    hb_payload.energy_pct = 40;
    hb_payload.degr = 7;
    hb_payload.uptime_s = 100;

    Packet hb{};
    hb.header.svc = ServiceCode::HEARTBEAT;
    hb.header.sndr = 0x05;
    hb.header.rcvr = 0x03;
    serialize_payload(hb_payload, hb.payload.data(), MAX_PAYLOAD, hb.payload_len);

    StateMachine::dispatch(ctx, Event::RX_HEARTBEAT, &hb);
    ASSERT(ctx.state == State::CORR_WAIT_RSP, "HEARTBEAT doesn't change state");
    ASSERT(ctx.last_heartbeat.energy_pct == 40, "Heartbeat payload parsed");
}

void test_reset_from_any_state() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    StateMachine::dispatch(ctx, Event::FAULT_DETECTED);
    ASSERT(ctx.state == State::CORR_WAIT_RSP, "In CORR_WAIT_RSP");

    // Receive RESET event
    StateMachine::dispatch(ctx, Event::RESET);
    ASSERT(ctx.state == State::IDLE, "RESET → IDLE");
    ASSERT(ctx.timer_deadline_ms == 0, "Timer cleared");
    ASSERT(ctx.rsp_count == 0, "Response count cleared");
}

void test_relay_energy_low() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    ASSERT(ctx.state == State::IDLE, "Start in IDLE");

    StateMachine::dispatch(ctx, Event::ENERGY_LOW);
    ASSERT(ctx.state == State::RELAY_WAIT_ACCEPT, "Energy low → RELAY_WAIT_ACCEPT");
    ASSERT(ctx.timer_deadline_ms == 10000, "10s relay timeout set");
}

void test_relay_provider_side() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    RelayReq relay_req{};
    relay_req.hop_count = 1;
    relay_req.fragment_count = 4;
    relay_req.window_s = 60;

    Packet relay_pkt{};
    relay_pkt.header.svc = ServiceCode::RELAY_REQ;
    relay_pkt.header.sndr = 0x09;
    relay_pkt.header.rcvr = 0x03;
    relay_pkt.header.flags = FLAG_OFFGRID;
    serialize_payload(relay_req, relay_pkt.payload.data(), MAX_PAYLOAD, relay_pkt.payload_len);

    StateMachine::dispatch(ctx, Event::RX_RELAY_REQ, &relay_pkt);
    ASSERT(ctx.state == State::RELAY_RECEIVING, "Relay request moves to provider side");
    ASSERT(ctx.last_relay_req.fragment_count == 4, "Relay request parsed");
}

void test_borrow_transition() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);

    BorrowReq borrow_req{};
    borrow_req.sensor_type = SensorType::SUN_SENSOR;
    borrow_req.duration_s = 120;
    borrow_req.priority = 1;

    Packet borrow_pkt{};
    borrow_pkt.header.svc = ServiceCode::BORROW_REQ;
    borrow_pkt.header.sndr = 0x0A;
    borrow_pkt.header.rcvr = 0x03;
    borrow_pkt.header.flags = FLAG_OFFGRID;
    serialize_payload(borrow_req, borrow_pkt.payload.data(), MAX_PAYLOAD, borrow_pkt.payload_len);

    StateMachine::dispatch(ctx, Event::RX_BORROW_REQ, &borrow_pkt);
    ASSERT(ctx.state == State::BORROW_SAMPLING, "Borrow request enters sampling state");
    ASSERT(ctx.borrow_duration_s == 120, "Borrow request parsed");
    ASSERT(ctx.peer_id == 0x0A, "Borrow requester peer tracked");
    ASSERT(ctx.last_borrow_decision.accepted == 1, "Borrow decision prepared on request receipt");
}

void test_borrow_decision_transition() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);
    ctx.state = State::BORROW_WAIT_ACCEPT;

    BorrowDecision decision{};
    decision.accepted = 1;
    decision.duration_s = 240;

    Packet decision_pkt{};
    decision_pkt.header.svc = ServiceCode::BORROW_DECISION;
    decision_pkt.header.sndr = 0x0A;
    decision_pkt.header.rcvr = 0x03;
    decision_pkt.header.flags = FLAG_OFFGRID;
    serialize_payload(decision, decision_pkt.payload.data(), MAX_PAYLOAD, decision_pkt.payload_len);

    StateMachine::dispatch(ctx, Event::RX_BORROW_DECISION, &decision_pkt);
    ASSERT(ctx.state == State::BORROW_RECEIVING, "Borrow decision moves requester to receiving state");
    ASSERT(ctx.last_borrow_decision.accepted == 1, "Borrow decision parsed");
    ASSERT(ctx.borrow_duration_s == 240, "Borrow decision duration stored");
}

void test_full_message_recovery_out_of_order_fragments() {
    Context ctx{};
    StateMachine::init_context(ctx, 0x03);
    ctx.state = State::BORROW_RECEIVING;

    constexpr uint16_t kFragCount = 3;
    constexpr uint16_t kFragSize = MAX_FRAGMENT_DATA;
    constexpr uint16_t kTotalLen = static_cast<uint16_t>(kFragCount * kFragSize);

    std::array<uint8_t, kTotalLen> expected{};
    for (uint16_t i = 0; i < kTotalLen; ++i) {
        expected[i] = static_cast<uint8_t>((i * 13U + 7U) & 0xFFU);
    }

    auto send_fragment = [&](uint16_t fragment_index, uint8_t seq) {
        DownlinkData data{};
        data.fragment_index = fragment_index;
        data.fragment_total = kFragCount;
        data.data_len = kFragSize;
        std::memcpy(data.data.data(), expected.data() + (fragment_index * kFragSize), kFragSize);

        Packet pkt{};
        pkt.header.svc = ServiceCode::DOWNLINK_DATA;
        pkt.header.sndr = 0x0A;
        pkt.header.rcvr = 0x03;
        pkt.header.seq = seq;
        pkt.header.degr = 2;
        pkt.header.flags = FLAG_OFFGRID;
        serialize_payload(data, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);

        StateMachine::dispatch(ctx, Event::RX_DOWNLINK_DATA, &pkt);
        ASSERT(ctx.state == State::BORROW_RECEIVING,
               "Out-of-order fragment processing keeps BORROW_RECEIVING state");
    };

    // Out-of-order delivery with a duplicate: 2, 0, 1, 1.
    send_fragment(2, 13);
    send_fragment(0, 11);
    send_fragment(1, 12);
    send_fragment(1, 14);

    ASSERT((ctx.frag_rcvd_mask & 0x7u) == 0x7u,
           "Fragment bitmask tracks all required fragments despite out-of-order delivery");
    ASSERT(ctx.relay_rx_len == kTotalLen,
           "Recovered message length matches full multi-fragment payload");
    ASSERT(std::memcmp(ctx.relay_rx_storage.data(), expected.data(), kTotalLen) == 0,
           "Recovered message bytes match expected payload after sequencing recovery");
}

int test_state_machine() {
    g_test_count = 0;
    g_passed_count = 0;

    test_correction_happy_path();
    test_timeout_no_neighbours();
    test_heartbeat_in_any_state();
    test_reset_from_any_state();
    test_relay_energy_low();
    test_relay_provider_side();
    test_borrow_transition();
    test_borrow_decision_transition();
    test_full_message_recovery_out_of_order_fragments();

    std::cout << "State Machine: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
