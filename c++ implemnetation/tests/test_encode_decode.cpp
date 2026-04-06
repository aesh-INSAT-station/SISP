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

void test_roundtrip_correction_req() {
    Packet pkt{};
    pkt.header.svc = ServiceCode::CORRECTION_REQ;
    pkt.header.sndr = 0x03;
    pkt.header.rcvr = BCAST_ADDR;
    pkt.header.seq = 0x01;
    pkt.header.degr = 2;
    pkt.header.flags = FLAG_OFFGRID;  // public broadcast

    pkt.payload[0] = static_cast<uint8_t>(SensorType::MAGNETOMETER);
    pkt.payload[1] = 0x00;
    pkt.payload[2] = 0x1E;  // 30s window
    pkt.payload_len = 3;

    uint8_t buf[MAX_PACKET];
    uint16_t len;

    ErrorCode err = Encoder::encode(pkt, buf, len);
    ASSERT(err == ErrorCode::OK, "Encode returns OK");
    ASSERT(len == HEADER_SIZE + 3, "Encoded length correct (no security prefix)");

    Packet decoded{};
    err = Decoder::decode(buf, len, decoded);
    ASSERT(err == ErrorCode::OK, "Decode returns OK");
    ASSERT(decoded.header.svc == ServiceCode::CORRECTION_REQ, "SVC roundtrip");
    ASSERT(decoded.header.sndr == 0x03, "SNDR roundtrip");
    ASSERT(decoded.header.rcvr == BCAST_ADDR, "RCVR roundtrip");
    ASSERT(decoded.header.degr == 2, "DEGR roundtrip");
    ASSERT(decoded.payload[0] == static_cast<uint8_t>(SensorType::MAGNETOMETER), "Payload[0] roundtrip");
}

void test_cksm_corruption_detected() {
    Packet pkt{};
    pkt.header.svc = ServiceCode::HEARTBEAT;
    pkt.header.sndr = 0x05;
    pkt.header.rcvr = 0x06;
    pkt.header.seq = 0x10;
    pkt.header.degr = 3;
    pkt.header.flags = FLAG_OFFGRID;
    pkt.payload_len = 0;

    uint8_t buf[MAX_PACKET];
    uint16_t len;

    ErrorCode err = Encoder::encode(pkt, buf, len);
    ASSERT(err == ErrorCode::OK, "Encode valid packet");

    // Flip one bit in header (byte 1)
    buf[1] ^= 0x01;

    Packet decoded{};
    err = Decoder::decode(buf, len, decoded);
    ASSERT(err == ErrorCode::ERR_CKSM, "Corrupted checksum detected");
}

void test_broadcast_address_detection() {
    Packet pkt{};
    pkt.header.rcvr = BCAST_ADDR;
    
    ASSERT(pkt.is_broadcast(), "is_broadcast() returns true for 0xFF");

    pkt.header.rcvr = 0x05;
    ASSERT(!pkt.is_broadcast(), "is_broadcast() returns false for non-0xFF");

    pkt.header.rcvr = BCAST_ADDR;
    ASSERT(pkt.is_for_me(0x01), "is_for_me() returns true for broadcast");
    ASSERT(pkt.is_for_me(0x01), "is_for_me() returns true for matching receiver");

    pkt.header.rcvr = 0x02;
    ASSERT(!pkt.is_for_me(0x01), "is_for_me() returns false for non-matching receiver");
}

void test_correction_rsp_with_payload() {
    Packet pkt{};
    pkt.header.svc = ServiceCode::CORRECTION_RSP;
    pkt.header.sndr = 0x07;
    pkt.header.rcvr = 0x03;
    pkt.header.seq = 0x42;
    pkt.header.degr = 5;
    pkt.header.flags = FLAG_OFFGRID;

    // Payload: sensor_type(1B) + reading_xyz(12B floats) + timestamp(4B)
    pkt.payload[0] = static_cast<uint8_t>(SensorType::MAGNETOMETER);
    float* readings = reinterpret_cast<float*>(&pkt.payload[1]);
    readings[0] = 100.5f;
    readings[1] = 200.3f;
    readings[2] = 300.1f;
    uint32_t* ts = reinterpret_cast<uint32_t*>(&pkt.payload[13]);
    *ts = 123456789;
    pkt.payload_len = 17;

    uint8_t buf[MAX_PACKET];
    uint16_t len;

    ErrorCode err = Encoder::encode(pkt, buf, len);
    ASSERT(err == ErrorCode::OK, "Encode response with float payload");
    ASSERT(len == HEADER_SIZE + 17, "Response packet length includes floats");

    Packet decoded{};
    err = Decoder::decode(buf, len, decoded);
    ASSERT(err == ErrorCode::OK, "Decode response packet");
    
    float* dec_readings = reinterpret_cast<float*>(&decoded.payload[1]);
    ASSERT(dec_readings[0] == readings[0], "Float payload[0] roundtrip");
    ASSERT(dec_readings[1] == readings[1], "Float payload[1] roundtrip");
    ASSERT(dec_readings[2] == readings[2], "Float payload[2] roundtrip");

    uint32_t* dec_ts = reinterpret_cast<uint32_t*>(&decoded.payload[13]);
    ASSERT(*dec_ts == *ts, "Timestamp roundtrip");
}

void test_all_svc_codes() {
    // Quick smoke test for all service codes
    Packet pkt{};
    pkt.header.sndr = 0x01;
    pkt.header.rcvr = 0x02;
    pkt.header.seq = 0x00;
    pkt.header.degr = 0;
    pkt.header.flags = FLAG_OFFGRID;
    pkt.payload_len = 0;

    uint8_t buf[MAX_PACKET];
    uint16_t len;
    Packet decoded{};

    for (int i = 0; i < 16; ++i) {
        pkt.header.svc = static_cast<ServiceCode>(i);
        
        // Skip reserved codes (they should fail decode)
        if (i >= static_cast<int>(ServiceCode::RESERVED_A) && 
            i <= static_cast<int>(ServiceCode::RESERVED_D)) {
            continue;
        }

        ErrorCode err = Encoder::encode(pkt, buf, len);
        ASSERT(err == ErrorCode::OK, std::string("Encode SVC=") + std::to_string(i));

        err = Decoder::decode(buf, len, decoded);
        ASSERT(err == ErrorCode::OK, std::string("Decode SVC=") + std::to_string(i));
        ASSERT(decoded.header.svc == pkt.header.svc, 
               std::string("SVC roundtrip for code ") + std::to_string(i));
    }
}

int test_encode_decode() {
    g_test_count = 0;
    g_passed_count = 0;

    test_roundtrip_correction_req();
    test_cksm_corruption_detected();
    test_broadcast_address_detection();
    test_correction_rsp_with_payload();
    test_all_svc_codes();

    std::cout << "Encode/Decode: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
