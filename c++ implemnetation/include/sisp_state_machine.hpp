#pragma once

#include "sisp_protocol.hpp"
#include "sisp_correction.hpp"
#include <array>
#include <cstdint>

namespace SISP {

/* ■■ State Enums (Section 7.1) ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

enum class State : uint8_t {
    IDLE = 0,
    
    // Service 1: Correction requester side
    CORR_WAIT_RSP = 1,
    CORR_COLLECTING = 2,
    CORR_COMPUTING = 3,
    CORR_DONE = 4,
    
    // Service 1: Correction responder side
    CORR_RESPONDING = 5,
    
    // Service 2: Relay requester side
    RELAY_WAIT_ACCEPT = 6,
    RELAY_SENDING = 7,
    RELAY_WAIT_ACK = 8,
    RELAY_DONE = 9,
    
    // Service 2: Relay provider side
    RELAY_RECEIVING = 10,
    RELAY_STORING = 11,
    RELAY_DOWNLINKING = 12,
    
    // Service 3: Borrow requester side
    BORROW_WAIT_ACCEPT = 13,
    BORROW_RECEIVING = 14,
    BORROW_DONE = 15,
    
    // Service 3: Borrow provider side
    BORROW_SAMPLING = 16,
    BORROW_SENDING = 17,
    
    // Error / Failure
    TIMEOUT = 18,
    ERROR = 19,
    CRITICAL_FAIL = 20,
    
    STATE_COUNT = 21
};

enum class Event : uint8_t {
    // Packet received events
    RX_CORRECTION_REQ = 0,
    RX_CORRECTION_RSP = 1,
    RX_RELAY_REQ = 2,
    RX_RELAY_ACCEPT = 3,
    RX_RELAY_REJECT = 4,
    RX_DOWNLINK_DATA = 5,
    RX_DOWNLINK_ACK = 6,
    RX_STATUS_BROADCAST = 7,
    RX_HEARTBEAT = 8,
    RX_HEARTBEAT_ACK = 9,
    RX_BORROW_REQ = 10,
    RX_FAILURE = 11,
    
    // Internal / timer events
    FAULT_DETECTED = 12,
    TIMER_EXPIRED = 13,
    ENERGY_LOW = 14,
    GS_VISIBLE = 15,
    GS_LOST = 16,
    ALL_FRAGS_SENT = 17,
    ALL_FRAGS_RCVD = 18,
    SENSOR_READ_DONE = 19,
    CORRECTION_DONE = 20,
    CRITICAL_FAILURE = 21,
    RESET = 22,
    RX_BORROW_DECISION = 23,
    
    EVT_COUNT = 24
};

/* ■■ Transaction Context (Section 7.3) ■■■■■■■■■■■■■■■■■■■■■■■■■ */

struct Context {
    static constexpr uint16_t RELAY_BUFFER_CAPACITY = static_cast<uint16_t>(MAX_FRAGMENT_DATA * 32U);

    State state;
    uint8_t self_id;                               // local node id
    uint8_t peer_id;                               // who we're talking to
    uint8_t seq;                                   // current sequence #
    uint8_t out_seq;                               // dedicated outgoing sequence #
    uint8_t current_degr;                          // local node degradation score
    ServiceCode service;                           // which service
    uint32_t timer_deadline_ms;                    // absolute expiry time
    uint8_t retry_count;                           // retransmits so far
    uint8_t max_retries;                           // give up after this

    // Replay protection (30s sliding window)
    std::array<uint8_t, 256> last_seen_seq;        // last SEQ seen per sender
    std::array<uint32_t, 256> last_seen_ts;        // timestamp of last SEQ
    std::array<uint8_t, 256> last_seen_valid;      // 0/1 valid marker

    // Neighbour trust table (satellite ID -> most recent observed DEGR)
    std::array<uint8_t, 256> neighbour_degr;       // latest degr seen per sender
    std::array<uint32_t, 256> neighbour_last_seen; // timestamp of last packet per sender

    // General peer profile table (friendliness + capabilities/health metadata)
    std::array<uint8_t, 256> peer_friendly;         // 1=trusted/friendly, 0=unknown/untrusted
    std::array<uint8_t, 256> peer_sensor_mask;      // latest advertised sensor health bitmask
    std::array<uint8_t, 256> peer_energy_pct;       // latest advertised energy percentage
    
    // Correction-specific
    std::array<std::array<float, 3>, 8> rsp_readings;  // up to 8 neighbours
    std::array<uint32_t, 8> rsp_timestamps_ms;          // correction response timestamps
    std::array<float, 8> rsp_weights;
    uint8_t rsp_count;
    std::array<float, 3> corrected_value;
    CorrectionFilter* correction_filter;            // External correction algorithm
    CorrectionReq last_correction_req;
    CorrectionRsp last_correction_rsp;
    
    // Relay-specific
    std::array<uint8_t, RELAY_BUFFER_CAPACITY> relay_tx_storage;
    uint16_t relay_tx_len;
    std::array<uint8_t, RELAY_BUFFER_CAPACITY> relay_rx_storage;
    uint16_t relay_rx_len;
    uint8_t* relay_buf;
    uint16_t relay_buf_len;
    uint8_t frag_total;
    uint8_t frag_sent;
    uint32_t frag_rcvd_mask;
    RelayReq last_relay_req;
    RelayDecision last_relay_decision;
    DownlinkData last_downlink_data;
    
    // Borrow-specific
    SensorType borrow_sensor;
    uint16_t borrow_duration_s;
    BorrowReq last_borrow_req;
    BorrowDecision last_borrow_decision;

    // General-purpose payload snapshots
    Status last_status;
    Heartbeat last_heartbeat;
    Failure last_failure;
    
    // Failure tracking (avoid cascading critical failures)
    std::array<uint8_t, 256> known_failed;         // 1 if satellite ID is known to be failed
    uint8_t last_failed_satellite_id;              // most recent failed satellite
    
    Context() 
                : state(State::IDLE), self_id(0), peer_id(0), seq(0), out_seq(0), current_degr(0),
          service(ServiceCode::CORRECTION_REQ),
          timer_deadline_ms(0), retry_count(0), max_retries(3),
          rsp_count(0), correction_filter(nullptr), relay_tx_len(0), relay_rx_len(0), relay_buf(nullptr), relay_buf_len(0),
          frag_total(0), frag_sent(0), frag_rcvd_mask(0),
          borrow_sensor(SensorType::MAGNETOMETER), borrow_duration_s(0) {
            last_seen_seq.fill(0);
            last_seen_ts.fill(0);
            last_seen_valid.fill(0);
            neighbour_degr.fill(0);
            neighbour_last_seen.fill(0);
            peer_friendly.fill(0);
            peer_sensor_mask.fill(0);
            peer_energy_pct.fill(0);
        rsp_readings.fill({});
        rsp_timestamps_ms.fill(0);
        rsp_weights.fill(0.0f);
        corrected_value.fill(0.0f);
        relay_tx_storage.fill(0);
        relay_rx_storage.fill(0);
        last_correction_req = {};
        last_correction_rsp = {};
        last_relay_req = {};
        last_relay_decision = {};
        last_downlink_data = {};
        last_borrow_req = {};
        last_borrow_decision = {};
        last_status = {};
        last_heartbeat = {};
        last_failure = {};
        known_failed.fill(0);
        last_failed_satellite_id = 0;
    }
};

/* ■■ State Machine Dispatch ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

using ActionFn = void(*)(Context& ctx, const Packet* pkt);

struct Transition {
    State next_state;
    ActionFn action;
};

class StateMachine {
public:
    StateMachine() = default;
    ~StateMachine() = default;

    /**
     * Dispatch an event into the state machine.
     * 
     * @param ctx       State machine context
     * @param evt       Event to inject
     * @param pkt       Packet (if any, for RX events)
     */
    static void dispatch(Context& ctx, Event evt, const Packet* pkt = nullptr);

    /**
     * Initialize a fresh context.
     */
    static void init_context(Context& ctx, uint8_t my_id);

    /**
     * Set the correction filter for this context.
     * The protocol does not own the filter; caller retains ownership.
     * Can be called at any time to switch algorithms.
     */
    static void set_correction_filter(Context& ctx, CorrectionFilter* filter);

    /**
     * Timer tick — call every 100ms from main loop or RTOS task.
     */
    static void tick(Context& ctx, uint32_t now_ms);
};

}  // namespace SISP
