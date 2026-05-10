#pragma once

#include "sisp_protocol.hpp"

namespace SISP {

/* ■■ Encoder: Packet → Raw Bytes ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

class Encoder {
public:
    Encoder() = default;
    ~Encoder() = default;

    // Disable copy/move (stateless utility class)
    Encoder(const Encoder&) = delete;
    Encoder& operator=(const Encoder&) = delete;

    /**
     * Encode a SISP packet into a byte buffer.
     * 
     * @param pkt       Input packet (header + payload)
     * @param buf       Output buffer (must be >= MAX_PACKET bytes)
     * @param out_len   Output: number of bytes written
     * @return          ErrorCode (OK on success, ERR_LEN if payload too long)
     */
    static ErrorCode encode(const Packet& pkt, uint8_t* buf, uint16_t& out_len);

    /**
     * Encode a packet into a fixed-size 512-bit frame (64 bytes).
     * Layout: 5-byte header + frame meta + transport/security extensions + payload + frame checksum.
     */
    static ErrorCode encode_frame(const Packet& pkt,
                                  const TransportMeta& meta,
                                  uint8_t out_frame[FRAME_SIZE]);

private:
    /**
     * Pack the 5-byte header into bytes following the canonical bit layout.
     * No C++ bitfields (portability across platforms).
     */
    static void pack_header(const Header& h, uint8_t* buf);

    /**
     * Compute and insert the 4-bit checksum into byte 4.
     * CRC-8/MAXIM over bytes 0-3 with CKSM field zeroed.
     */
    static void insert_checksum(uint8_t* buf);
};

}  // namespace SISP
