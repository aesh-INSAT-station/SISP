#include "sisp_decoder.hpp"
#include "sisp_protocol.hpp"
#include <cstring>

namespace SISP {

ErrorCode Decoder::decode(const uint8_t* buf, uint16_t len, Packet& out_pkt) {
    if (!buf || len < HEADER_SIZE) {
        return ErrorCode::ERR_LEN;
    }

    // Unpack header
    ErrorCode err = unpack_header(buf, out_pkt.header);
    if (err != ErrorCode::OK) {
        return err;
    }

    // Validate checksum
    if (!validate_checksum(buf)) {
        return ErrorCode::ERR_CKSM;
    }

    // Reject reserved SVC codes
    if (out_pkt.header.svc >= ServiceCode::RESERVED_A && 
        out_pkt.header.svc <= ServiceCode::RESERVED_D) {
        return ErrorCode::ERR_RESERVED;
    }

    // Extract payload — skip security prefix if present
    uint16_t offset = HEADER_SIZE;
    if (!(out_pkt.header.flags & FLAG_OFFGRID)) {
        if (len < offset + SEC_PREFIX) {
            return ErrorCode::ERR_LEN;
        }

        uint32_t sec_word = 0;
        uint32_t chunk = 0;
        std::memcpy(&chunk, buf + offset, sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, buf + offset + sizeof(chunk), sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, buf + offset + (2 * sizeof(chunk)), sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, buf + offset + (3 * sizeof(chunk)), sizeof(chunk));
        sec_word |= chunk;
        if (sec_word != 0) {
            return ErrorCode::ERR_CKSM;
        }

        offset += SEC_PREFIX;
    }

    out_pkt.payload_len = len - offset;
    if (out_pkt.payload_len > MAX_PAYLOAD) {
        return ErrorCode::ERR_LEN;
    }

    std::memcpy(out_pkt.payload.data(), buf + offset, out_pkt.payload_len);

    return ErrorCode::OK;
}

ErrorCode Decoder::unpack_header(const uint8_t* buf, Header& h) {
    // Unpack header — inverse of encode
    // Bit layout:
    // Byte 0: [ SVC[3:0] (high 4) | SNDR[7:4] (low 4) ]
    // Byte 1: [ SNDR[3:0] (high 4) | RCVR[7:4] (low 4) ]
    // Byte 2: [ RCVR[3:0] (high 4) | SEQ[7:4] (low 4) ]
    // Byte 3: [ SEQ[3:0] (high 4) | DEGR[3:0] (low 4) ]
    // Byte 4: [ FLAGS[3:0] (high 4) | CKSM[3:0] (low 4) ]

    h.svc = static_cast<ServiceCode>((buf[0] >> 4) & 0x0F);
    h.sndr = ((buf[0] & 0x0F) << 4) | ((buf[1] >> 4) & 0x0F);
    h.rcvr = ((buf[1] & 0x0F) << 4) | ((buf[2] >> 4) & 0x0F);
    h.seq = ((buf[2] & 0x0F) << 4) | ((buf[3] >> 4) & 0x0F);
    h.degr = (buf[3] & 0x0F);
    h.flags = (buf[4] >> 4) & 0x0F;
    h.cksm = (buf[4] & 0x0F);

    return ErrorCode::OK;
}

bool Decoder::validate_checksum(const uint8_t* buf) {
    // Compute CRC-8/MAXIM over bytes 0-3 with CKSM field zeroed
    // The received CKSM is in buf[4] low nibble
    // Expected value is upper nibble of the computed CRC

    auto buf_copy = std::array<uint8_t, 4>{};
    std::memcpy(buf_copy.data(), buf, 4);
    buf_copy[4 - 4] = buf[4]; // Copy byte 4 but with CKSM zeroed (already is)
    
    uint8_t computed_crc = compute_crc8_maxim(buf, 4);
    uint8_t expected_cksm = (computed_crc >> 4) & 0x0F;
    uint8_t received_cksm = buf[4] & 0x0F;

    return expected_cksm == received_cksm;
}

}  // namespace SISP
