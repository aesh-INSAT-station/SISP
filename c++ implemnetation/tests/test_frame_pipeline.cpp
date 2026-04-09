#include "sisp_encoder.hpp"
#include "sisp_decoder.hpp"
#include "sisp_state_machine.hpp"
#include "sisp_protocol.hpp"

#include <array>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <mutex>
#include <queue>
#include <thread>

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

static Event map_svc_to_event(ServiceCode svc) {
    switch (svc) {
        case ServiceCode::CORRECTION_REQ: return Event::RX_CORRECTION_REQ;
        case ServiceCode::CORRECTION_RSP: return Event::RX_CORRECTION_RSP;
        case ServiceCode::RELAY_REQ: return Event::RX_RELAY_REQ;
        case ServiceCode::RELAY_ACCEPT: return Event::RX_RELAY_ACCEPT;
        case ServiceCode::RELAY_REJECT: return Event::RX_RELAY_REJECT;
        case ServiceCode::DOWNLINK_DATA: return Event::RX_DOWNLINK_DATA;
        case ServiceCode::DOWNLINK_ACK: return Event::RX_DOWNLINK_ACK;
        case ServiceCode::STATUS_BROADCAST: return Event::RX_STATUS_BROADCAST;
        case ServiceCode::HEARTBEAT: return Event::RX_HEARTBEAT;
        case ServiceCode::HEARTBEAT_ACK: return Event::RX_HEARTBEAT_ACK;
        case ServiceCode::BORROW_REQ: return Event::RX_BORROW_REQ;
        case ServiceCode::FAILURE: return Event::RX_FAILURE;
        default: return Event::RESET;
    }
}

static void test_fixed_frame_tcp_mode() {
    Packet pkt{};
    pkt.header.svc = ServiceCode::CORRECTION_RSP;
    pkt.header.sndr = 0x11;
    pkt.header.rcvr = 0x22;
    pkt.header.seq = 0x33;
    pkt.header.degr = 4;
    pkt.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_PROTO | FLAG_TMAX);

    CorrectionRsp rsp{};
    rsp.sensor_type = SensorType::MAGNETOMETER;
    rsp.reading.x = 10.5f;
    rsp.reading.y = -4.0f;
    rsp.reading.z = 2.25f;
    rsp.reading.ts_ms = 77;
    serialize_payload(rsp, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);

    TransportMeta tx_meta{};
    tx_meta.session_id = 0x1234;
    tx_meta.ack_seq = 8;
    tx_meta.window = 32;
    tx_meta.tmax_deadline_ds = 900;

    std::array<uint8_t, FRAME_SIZE> frame{};
    ErrorCode err = Encoder::encode_frame(pkt, tx_meta, frame.data());
    ASSERT(err == ErrorCode::OK, "Encode 512-bit frame in TCP-like mode");

    Packet out{};
    FrameInfo info{};
    err = Decoder::decode_frame(frame.data(), out, info);
    ASSERT(err == ErrorCode::OK, "Decode 512-bit frame in TCP-like mode");
    ASSERT(out.header.svc == pkt.header.svc, "Frame SVC roundtrip");
    ASSERT(out.header.seq == pkt.header.seq, "Frame SEQ roundtrip");
    ASSERT(out.payload_len == pkt.payload_len, "Frame payload length roundtrip");
    ASSERT(info.transport.session_id == tx_meta.session_id, "TCP session_id parsed");
    ASSERT(info.transport.ack_seq == tx_meta.ack_seq, "TCP ack_seq parsed");
    ASSERT(info.transport.window == tx_meta.window, "TCP window parsed");
    ASSERT(info.transport.tmax_deadline_ds == tx_meta.tmax_deadline_ds, "TMAX extension parsed");
}

static void test_fixed_frame_udp_relay_mode() {
    Packet pkt{};
    pkt.header.svc = ServiceCode::RELAY_REQ;
    pkt.header.sndr = 0x31;
    pkt.header.rcvr = 0x41;
    pkt.header.seq = 0x01;
    pkt.header.degr = 1;
    pkt.header.flags = static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);  // PROTO=0 => UDP-like

    RelayReq req{};
    req.hop_count = 2;
    req.fragment_count = 5;
    req.window_s = 40;
    serialize_payload(req, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);

    TransportMeta tx_meta{};
    tx_meta.datagram_tag = 0xAA;
    tx_meta.hop_limit = 12;
    tx_meta.relay_hops_remaining = 3;
    tx_meta.relay_path_id = 9;

    std::array<uint8_t, FRAME_SIZE> frame{};
    ErrorCode err = Encoder::encode_frame(pkt, tx_meta, frame.data());
    ASSERT(err == ErrorCode::OK, "Encode 512-bit frame in UDP-like relay mode");

    Packet out{};
    FrameInfo info{};
    err = Decoder::decode_frame(frame.data(), out, info);
    ASSERT(err == ErrorCode::OK, "Decode 512-bit frame in UDP-like relay mode");
    ASSERT(info.transport.datagram_tag == tx_meta.datagram_tag, "UDP datagram_tag parsed");
    ASSERT(info.transport.hop_limit == tx_meta.hop_limit, "UDP hop_limit parsed");
    ASSERT(info.transport.relay_hops_remaining == tx_meta.relay_hops_remaining, "Relay hops parsed");
    ASSERT(info.transport.relay_path_id == tx_meta.relay_path_id, "Relay path parsed");
}

static void test_multithread_pipeline_real_data() {
    std::queue<std::array<uint8_t, FRAME_SIZE>> channel;
    std::mutex m;
    std::condition_variable cv;
    bool done = false;

    Context receiver_ctx{};
    StateMachine::init_context(receiver_ctx, 0x42);

    std::thread producer([&]() {
        for (int i = 0; i < 40; ++i) {
            Packet pkt{};
            pkt.header.svc = (i % 2 == 0) ? ServiceCode::HEARTBEAT : ServiceCode::STATUS_BROADCAST;
            pkt.header.sndr = static_cast<uint8_t>(0x10 + (i % 5));
            pkt.header.rcvr = 0x42;
            pkt.header.seq = static_cast<uint8_t>(i);
            pkt.header.degr = static_cast<uint8_t>(i % 8);
            pkt.header.flags = (i % 2 == 0)
                ? static_cast<uint8_t>(FLAG_OFFGRID | FLAG_PROTO)
                : static_cast<uint8_t>(FLAG_OFFGRID | FLAG_RELAY);

            if (pkt.header.svc == ServiceCode::HEARTBEAT) {
                Heartbeat hb{};
                hb.energy_pct = static_cast<uint8_t>(50 + (i % 40));
                hb.degr = static_cast<uint8_t>(i % 16);
                hb.uptime_s = static_cast<uint32_t>(1000 + i);
                serialize_payload(hb, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);
            } else {
                Status st{};
                st.energy_pct = static_cast<uint8_t>(70 + (i % 20));
                st.ground_vis_s = static_cast<uint16_t>(100 + i);
                st.sensor_mask = 0x3F;
                st.uptime_s = static_cast<uint32_t>(2000 + i);
                serialize_payload(st, pkt.payload.data(), MAX_PAYLOAD, pkt.payload_len);
            }

            TransportMeta meta{};
            meta.session_id = static_cast<uint16_t>(0x2200 + i);
            meta.ack_seq = static_cast<uint8_t>(i % 255);
            meta.window = 64;
            meta.datagram_tag = static_cast<uint8_t>(0x80 + (i % 32));
            meta.hop_limit = 8;
            meta.relay_hops_remaining = 2;
            meta.relay_path_id = 1;

            std::array<uint8_t, FRAME_SIZE> frame{};
            if (Encoder::encode_frame(pkt, meta, frame.data()) == ErrorCode::OK) {
                std::unique_lock<std::mutex> lock(m);
                channel.push(frame);
                lock.unlock();
                cv.notify_one();
            }
        }

        std::unique_lock<std::mutex> lock(m);
        done = true;
        lock.unlock();
        cv.notify_one();
    });

    int consumed = 0;
    int decoded_ok = 0;
    int heartbeat_count = 0;
    int status_count = 0;

    std::thread consumer([&]() {
        while (true) {
            std::unique_lock<std::mutex> lock(m);
            cv.wait(lock, [&]() { return !channel.empty() || done; });
            if (channel.empty() && done) {
                break;
            }
            auto frame = channel.front();
            channel.pop();
            lock.unlock();

            Packet pkt{};
            FrameInfo info{};
            ErrorCode err = Decoder::decode_frame(frame.data(), pkt, info);
            consumed++;
            if (err == ErrorCode::OK) {
                decoded_ok++;
                Event evt = map_svc_to_event(pkt.header.svc);
                StateMachine::dispatch(receiver_ctx, evt, &pkt);
                if (pkt.header.svc == ServiceCode::HEARTBEAT) {
                    heartbeat_count++;
                } else if (pkt.header.svc == ServiceCode::STATUS_BROADCAST) {
                    status_count++;
                }
            }
        }
    });

    producer.join();
    consumer.join();

    ASSERT(consumed == 40, "Multithread pipeline consumed all frames");
    ASSERT(decoded_ok == 40, "Multithread pipeline decoded all frames");
    ASSERT(heartbeat_count == 20, "Multithread pipeline heartbeat count correct");
    ASSERT(status_count == 20, "Multithread pipeline status count correct");
    ASSERT(receiver_ctx.last_heartbeat.uptime_s == 1038, "Receiver heartbeat state updated by real traffic");
    ASSERT(receiver_ctx.last_status.uptime_s == 2039, "Receiver status state updated by real traffic");
}

int test_frame_pipeline() {
    g_test_count = 0;
    g_passed_count = 0;

    test_fixed_frame_tcp_mode();
    test_fixed_frame_udp_relay_mode();
    test_multithread_pipeline_real_data();

    std::cout << "Frame Pipeline: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
