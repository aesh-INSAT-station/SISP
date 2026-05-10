#pragma once

#include <cstdint>
#include <cstring>
#include <array>
#include <cmath>

/* ============================================================================
 * SISP Protocol: Satellite Inter-Service Protocol
 * Version 1.0 — C++ Implementation
 * 
 * Core types, constants, and packet structures per spec Section 5 & 2.2
 * =========================================================================== */

namespace SISP {

/* ■■ Version ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
static constexpr uint8_t VERSION = 1;
static constexpr uint16_t MAX_PACKET = 128;       // bytes, max total packet size
static constexpr uint8_t FRAME_SIZE = 64;         // bytes, fixed 512-bit frame
static constexpr uint8_t HEADER_SIZE = 5;         // bytes, fixed header
static constexpr uint8_t SEC_PREFIX = 16;         // bytes, security prefix
static constexpr uint16_t MAX_PAYLOAD = 107;      // = 128 - 5 - 16
static constexpr uint8_t BCAST_ADDR = 0xFF;       // broadcast to all neighbours
static constexpr uint8_t GROUND_ADDR = 0x00;      // ground station address

/* ■■ Service Codes (SVC Field) ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
enum class ServiceCode : uint8_t {
    CORRECTION_REQ = 0x0,
    CORRECTION_RSP = 0x1,
    RELAY_REQ = 0x2,
    RELAY_ACCEPT = 0x3,
    RELAY_REJECT = 0x4,
    DOWNLINK_DATA = 0x5,
    DOWNLINK_ACK = 0x6,
    STATUS_BROADCAST = 0x7,
    HEARTBEAT = 0x8,
    HEARTBEAT_ACK = 0x9,
    BORROW_DECISION = 0xA,
    RESERVED_B = 0xB,
    RESERVED_C = 0xC,
    RESERVED_D = 0xD,
    BORROW_REQ = 0xE,
    FAILURE = 0xF,
};

/* ■■ Sensor Types ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
enum class SensorType : uint8_t {
    MAGNETOMETER = 0x01,      // 3-axis, nT
    SUN_SENSOR = 0x02,        // 6-face photodiodes
    GYROSCOPE = 0x03,         // 3-axis, deg/s
    STAR_TRACKER = 0x04,      // quaternion
    THERMAL = 0x05,           // surface temp, K
    OPTICAL = 0x06,           // radiance, W/m2/sr
};

enum class PhyProfile : uint8_t {
    CONTROL_437_NARROW = 0x00,  // 10/12.5 kHz-class always-on control PHY
    BULK_437_WIDE = 0x01,       // 20/25 kHz-class emergency/bulk PHY
};

static constexpr uint8_t PHY_CAP_CONTROL_437_NARROW = (1 << 0);
static constexpr uint8_t PHY_CAP_BULK_437_WIDE = (1 << 1);
static constexpr uint8_t PHY_CAP_DEFAULT = PHY_CAP_CONTROL_437_NARROW | PHY_CAP_BULK_437_WIDE;

static constexpr uint8_t SENSOR_MASK_MAGNETOMETER = (1 << 0);
static constexpr uint8_t SENSOR_MASK_SUN_SENSOR = (1 << 1);
static constexpr uint8_t SENSOR_MASK_GYROSCOPE = (1 << 2);
static constexpr uint8_t SENSOR_MASK_STAR_TRACKER = (1 << 3);
static constexpr uint8_t SENSOR_MASK_THERMAL = (1 << 4);
static constexpr uint8_t SENSOR_MASK_OPTICAL = (1 << 5);
static constexpr uint8_t SENSOR_MASK_ALL = SENSOR_MASK_MAGNETOMETER | SENSOR_MASK_SUN_SENSOR |
                                           SENSOR_MASK_GYROSCOPE | SENSOR_MASK_STAR_TRACKER |
                                           SENSOR_MASK_THERMAL | SENSOR_MASK_OPTICAL;

/* ■■ FLAGS nibble bits ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
static constexpr uint8_t FLAG_OFFGRID = (1 << 3);  // 1=cross-op/public
static constexpr uint8_t FLAG_PROTO = (1 << 2);    // 1=TCP-like, ACK reqd
static constexpr uint8_t FLAG_RELAY = (1 << 1);    // 1=fwd permitted
static constexpr uint8_t FLAG_TMAX = (1 << 0);     // 1=time-critical
static constexpr uint16_t MAX_FRAGMENT_DATA = 101;  // 107 - 6 byte fragment envelope

/* ■■ Error Codes ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
enum class ErrorCode : int8_t {
    OK = 0,
    ERR_CKSM = -1,        // header checksum mismatch
    ERR_LEN = -2,         // packet too short/long
    ERR_RESERVED = -3,    // reserved SVC code
    ERR_ADDR = -4,        // wrong RCVR address
    ERR_DUP = -5,         // duplicate SEQ detected
};

/* ■■ Packed Header Structure ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
/* Bit layout (NOT using C++ bitfields due to platform portability):
 * Byte 0: [ SVC[3:0] | SNDR[7:4] ] <- high nibble = SVC, low = SNDR upper
 * Byte 1: [ SNDR[3:0] | RCVR[7:4] ] <- SNDR spans bytes 0-1
 * Byte 2: [ RCVR[3:0] | SEQ[7:4] ] <- RCVR spans bytes 1-2
 * Byte 3: [ SEQ[3:0] | DEGR[3:0] ]
 * Byte 4: [ FLAGS[3:0]| CKSM[3:0] ] <- CKSM computed last
 */
struct Header {
    ServiceCode svc;        // 4 bits
    uint8_t sndr;           // 8 bits
    uint8_t rcvr;           // 8 bits
    uint8_t seq;            // 8 bits
    uint8_t degr;           // 4 bits, 0-15
    uint8_t flags;          // 4 bits: OFFGRID|PROTO|RELAY|TMAX
    uint8_t cksm;           // 4 bits

    Header() 
        : svc(ServiceCode::CORRECTION_REQ), sndr(0), rcvr(0), seq(0), 
          degr(0), flags(0), cksm(0) {}
};

/* ■■ Payload Structs ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

struct Vec3Reading {
    float x, y, z;          // reading (units depend on sensor)
    uint32_t ts_ms;         // timestamp milliseconds since boot

    Vec3Reading() : x(0), y(0), z(0), ts_ms(0) {}
};

struct CorrectionReq {
    SensorType sensor_type;
    uint16_t window_s;      // contact window remaining, s
};

struct RelayReq {
    uint8_t hop_count;
    uint16_t fragment_count;
    uint16_t window_s;
};

struct RelayDecision {
    uint8_t accepted;
    uint8_t reason;
};

struct DownlinkData {
    uint16_t fragment_index;
    uint16_t fragment_total;
    uint16_t data_len;
    std::array<uint8_t, MAX_FRAGMENT_DATA> data;

    DownlinkData() : fragment_index(0), fragment_total(0), data_len(0) {
        data.fill(0);
    }
};

struct DownlinkAck {
    uint32_t crc32;
};

struct Heartbeat {
    uint8_t energy_pct;
    uint8_t degr;
    uint32_t uptime_s;
};

struct Failure {
    uint8_t code;
    uint8_t detail;
    uint8_t degr;
};

struct BorrowReq {
    SensorType sensor_type;
    uint16_t duration_s;
    uint8_t priority;
};

struct BorrowDecision {
    uint8_t accepted;
    uint16_t duration_s;
};

struct CorrectionRsp {
    SensorType sensor_type;
    Vec3Reading reading;
};

struct Status {
    uint8_t energy_pct;     // 0-100
    uint16_t ground_vis_s;  // seconds until next GS pass
    uint8_t sensor_mask;    // bitmask: bit=1 means healthy
    uint32_t uptime_s;
    uint8_t phy_cap_mask;   // bitmask of supported PhyProfile values
};

/* ■■ Full Packet Structure ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
struct Packet {
    Header header;
    std::array<uint8_t, MAX_PAYLOAD> payload;
    uint16_t payload_len;

    Packet() : payload_len(0) {
        payload.fill(0);
    }

    // Convenience check functions
    bool is_broadcast() const {
        return header.rcvr == BCAST_ADDR;
    }

    bool is_for_me(uint8_t my_id) const {
        return header.rcvr == my_id || header.rcvr == BCAST_ADDR;
    }

    bool has_security() const {
        return !(header.flags & FLAG_OFFGRID);
    }
};

/* ■■ Fixed 512-bit Frame Metadata ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
struct TransportMeta {
    uint16_t session_id;            // TCP-like session identifier
    uint8_t ack_seq;                // TCP-like ack sequence
    uint8_t window;                 // TCP-like advertised window
    uint8_t datagram_tag;           // UDP-like datagram tag
    uint8_t hop_limit;              // UDP-like hop limit
    uint8_t relay_hops_remaining;   // relay extension
    uint8_t relay_path_id;          // relay path identifier
    uint16_t tmax_deadline_ds;      // time critical deadline in deciseconds
    PhyProfile phy_profile;         // PHY used for this frame
    uint8_t phy_cap_mask;           // advertised local PHY support

    TransportMeta()
        : session_id(0), ack_seq(0), window(0), datagram_tag(0), hop_limit(0),
          relay_hops_remaining(0), relay_path_id(0), tmax_deadline_ds(0),
          phy_profile(PhyProfile::CONTROL_437_NARROW), phy_cap_mask(PHY_CAP_DEFAULT) {}
};

struct FrameInfo {
    uint8_t payload_len;
    uint8_t extension_len;
    TransportMeta transport;

    FrameInfo() : payload_len(0), extension_len(0), transport() {}
};

/* ■■ API Function Declarations ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

// Convert SVC enum to string name
const char* svc_name(ServiceCode svc);

// DEGR computation (Section 9)
uint8_t compute_degr(float k_factor, float svd_residual, 
                     uint32_t age_days, float orbit_error_m);

// CRC-8/MAXIM computation
uint8_t compute_crc8_maxim(const uint8_t* data, size_t len);

// 512-bit frame helpers
uint8_t compute_frame_checksum(const uint8_t* data, size_t len_without_checksum);
uint16_t compute_frame_extension_len(uint8_t flags);
uint16_t compute_frame_payload_capacity(uint8_t flags);
uint8_t sensor_mask_for(SensorType sensor);
uint8_t phy_cap_for(PhyProfile phy);

// Typed payload serialization helpers
ErrorCode serialize_payload(const CorrectionReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, CorrectionReq& dst);

ErrorCode serialize_payload(const RelayReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, RelayReq& dst);

ErrorCode serialize_payload(const RelayDecision& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, RelayDecision& dst);

ErrorCode serialize_payload(const CorrectionRsp& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, CorrectionRsp& dst);

ErrorCode serialize_payload(const DownlinkData& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, DownlinkData& dst);

ErrorCode serialize_payload(const DownlinkAck& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, DownlinkAck& dst);

ErrorCode serialize_payload(const Status& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Status& dst);

ErrorCode serialize_payload(const Heartbeat& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Heartbeat& dst);

ErrorCode serialize_payload(const Failure& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Failure& dst);

ErrorCode serialize_payload(const BorrowReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, BorrowReq& dst);

ErrorCode serialize_payload(const BorrowDecision& src, uint8_t* out, uint16_t capacity, uint16_t& out_len);
ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, BorrowDecision& dst);

}  // namespace SISP
