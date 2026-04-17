#include "sisp_protocol.hpp"
#include <cstring>

namespace SISP {

/* ■■ CRC-8/MAXIM Lookup Table ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
/* Polynomial: 0x31, Init: 0x00, RefIn: true, RefOut: true */
static constexpr std::array<uint8_t, 256> CRC8_TABLE = {{
    0x00, 0x5E, 0xBC, 0xE2, 0x61, 0x3F, 0xDD, 0x83, 0xC2, 0x9C, 0x7E, 0x20,
    0xA3, 0xFD, 0x1F, 0x41, 0x9D, 0xC3, 0x21, 0x7F, 0xFC, 0xA2, 0x40, 0x1E,
    0x5F, 0x01, 0xE3, 0xBD, 0x3E, 0x60, 0x82, 0xDC, 0x23, 0x7D, 0x9F, 0xC1,
    0x42, 0x1C, 0xFE, 0xA0, 0xE1, 0xBF, 0x5D, 0x03, 0x80, 0xDE, 0x3C, 0x62,
    0xBE, 0xE0, 0x02, 0x5C, 0xDF, 0x81, 0x63, 0x3D, 0x7C, 0x22, 0xC0, 0x9E,
    0x1D, 0x43, 0xA1, 0xFF, 0x46, 0x18, 0xFA, 0xA4, 0x27, 0x79, 0x9B, 0xC5,
    0x84, 0xDA, 0x38, 0x66, 0xE5, 0xBB, 0x59, 0x07, 0xDB, 0x85, 0x67, 0x39,
    0xBA, 0xE4, 0x06, 0x58, 0x19, 0x47, 0xA5, 0xFB, 0x78, 0x26, 0xC4, 0x9A,
    0x65, 0x3B, 0xD9, 0x87, 0x04, 0x5A, 0xB8, 0xE6, 0xA7, 0xF9, 0x1B, 0x45,
    0xC6, 0x98, 0x7A, 0x24, 0xF8, 0xA6, 0x44, 0x1A, 0x99, 0xC7, 0x25, 0x7B,
    0x3A, 0x64, 0x86, 0xD8, 0x5B, 0x05, 0xE7, 0xB9, 0x8C, 0xD2, 0x30, 0x6E,
    0xED, 0xB3, 0x51, 0x0F, 0x4E, 0x10, 0xF2, 0xAC, 0x2F, 0x71, 0x93, 0xCD,
    0x11, 0x4F, 0xAD, 0xF3, 0x70, 0x2E, 0xCC, 0x92, 0xD3, 0x8D, 0x6F, 0x31,
    0xB2, 0xEC, 0x0E, 0x50, 0xAF, 0xF1, 0x13, 0x4D, 0xCE, 0x90, 0x72, 0x2C,
    0x6D, 0x33, 0xD1, 0x8F, 0x0C, 0x52, 0xB0, 0xEE, 0x32, 0x6C, 0x8E, 0xD0,
    0x53, 0x0D, 0xEF, 0xB1, 0xF0, 0xAE, 0x4C, 0x12, 0x91, 0xCF, 0x2D, 0x73,
    0xCA, 0x94, 0x76, 0x28, 0xAB, 0xF5, 0x17, 0x49, 0x08, 0x56, 0xB4, 0xEA,
    0x69, 0x37, 0xD5, 0x8B, 0x57, 0x09, 0xEB, 0xB5, 0x36, 0x68, 0x8A, 0xD4,
    0x95, 0xCB, 0x29, 0x77, 0xF4, 0xAA, 0x48, 0x16, 0xE9, 0xB7, 0x55, 0x0B,
    0x88, 0xD6, 0x34, 0x6A, 0x2B, 0x75, 0x97, 0xC9, 0x4A, 0x14, 0xF6, 0xA8,
    0x74, 0x2A, 0xC8, 0x96, 0x15, 0x4B, 0xA9, 0xF7, 0xB6, 0xE8, 0x0A, 0x54,
    0xD7, 0x89, 0x6B, 0x35,
}};

uint8_t compute_crc8_maxim(const uint8_t* data, size_t len) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; ++i) {
        crc = CRC8_TABLE[crc ^ data[i]];
    }
    return crc;
}

uint8_t compute_frame_checksum(const uint8_t* data, size_t len_without_checksum) {
    return compute_crc8_maxim(data, len_without_checksum);
}

uint16_t compute_frame_extension_len(uint8_t flags) {
    uint16_t ext_len = 0;

    // Transport-mode extension:
    // PROTO=1 => TCP-like tuple (session_id, ack_seq, window) => 4 bytes
    // PROTO=0 => UDP-like tuple (datagram_tag, hop_limit) => 2 bytes
    if (flags & FLAG_PROTO) {
        ext_len += 4;
    } else {
        ext_len += 2;
    }

    // Optional relay extension (2 bytes)
    if (flags & FLAG_RELAY) {
        ext_len += 2;
    }

    // Optional time-critical extension (2 bytes)
    if (flags & FLAG_TMAX) {
        ext_len += 2;
    }

    // Security prefix included when OFFGRID=0
    if (!(flags & FLAG_OFFGRID)) {
        ext_len += SEC_PREFIX;
    }

    return ext_len;
}

uint16_t compute_frame_payload_capacity(uint8_t flags) {
    // Frame layout:
    // [0..4]   header
    // [5]      payload_len
    // [6]      extension_len
    // [7]      control bits
    // [8..]    extension bytes then payload
    // [63]     frame checksum
    const uint16_t overhead = HEADER_SIZE + 3 + 1;  // header + meta + frame checksum
    const uint16_t ext_len = compute_frame_extension_len(flags);
    const uint16_t total = static_cast<uint16_t>(overhead + ext_len);
    if (total >= FRAME_SIZE) {
        return 0;
    }
    return static_cast<uint16_t>(FRAME_SIZE - total);
}

/* ■■ Service Code Name Lookup ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
const char* svc_name(ServiceCode svc) {
    switch (svc) {
        case ServiceCode::CORRECTION_REQ:     return "CORRECTION_REQ";
        case ServiceCode::CORRECTION_RSP:     return "CORRECTION_RSP";
        case ServiceCode::RELAY_REQ:          return "RELAY_REQ";
        case ServiceCode::RELAY_ACCEPT:       return "RELAY_ACCEPT";
        case ServiceCode::RELAY_REJECT:       return "RELAY_REJECT";
        case ServiceCode::DOWNLINK_DATA:      return "DOWNLINK_DATA";
        case ServiceCode::DOWNLINK_ACK:       return "DOWNLINK_ACK";
        case ServiceCode::STATUS_BROADCAST:   return "STATUS_BROADCAST";
        case ServiceCode::HEARTBEAT:          return "HEARTBEAT";
        case ServiceCode::HEARTBEAT_ACK:      return "HEARTBEAT_ACK";
        case ServiceCode::BORROW_DECISION:    return "BORROW_DECISION";
        case ServiceCode::RESERVED_B:         return "RESERVED_B";
        case ServiceCode::RESERVED_C:         return "RESERVED_C";
        case ServiceCode::RESERVED_D:         return "RESERVED_D";
        case ServiceCode::BORROW_REQ:         return "BORROW_REQ";
        case ServiceCode::FAILURE:            return "FAILURE";
        default:                              return "UNKNOWN";
    }
}

/* ■■ DEGR Computation (Section 9) ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */
uint8_t compute_degr(float k_factor, float svd_residual, 
                     uint32_t age_days, float orbit_error_m) {
    // Combined threshold model (protocol-level health score only).
    // NOTE: no SVD algorithm implementation here; this only consumes the residual input.

    // 1) k-factor contribution, gradual 0..5 (restored behavior)
    // Maps |k-1| to a 6-level score with 0.1 step buckets.
    float k_dev = std::fabsf(k_factor - 1.0f);
    uint8_t k_score = 0;
    if (k_dev >= 0.50f) {
        k_score = 5;
    } else if (k_dev >= 0.40f) {
        k_score = 4;
    } else if (k_dev >= 0.30f) {
        k_score = 3;
    } else if (k_dev >= 0.20f) {
        k_score = 2;
    } else if (k_dev >= 0.10f) {
        k_score = 1;
    }

    // 2) SVD residual contribution, bucketed 0..5 (input is expected in [0,1])
    uint8_t svd_score = 0;
    if (svd_residual > 0.80f) {
        svd_score = 5;
    } else if (svd_residual > 0.60f) {
        svd_score = 4;
    } else if (svd_residual > 0.40f) {
        svd_score = 3;
    } else if (svd_residual > 0.20f) {
        svd_score = 2;
    } else if (svd_residual > 0.00f) {
        svd_score = 1;
    }

    // 3) Age contribution 0..3
    uint8_t age_score = 0;
    if (age_days >= 1095U) {
        age_score = 3;
    } else if (age_days >= 730U) {
        age_score = 2;
    } else if (age_days >= 365U) {
        age_score = 1;
    }

    // 4) Orbit deviation contribution 0..2
    float abs_orbit = orbit_error_m < 0.0f ? -orbit_error_m : orbit_error_m;
    uint8_t orbit_score = 0;
    if (abs_orbit >= 500.0f) {
        orbit_score = 2;
    } else if (abs_orbit >= 250.0f) {
        orbit_score = 1;
    }

    // Final combined DEGR in [0,15]
    uint16_t total = static_cast<uint16_t>(k_score + svd_score + age_score + orbit_score);
    return total > 15U ? 15U : static_cast<uint8_t>(total);
}

namespace {

static ErrorCode ensure_capacity(uint16_t capacity, uint16_t required) {
    return capacity < required ? ErrorCode::ERR_LEN : ErrorCode::OK;
}

static void put_u16_be(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

static uint16_t get_u16_be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) |
                                 static_cast<uint16_t>(in[1]));
}

static void put_u32_be(uint8_t* out, uint32_t value) {
    out[0] = static_cast<uint8_t>((value >> 24) & 0xFF);
    out[1] = static_cast<uint8_t>((value >> 16) & 0xFF);
    out[2] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[3] = static_cast<uint8_t>(value & 0xFF);
}

static uint32_t get_u32_be(const uint8_t* in) {
    return (static_cast<uint32_t>(in[0]) << 24) |
           (static_cast<uint32_t>(in[1]) << 16) |
           (static_cast<uint32_t>(in[2]) << 8) |
           static_cast<uint32_t>(in[3]);
}

template <typename T>
static ErrorCode copy_exact(const T& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (out == nullptr) {
        out_len = 0;
        return ErrorCode::ERR_LEN;
    }
    out_len = static_cast<uint16_t>(sizeof(T));
    if (capacity < out_len) {
        out_len = 0;
        return ErrorCode::ERR_LEN;
    }
    std::memcpy(out, &src, sizeof(T));
    return ErrorCode::OK;
}

}  // namespace

ErrorCode serialize_payload(const CorrectionReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 3) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = static_cast<uint8_t>(src.sensor_type);
    put_u16_be(out + 1, src.window_s);
    out_len = 3;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, CorrectionReq& dst) {
    if (!data || len != 3) return ErrorCode::ERR_LEN;
    dst.sensor_type = static_cast<SensorType>(data[0]);
    dst.window_s = get_u16_be(data + 1);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const RelayReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 5) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.hop_count;
    put_u16_be(out + 1, src.fragment_count);
    put_u16_be(out + 3, src.window_s);
    out_len = 5;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, RelayReq& dst) {
    if (!data || len != 5) return ErrorCode::ERR_LEN;
    dst.hop_count = data[0];
    dst.fragment_count = get_u16_be(data + 1);
    dst.window_s = get_u16_be(data + 3);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const RelayDecision& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 2) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.accepted;
    out[1] = src.reason;
    out_len = 2;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, RelayDecision& dst) {
    if (!data || len != 2) return ErrorCode::ERR_LEN;
    dst.accepted = data[0];
    dst.reason = data[1];
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const CorrectionRsp& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 17) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = static_cast<uint8_t>(src.sensor_type);
    std::memcpy(out + 1, &src.reading.x, sizeof(float));
    std::memcpy(out + 5, &src.reading.y, sizeof(float));
    std::memcpy(out + 9, &src.reading.z, sizeof(float));
    put_u32_be(out + 13, src.reading.ts_ms);
    out_len = 17;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, CorrectionRsp& dst) {
    if (!data || len != 17) return ErrorCode::ERR_LEN;
    dst.sensor_type = static_cast<SensorType>(data[0]);
    std::memcpy(&dst.reading.x, data + 1, sizeof(float));
    std::memcpy(&dst.reading.y, data + 5, sizeof(float));
    std::memcpy(&dst.reading.z, data + 9, sizeof(float));
    dst.reading.ts_ms = get_u32_be(data + 13);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const DownlinkData& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (src.data_len > MAX_FRAGMENT_DATA) return ErrorCode::ERR_LEN;
    if (ensure_capacity(capacity, static_cast<uint16_t>(6 + src.data_len)) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    put_u16_be(out + 0, src.fragment_index);
    put_u16_be(out + 2, src.fragment_total);
    put_u16_be(out + 4, src.data_len);
    if (src.data_len > 0) {
        std::memcpy(out + 6, src.data.data(), src.data_len);
    }
    out_len = static_cast<uint16_t>(6 + src.data_len);
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, DownlinkData& dst) {
    if (!data || len < 6) return ErrorCode::ERR_LEN;
    dst.fragment_index = get_u16_be(data + 0);
    dst.fragment_total = get_u16_be(data + 2);
    dst.data_len = get_u16_be(data + 4);
    if (dst.data_len > MAX_FRAGMENT_DATA || static_cast<uint16_t>(6 + dst.data_len) != len) {
        return ErrorCode::ERR_LEN;
    }
    if (dst.data_len > 0) {
        std::memcpy(dst.data.data(), data + 6, dst.data_len);
    }
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const DownlinkAck& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 4) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    put_u32_be(out, src.crc32);
    out_len = 4;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, DownlinkAck& dst) {
    if (!data || len != 4) return ErrorCode::ERR_LEN;
    dst.crc32 = get_u32_be(data);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const Status& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 8) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.energy_pct;
    put_u16_be(out + 1, src.ground_vis_s);
    out[3] = src.sensor_mask;
    put_u32_be(out + 4, src.uptime_s);
    out_len = 8;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Status& dst) {
    if (!data || len != 8) return ErrorCode::ERR_LEN;
    dst.energy_pct = data[0];
    dst.ground_vis_s = get_u16_be(data + 1);
    dst.sensor_mask = data[3];
    dst.uptime_s = get_u32_be(data + 4);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const Heartbeat& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 6) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.energy_pct;
    out[1] = src.degr;
    put_u32_be(out + 2, src.uptime_s);
    out_len = 6;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Heartbeat& dst) {
    if (!data || len != 6) return ErrorCode::ERR_LEN;
    dst.energy_pct = data[0];
    dst.degr = data[1];
    dst.uptime_s = get_u32_be(data + 2);
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const Failure& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 3) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.code;
    out[1] = src.detail;
    out[2] = src.degr;
    out_len = 3;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, Failure& dst) {
    if (!data || len != 3) return ErrorCode::ERR_LEN;
    dst.code = data[0];
    dst.detail = data[1];
    dst.degr = data[2];
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const BorrowReq& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 4) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = static_cast<uint8_t>(src.sensor_type);
    put_u16_be(out + 1, src.duration_s);
    out[3] = src.priority;
    out_len = 4;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, BorrowReq& dst) {
    if (!data || len != 4) return ErrorCode::ERR_LEN;
    dst.sensor_type = static_cast<SensorType>(data[0]);
    dst.duration_s = get_u16_be(data + 1);
    dst.priority = data[3];
    return ErrorCode::OK;
}

ErrorCode serialize_payload(const BorrowDecision& src, uint8_t* out, uint16_t capacity, uint16_t& out_len) {
    if (ensure_capacity(capacity, 3) != ErrorCode::OK) return ErrorCode::ERR_LEN;
    out[0] = src.accepted;
    put_u16_be(out + 1, src.duration_s);
    out_len = 3;
    return ErrorCode::OK;
}

ErrorCode deserialize_payload(const uint8_t* data, uint16_t len, BorrowDecision& dst) {
    if (!data || len != 3) return ErrorCode::ERR_LEN;
    dst.accepted = data[0];
    dst.duration_s = get_u16_be(data + 1);
    return ErrorCode::OK;
}

}  // namespace SISP
