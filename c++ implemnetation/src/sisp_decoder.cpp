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
    if (out_pkt.header.svc >= ServiceCode::RESERVED_B && 
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
    uint8_t computed_crc = compute_crc8_maxim(buf, 4);
    uint8_t expected_cksm = (computed_crc >> 4) & 0x0F;
    uint8_t received_cksm = buf[4] & 0x0F;

    return expected_cksm == received_cksm;
}

bool Decoder::validate_header_checksum(const uint8_t* buf) {
    return validate_checksum(buf);
}

ErrorCode Decoder::decode_frame(const uint8_t in_frame[FRAME_SIZE],
                                Packet& out_pkt,
                                FrameInfo& out_info) {
    if (!in_frame) {
        return ErrorCode::ERR_LEN;
    }

    uint8_t frame_cksm = compute_frame_checksum(in_frame, FRAME_SIZE - 1);
    if (frame_cksm != in_frame[FRAME_SIZE - 1]) {
        return ErrorCode::ERR_CKSM;
    }

    if (unpack_header(in_frame, out_pkt.header) != ErrorCode::OK) {
        return ErrorCode::ERR_LEN;
    }

    if (!validate_header_checksum(in_frame)) {
        return ErrorCode::ERR_CKSM;
    }

    if (out_pkt.header.svc >= ServiceCode::RESERVED_B &&
        out_pkt.header.svc <= ServiceCode::RESERVED_D) {
        return ErrorCode::ERR_RESERVED;
    }

    const uint8_t payload_len = in_frame[5];
    const uint8_t ext_len = in_frame[6];
    const uint8_t ctrl = in_frame[7];
    (void)ctrl;

    out_info.payload_len = payload_len;
    out_info.extension_len = ext_len;

    uint16_t expected_ext_len = compute_frame_extension_len(out_pkt.header.flags);
    if (ext_len != expected_ext_len) {
        return ErrorCode::ERR_LEN;
    }

    if (payload_len > compute_frame_payload_capacity(out_pkt.header.flags)) {
        return ErrorCode::ERR_LEN;
    }

    uint16_t cursor = 8;
    if (out_pkt.header.flags & FLAG_PROTO) {
        out_info.transport.session_id = static_cast<uint16_t>((static_cast<uint16_t>(in_frame[cursor]) << 8) |
                                                              static_cast<uint16_t>(in_frame[cursor + 1]));
        out_info.transport.ack_seq = in_frame[cursor + 2];
        out_info.transport.window = in_frame[cursor + 3];
        cursor += 4;
    } else {
        out_info.transport.datagram_tag = in_frame[cursor + 0];
        out_info.transport.hop_limit = in_frame[cursor + 1];
        cursor += 2;
    }

    if (out_pkt.header.flags & FLAG_RELAY) {
        out_info.transport.relay_hops_remaining = in_frame[cursor + 0];
        out_info.transport.relay_path_id = in_frame[cursor + 1];
        cursor += 2;
    }

    if (out_pkt.header.flags & FLAG_TMAX) {
        out_info.transport.tmax_deadline_ds = static_cast<uint16_t>((static_cast<uint16_t>(in_frame[cursor]) << 8) |
                                                                    static_cast<uint16_t>(in_frame[cursor + 1]));
        cursor += 2;
    }

    if (!(out_pkt.header.flags & FLAG_OFFGRID)) {
        uint32_t sec_word = 0;
        uint32_t chunk = 0;
        std::memcpy(&chunk, in_frame + cursor, sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, in_frame + cursor + sizeof(chunk), sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, in_frame + cursor + (2 * sizeof(chunk)), sizeof(chunk));
        sec_word |= chunk;
        std::memcpy(&chunk, in_frame + cursor + (3 * sizeof(chunk)), sizeof(chunk));
        sec_word |= chunk;
        if (sec_word != 0) {
            return ErrorCode::ERR_CKSM;
        }
        cursor += SEC_PREFIX;
    }

    if (static_cast<uint16_t>(cursor + payload_len) > (FRAME_SIZE - 1)) {
        return ErrorCode::ERR_LEN;
    }

    out_pkt.payload_len = payload_len;
    if (payload_len > 0) {
        std::memcpy(out_pkt.payload.data(), in_frame + cursor, payload_len);
    }

    return ErrorCode::OK;
}

}  // namespace SISP
