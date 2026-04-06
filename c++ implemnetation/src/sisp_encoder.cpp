#include "sisp_encoder.hpp"
#include "sisp_protocol.hpp"
#include <cstring>

namespace SISP {

ErrorCode Encoder::encode(const Packet& pkt, uint8_t* buf, uint16_t& out_len) {
    if (!buf) {
        out_len = 0;
        return ErrorCode::ERR_LEN;
    }

    if (pkt.payload_len > MAX_PAYLOAD) {
        out_len = 0;
        return ErrorCode::ERR_LEN;
    }

    const Header& h = pkt.header;

    // Pack 5-byte header — no bitfields, pure bit ops
    pack_header(h, buf);

    // Compute and insert checksum
    insert_checksum(buf);

    // Security prefix — only if OFFGRID=0 (i.e., encrypted)
    uint16_t offset = HEADER_SIZE;
    if (!(h.flags & FLAG_OFFGRID)) {
        // TODO: copy key_handle[4] + hmac_truncated[12] here
        // For simulation: zero-fill the security prefix
        std::memset(buf + offset, 0x00, SEC_PREFIX);
        offset += SEC_PREFIX;
    }

    // Payload
    std::memcpy(buf + offset, pkt.payload.data(), pkt.payload_len);
    out_len = offset + pkt.payload_len;

    return ErrorCode::OK;
}

void Encoder::pack_header(const Header& h, uint8_t* buf) {
    // Bit layout (canonical):
    // Byte 0: [ SVC[3:0] (high 4) | SNDR[7:4] (low 4) ]
    // Byte 1: [ SNDR[3:0] (high 4) | RCVR[7:4] (low 4) ]
    // Byte 2: [ RCVR[3:0] (high 4) | SEQ[7:4] (low 4) ]
    // Byte 3: [ SEQ[3:0] (high 4) | DEGR[3:0] (low 4) ]
    // Byte 4: [ FLAGS[3:0] (high 4) | CKSM[3:0] (low 4) ] — CKSM zeroed for now

    buf[0] = ((static_cast<uint8_t>(h.svc) & 0x0F) << 4) | 
             ((h.sndr >> 4) & 0x0F);

    buf[1] = ((h.sndr & 0x0F) << 4) | 
             ((h.rcvr >> 4) & 0x0F);

    buf[2] = ((h.rcvr & 0x0F) << 4) | 
             ((h.seq >> 4) & 0x0F);

    buf[3] = ((h.seq & 0x0F) << 4) | 
             (h.degr & 0x0F);

    buf[4] = ((h.flags & 0x0F) << 4);  // CKSM zeroed for now
}

void Encoder::insert_checksum(uint8_t* buf) {
    // CRC-8/MAXIM over buf[0..3] with buf[4] CKSM nibble = 0
    // Store upper nibble of result into buf[4] lower nibble
    uint8_t cksm = compute_crc8_maxim(buf, 4);
    buf[4] |= (cksm >> 4) & 0x0F;
}

}  // namespace SISP
