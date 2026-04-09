#pragma once

#include "sisp_protocol.hpp"

namespace SISP {

/* ■■ Decoder: Raw Bytes → Packet ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

class Decoder {
public:
    Decoder() = default;
    ~Decoder() = default;

    // Disable copy/move (stateless utility class)
    Decoder(const Decoder&) = delete;
    Decoder& operator=(const Decoder&) = delete;

    /**
     * Decode a byte buffer into a SISP packet.
     * 
     * @param buf       Input buffer (raw packet bytes)
     * @param len       Length of buffer
     * @param out_pkt   Output packet (header + payload)
     * @return          ErrorCode (OK on success, error code otherwise)
     */
    static ErrorCode decode(const uint8_t* buf, uint16_t len, Packet& out_pkt);

    /**
     * Decode a fixed 512-bit frame into packet + frame metadata.
     */
    static ErrorCode decode_frame(const uint8_t in_frame[FRAME_SIZE],
                                  Packet& out_pkt,
                                  FrameInfo& out_info);

private:
    /**
     * Unpack the 5-byte header from raw bytes.
     */
    static ErrorCode unpack_header(const uint8_t* buf, Header& h);

    /**
     * Validate the checksum by comparing computed vs received.
     */
    static bool validate_checksum(const uint8_t* buf);

    static bool validate_header_checksum(const uint8_t* buf);
};

}  // namespace SISP
