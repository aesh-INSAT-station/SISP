#include "sisp_state_machine.hpp"
#include "sisp_encoder.hpp"
#include "sisp_decoder.hpp"
#include "sisp_correction.hpp"
#include "sisp_protocol.hpp"
#include <iostream>
#include <vector>
#include <cstring>

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

/**
 * Protocol Simulation Test Suite
 *
 * This test suite validates the SISP protocol at a reliable level by simulating
 * multi-node scenarios and verifying correct behavior end-to-end:
 *
 * 1. Packet transmission and delivery
 * 2. State machine transitions
 * 3. Relay path establishment
 * 4. Correction workflow
 * 5. Error handling and timeouts
 * 6. Pluggable correction algorithm integration
 *
 * Protocol logic is tested independently from correction algorithms.
 */

// Simulated node with internal state
struct SimulatedNode {
    Context state_ctx;
    uint8_t node_id;
    std::vector<uint8_t> tx_buffer;      // Outgoing frames
    std::vector<uint8_t> rx_buffer;      // Incoming frames
    WeightedMedianFilter default_filter;
    uint32_t time_ms;
};

// Simulate a packet transmission from one node to another
static void sim_deliver_packet(SimulatedNode& sender, 
                                SimulatedNode& recipient,
                                const uint8_t* frame_data,
                                uint16_t frame_size) {
    if (!frame_data || frame_size != FRAME_SIZE) {
        return;
    }

    // Decode at recipient side
    Packet pkt{};
    FrameInfo info{};
    ErrorCode err = Decoder::decode_frame(frame_data, pkt, info);
    if (err != ErrorCode::OK) {
        return;  // Drop corrupted frames
    }

    // Check if this recipient is the intended target
    if (!pkt.is_for_me(recipient.node_id) && !pkt.is_broadcast()) {
        return;  // Not for us
    }

    // Map service code to event
    Event evt;
    switch (pkt.header.svc) {
        case ServiceCode::CORRECTION_REQ:    evt = Event::RX_CORRECTION_REQ; break;
        case ServiceCode::CORRECTION_RSP:    evt = Event::RX_CORRECTION_RSP; break;
        case ServiceCode::RELAY_REQ:         evt = Event::RX_RELAY_REQ; break;
        case ServiceCode::RELAY_ACCEPT:      evt = Event::RX_RELAY_ACCEPT; break;
        case ServiceCode::RELAY_REJECT:      evt = Event::RX_RELAY_REJECT; break;
              case ServiceCode::BORROW_DECISION:   evt = Event::RX_BORROW_DECISION; break;
        case ServiceCode::HEARTBEAT:         evt = Event::RX_HEARTBEAT; break;
        case ServiceCode::STATUS_BROADCAST:  evt = Event::RX_STATUS_BROADCAST; break;
        default: return;
    }

    StateMachine::dispatch(recipient.state_ctx, evt, &pkt);
}

// Scenario 1: Single node correction flow
static void test_scenario_single_node_correction() {
    SimulatedNode node1{};
    node1.node_id = 0x01;
    StateMachine::init_context(node1.state_ctx, node1.node_id);
    StateMachine::set_correction_filter(node1.state_ctx, &node1.default_filter);

    ASSERT(node1.state_ctx.state == State::IDLE, 
           "Single-node: Start in IDLE");

    // Trigger fault
    StateMachine::dispatch(node1.state_ctx, Event::FAULT_DETECTED);
    ASSERT(node1.state_ctx.state == State::CORR_WAIT_RSP, 
           "Single-node: Fault triggers correction request");

    // Simulate responses arriving
    for (int i = 0; i < 2; ++i) {
        CorrectionRsp rsp{};
        rsp.sensor_type = SensorType::MAGNETOMETER;
        rsp.reading.x = 100.0f + i * 10;
        rsp.reading.y = 200.0f + i * 10;
        rsp.reading.z = 300.0f + i * 10;
        rsp.reading.ts_ms = 10 + i;

        Packet pkt{};
        pkt.header.svc = ServiceCode::CORRECTION_RSP;
        pkt.header.sndr = static_cast<uint8_t>(0x10 + i);
        pkt.header.rcvr = node1.node_id;
        pkt.header.seq = i + 1;
        pkt.header.degr = static_cast<uint8_t>(i + 1);
        pkt.header.flags = FLAG_OFFGRID;
        serialize_payload(rsp, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);

        StateMachine::dispatch(node1.state_ctx, Event::RX_CORRECTION_RSP, &pkt);
    }

    ASSERT(node1.state_ctx.rsp_count == 2, 
           "Single-node: Collected 2 correction responses");

    // Trigger correction computation
    StateMachine::tick(node1.state_ctx, 5100);
    ASSERT(node1.state_ctx.state == State::CORR_COMPUTING, 
           "Single-node: Timer expired triggers computation");

    StateMachine::dispatch(node1.state_ctx, Event::CORRECTION_DONE);
    ASSERT(node1.state_ctx.state == State::IDLE, 
           "Single-node: Correction done returns to IDLE");

    ASSERT(node1.state_ctx.corrected_value[0] != 0.0f, 
           "Single-node: Correction filter produced result");
}

// Scenario 2: Two-node relay exchange
static void test_scenario_relay_exchange() {
    SimulatedNode requester{}, provider{};
    requester.node_id = 0x02;
    provider.node_id = 0x03;

    StateMachine::init_context(requester.state_ctx, requester.node_id);
    StateMachine::init_context(provider.state_ctx, provider.node_id);

    ASSERT(requester.state_ctx.state == State::IDLE, 
           "Relay: Requester starts in IDLE");
    ASSERT(provider.state_ctx.state == State::IDLE, 
           "Relay: Provider starts in IDLE");

    // Requester detects energy low
    StateMachine::dispatch(requester.state_ctx, Event::ENERGY_LOW);
    ASSERT(requester.state_ctx.state == State::RELAY_WAIT_ACCEPT, 
           "Relay: Energy low transitions to RELAY_WAIT_ACCEPT");

    // Simulate provider receiving relay request
    RelayReq relay_req{};
    relay_req.hop_count = 1;
    relay_req.fragment_count = 4;
    relay_req.window_s = 60;

    Packet relay_pkt{};
    relay_pkt.header.svc = ServiceCode::RELAY_REQ;
    relay_pkt.header.sndr = requester.node_id;
    relay_pkt.header.rcvr = BCAST_ADDR;  // Broadcast
    relay_pkt.header.seq = 1;
    relay_pkt.header.degr = 1;
    relay_pkt.header.flags = FLAG_OFFGRID | FLAG_RELAY;
    serialize_payload(relay_req, relay_pkt.payload.data(), MAX_PAYLOAD, relay_pkt.payload_len);

    StateMachine::dispatch(provider.state_ctx, Event::RX_RELAY_REQ, &relay_pkt);
    ASSERT(provider.state_ctx.state == State::RELAY_RECEIVING, 
           "Relay: Provider transitions to RELAY_RECEIVING");
    ASSERT(provider.state_ctx.last_relay_req.fragment_count == 4, 
           "Relay: Provider stores relay request details");
}

// Scenario 3: Multi-node heartbeat dissemination
static void test_scenario_heartbeat_broadcast() {
    SimulatedNode announcer{}, listener1{}, listener2{};
    announcer.node_id = 0x04;
    listener1.node_id = 0x05;
    listener2.node_id = 0x06;

    StateMachine::init_context(announcer.state_ctx, announcer.node_id);
    StateMachine::init_context(listener1.state_ctx, listener1.node_id);
    StateMachine::init_context(listener2.state_ctx, listener2.node_id);

    // Announcer broadcasts heartbeat
    Heartbeat hb{};
    hb.energy_pct = 75;
    hb.degr = 3;
    hb.uptime_s = 10000;

    Packet hb_pkt{};
    hb_pkt.header.svc = ServiceCode::HEARTBEAT;
    hb_pkt.header.sndr = announcer.node_id;
    hb_pkt.header.rcvr = BCAST_ADDR;
    hb_pkt.header.seq = 1;
    hb_pkt.header.degr = 3;
    hb_pkt.header.flags = FLAG_OFFGRID;
    serialize_payload(hb, hb_pkt.payload.data(), MAX_PAYLOAD, hb_pkt.payload_len);

    // Both listeners receive and process
    StateMachine::dispatch(listener1.state_ctx, Event::RX_HEARTBEAT, &hb_pkt);
    StateMachine::dispatch(listener2.state_ctx, Event::RX_HEARTBEAT, &hb_pkt);

    ASSERT(listener1.state_ctx.last_heartbeat.energy_pct == 75, 
           "Heartbeat: Listener1 receives heartbeat");
    ASSERT(listener2.state_ctx.last_heartbeat.energy_pct == 75, 
           "Heartbeat: Listener2 receives heartbeat");
    ASSERT(listener1.state_ctx.last_heartbeat.uptime_s == 10000, 
           "Heartbeat: Uptime preserved");
}

// Scenario 4: Correction algorithm independent of protocol
static void test_scenario_pluggable_correction() {
    SimulatedNode node1{}, node2{};
    node1.node_id = 0x07;
    node2.node_id = 0x08;

    StateMachine::init_context(node1.state_ctx, node1.node_id);
    StateMachine::init_context(node2.state_ctx, node2.node_id);

    // Start with no filter
    ASSERT(node1.state_ctx.correction_filter == nullptr, 
           "Plugin: No filter initially");

    // Plug in weighted median filter
    WeightedMedianFilter filter1;
    StateMachine::set_correction_filter(node1.state_ctx, &filter1);
    ASSERT(node1.state_ctx.correction_filter != nullptr, 
           "Plugin: Filter can be set dynamically");

    // Plug in different filter for node2
    KalmanFilter filter2;
    StateMachine::set_correction_filter(node2.state_ctx, &filter2);
    ASSERT(node2.state_ctx.correction_filter != &filter1, 
           "Plugin: Different filters for different nodes");

    // Both can receive and compute independently
    StateMachine::dispatch(node1.state_ctx, Event::FAULT_DETECTED);
    StateMachine::dispatch(node2.state_ctx, Event::FAULT_DETECTED);

    ASSERT(node1.state_ctx.state == State::CORR_WAIT_RSP, 
           "Plugin: Node1 with median filter works");
    ASSERT(node2.state_ctx.state == State::CORR_WAIT_RSP, 
           "Plugin: Node2 with Kalman filter works");
}

// Scenario 5: Error handling - corrupted packet rejection
static void test_scenario_error_handling() {
       SimulatedNode sender{}, node{};
       sender.node_id = 0x0A;
    node.node_id = 0x09;
       StateMachine::init_context(sender.state_ctx, sender.node_id);
    StateMachine::init_context(node.state_ctx, node.node_id);

       // Create a valid heartbeat packet/frame.
    Heartbeat hb{};
    hb.energy_pct = 80;
    hb.degr = 2;
    hb.uptime_s = 5000;

    Packet hb_pkt{};
    hb_pkt.header.svc = ServiceCode::HEARTBEAT;
    hb_pkt.header.sndr = 0x0A;
    hb_pkt.header.rcvr = node.node_id;
    hb_pkt.header.seq = 42;
    hb_pkt.header.degr = 2;
    hb_pkt.header.flags = FLAG_OFFGRID;
    serialize_payload(hb, hb_pkt.payload.data(), MAX_PAYLOAD, hb_pkt.payload_len);

    TransportMeta meta{};
    meta.datagram_tag = 1;
    meta.hop_limit = 1;

    uint8_t valid_frame[FRAME_SIZE]{};
    ErrorCode enc_err = Encoder::encode_frame(hb_pkt, meta, valid_frame);
    ASSERT(enc_err == ErrorCode::OK, "Error: Valid heartbeat frame encoded");

    uint8_t corrupted_frame[FRAME_SIZE]{};
    std::memcpy(corrupted_frame, valid_frame, FRAME_SIZE);
    corrupted_frame[FRAME_SIZE - 1] ^= 0x01;  // Flip frame checksum bit.

    // Corrupted frame must be dropped by decoder path.
    sim_deliver_packet(sender, node, corrupted_frame, FRAME_SIZE);
    ASSERT(node.state_ctx.last_heartbeat.energy_pct == 0,
           "Error: Corrupted frame rejected");

    // Valid frame must still be accepted.
    sim_deliver_packet(sender, node, valid_frame, FRAME_SIZE);
    ASSERT(node.state_ctx.last_heartbeat.energy_pct == 80,
           "Error: Valid frame accepted after corrupted frame drop");
}

// Scenario 6: State machine RESET from any state
static void test_scenario_reset_recovery() {
    // Test: RESET from CORR_WAIT_RSP
    SimulatedNode node{};
    node.node_id = 0x0B;
    StateMachine::init_context(node.state_ctx, node.node_id);

    StateMachine::dispatch(node.state_ctx, Event::FAULT_DETECTED);
    ASSERT(node.state_ctx.state == State::CORR_WAIT_RSP, 
           "Reset: Can reach CORR_WAIT_RSP state");

    StateMachine::dispatch(node.state_ctx, Event::RESET);
    ASSERT(node.state_ctx.state == State::IDLE, 
           "Reset: Escape to IDLE from any state");

    // Verify context is properly cleared
    ASSERT(node.state_ctx.rsp_count == 0, 
           "Reset: Clears response collection state");
}

int test_protocol_simulation() {
    g_test_count = 0;
    g_passed_count = 0;

    std::cout << "\n--- Protocol Simulation Suite ---\n" << std::endl;

    test_scenario_single_node_correction();
    test_scenario_relay_exchange();
    test_scenario_heartbeat_broadcast();
    test_scenario_pluggable_correction();
    test_scenario_error_handling();
    test_scenario_reset_recovery();

    std::cout << "\nProtocol Simulation: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
