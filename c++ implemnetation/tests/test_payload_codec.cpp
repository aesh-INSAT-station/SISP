#include "sisp_protocol.hpp"
#include <iostream>
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

static void test_correction_req_codec() {
    CorrectionReq src{};
    src.sensor_type = SensorType::GYROSCOPE;
    src.window_s = 321;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(src, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize CorrectionReq");
    ASSERT(len == 3, "CorrectionReq size is 3 bytes");

    CorrectionReq dst{};
    ASSERT(deserialize_payload(buf, len, dst) == ErrorCode::OK, "Deserialize CorrectionReq");
    ASSERT(dst.sensor_type == src.sensor_type, "CorrectionReq sensor type roundtrip");
    ASSERT(dst.window_s == src.window_s, "CorrectionReq window roundtrip");
}

static void test_correction_rsp_codec() {
    CorrectionRsp src{};
    src.sensor_type = SensorType::STAR_TRACKER;
    src.reading.x = 1.25f;
    src.reading.y = -2.5f;
    src.reading.z = 3.75f;
    src.reading.ts_ms = 123456;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(src, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize CorrectionRsp");
    ASSERT(len == 17, "CorrectionRsp size is 17 bytes");

    CorrectionRsp dst{};
    ASSERT(deserialize_payload(buf, len, dst) == ErrorCode::OK, "Deserialize CorrectionRsp");
    ASSERT(dst.sensor_type == src.sensor_type, "CorrectionRsp sensor type roundtrip");
    ASSERT(dst.reading.x == src.reading.x, "CorrectionRsp x roundtrip");
    ASSERT(dst.reading.y == src.reading.y, "CorrectionRsp y roundtrip");
    ASSERT(dst.reading.z == src.reading.z, "CorrectionRsp z roundtrip");
    ASSERT(dst.reading.ts_ms == src.reading.ts_ms, "CorrectionRsp timestamp roundtrip");
}

static void test_relay_codec() {
    RelayReq req{};
    req.hop_count = 2;
    req.fragment_count = 7;
    req.window_s = 900;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(req, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize RelayReq");
    ASSERT(len == 5, "RelayReq size is 5 bytes");

    RelayReq req_out{};
    ASSERT(deserialize_payload(buf, len, req_out) == ErrorCode::OK, "Deserialize RelayReq");
    ASSERT(req_out.hop_count == req.hop_count, "RelayReq hop count roundtrip");
    ASSERT(req_out.fragment_count == req.fragment_count, "RelayReq fragment count roundtrip");
    ASSERT(req_out.window_s == req.window_s, "RelayReq window roundtrip");

    RelayDecision dec{};
    dec.accepted = 1;
    dec.reason = 0;
    ASSERT(serialize_payload(dec, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize RelayDecision");
    ASSERT(len == 2, "RelayDecision size is 2 bytes");

    RelayDecision dec_out{};
    ASSERT(deserialize_payload(buf, len, dec_out) == ErrorCode::OK, "Deserialize RelayDecision");
    ASSERT(dec_out.accepted == dec.accepted, "RelayDecision accepted roundtrip");
    ASSERT(dec_out.reason == dec.reason, "RelayDecision reason roundtrip");
}

static void test_downlink_codec() {
    DownlinkData src{};
    src.fragment_index = 3;
    src.fragment_total = 5;
    src.data_len = 6;
    src.data[0] = 11;
    src.data[1] = 22;
    src.data[2] = 33;
    src.data[3] = 44;
    src.data[4] = 55;
    src.data[5] = 66;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(src, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize DownlinkData");
    ASSERT(len == 12, "DownlinkData size is envelope plus data");

    DownlinkData dst{};
    ASSERT(deserialize_payload(buf, len, dst) == ErrorCode::OK, "Deserialize DownlinkData");
    ASSERT(dst.fragment_index == src.fragment_index, "DownlinkData fragment index roundtrip");
    ASSERT(dst.fragment_total == src.fragment_total, "DownlinkData fragment total roundtrip");
    ASSERT(dst.data_len == src.data_len, "DownlinkData data length roundtrip");
    ASSERT(std::memcmp(dst.data.data(), src.data.data(), src.data_len) == 0, "DownlinkData bytes roundtrip");

    DownlinkAck ack{};
    ack.crc32 = 0xDEADBEEF;
    ASSERT(serialize_payload(ack, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize DownlinkAck");
    ASSERT(len == 4, "DownlinkAck size is 4 bytes");

    DownlinkAck ack_out{};
    ASSERT(deserialize_payload(buf, len, ack_out) == ErrorCode::OK, "Deserialize DownlinkAck");
    ASSERT(ack_out.crc32 == ack.crc32, "DownlinkAck crc32 roundtrip");
}

static void test_status_and_heartbeat_codec() {
    Status status{};
    status.energy_pct = 87;
    status.ground_vis_s = 120;
    status.sensor_mask = 0x3F;
    status.uptime_s = 654321;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(status, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize Status");
    ASSERT(len == 8, "Status size is 8 bytes");

    Status status_out{};
    ASSERT(deserialize_payload(buf, len, status_out) == ErrorCode::OK, "Deserialize Status");
    ASSERT(status_out.energy_pct == status.energy_pct, "Status energy roundtrip");
    ASSERT(status_out.ground_vis_s == status.ground_vis_s, "Status visibility roundtrip");
    ASSERT(status_out.sensor_mask == status.sensor_mask, "Status mask roundtrip");
    ASSERT(status_out.uptime_s == status.uptime_s, "Status uptime roundtrip");

    Heartbeat heartbeat{};
    heartbeat.energy_pct = 45;
    heartbeat.degr = 6;
    heartbeat.uptime_s = 42;
    ASSERT(serialize_payload(heartbeat, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize Heartbeat");
    ASSERT(len == 6, "Heartbeat size is 6 bytes");

    Heartbeat heartbeat_out{};
    ASSERT(deserialize_payload(buf, len, heartbeat_out) == ErrorCode::OK, "Deserialize Heartbeat");
    ASSERT(heartbeat_out.energy_pct == heartbeat.energy_pct, "Heartbeat energy roundtrip");
    ASSERT(heartbeat_out.degr == heartbeat.degr, "Heartbeat degr roundtrip");
    ASSERT(heartbeat_out.uptime_s == heartbeat.uptime_s, "Heartbeat uptime roundtrip");
}

static void test_failure_and_borrow_codec() {
    Failure failure{};
    failure.code = 9;
    failure.detail = 4;
    failure.degr = 15;

    uint8_t buf[MAX_PAYLOAD];
    uint16_t len = 0;
    ASSERT(serialize_payload(failure, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize Failure");
    ASSERT(len == 3, "Failure size is 3 bytes");

    Failure failure_out{};
    ASSERT(deserialize_payload(buf, len, failure_out) == ErrorCode::OK, "Deserialize Failure");
    ASSERT(failure_out.code == failure.code, "Failure code roundtrip");
    ASSERT(failure_out.detail == failure.detail, "Failure detail roundtrip");
    ASSERT(failure_out.degr == failure.degr, "Failure degr roundtrip");

    BorrowReq borrow_req{};
    borrow_req.sensor_type = SensorType::OPTICAL;
    borrow_req.duration_s = 180;
    borrow_req.priority = 2;
    ASSERT(serialize_payload(borrow_req, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize BorrowReq");
    ASSERT(len == 4, "BorrowReq size is 4 bytes");

    BorrowReq borrow_out{};
    ASSERT(deserialize_payload(buf, len, borrow_out) == ErrorCode::OK, "Deserialize BorrowReq");
    ASSERT(borrow_out.sensor_type == borrow_req.sensor_type, "BorrowReq sensor roundtrip");
    ASSERT(borrow_out.duration_s == borrow_req.duration_s, "BorrowReq duration roundtrip");
    ASSERT(borrow_out.priority == borrow_req.priority, "BorrowReq priority roundtrip");

    BorrowDecision decision{};
    decision.accepted = 1;
    decision.duration_s = 180;
    ASSERT(serialize_payload(decision, buf, MAX_PAYLOAD, len) == ErrorCode::OK, "Serialize BorrowDecision");
    ASSERT(len == 3, "BorrowDecision size is 3 bytes");

    BorrowDecision decision_out{};
    ASSERT(deserialize_payload(buf, len, decision_out) == ErrorCode::OK, "Deserialize BorrowDecision");
    ASSERT(decision_out.accepted == decision.accepted, "BorrowDecision accepted roundtrip");
    ASSERT(decision_out.duration_s == decision.duration_s, "BorrowDecision duration roundtrip");
}

int test_payload_codec() {
    g_test_count = 0;
    g_passed_count = 0;

    test_correction_req_codec();
    test_correction_rsp_codec();
    test_relay_codec();
    test_downlink_codec();
    test_status_and_heartbeat_codec();
    test_failure_and_borrow_codec();

    std::cout << "Payload Codec: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
