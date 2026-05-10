#include "sisp_protocol.hpp"
#include "sisp_degr.hpp"
#include <iostream>
#include <cmath>
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

void test_degr_zero_healthy() {
    // Healthy satellite: k_factor=1.0, no SVD residual, fresh, nominal orbit
    uint8_t degr = compute_degr(1.0f, 0.0f, 0, 0.0f);
    ASSERT(degr == 0, "Healthy satellite → DEGR=0");
}

void test_degr_fifteen_worst() {
    // Worst case: k_factor far from 1.0, high SVD residual, old satellite, off-orbit
    uint8_t degr = compute_degr(0.0f, 1.0f, 1095, 1000.0f);  // 3 years, 1km off-orbit
    ASSERT(degr == 15, "Worst case → DEGR=15");
}

void test_degr_intermediate() {
    // Medium degradation: k_factor = 0.8, SVD = 0.5, 1 year old, 100m off-orbit
    uint8_t degr = compute_degr(0.8f, 0.5f, 365, 100.0f);
    ASSERT(degr > 0 && degr < 15, "Intermediate degradation");
    std::cout << "  Intermediate DEGR=" << static_cast<int>(degr) << std::endl;
}

void test_degr_k_factor_deviation() {
    // Test k-factor contribution (gradual 0..5)
    uint8_t d0 = compute_degr(1.0f, 0.0f, 0, 0.0f);   // k deviation = 0
    uint8_t d1 = compute_degr(1.25f, 0.0f, 0, 0.0f);  // k deviation = 0.25
    uint8_t d2 = compute_degr(1.5f, 0.0f, 0, 0.0f);   // k deviation = 0.5
    
    ASSERT(d0 == 0, "DEGR=0 for k=1.0");
    ASSERT(d1 > d0, "k deviation increases DEGR");
    ASSERT(d1 == 2, "k deviation=0.25 maps to score 2");
    ASSERT(d2 == 5, "k deviation >= 0.5 maps to score 5");
}

void test_degr_svd_residual() {
    // Test SVD residual contribution (bucketed 0-5)
    uint8_t d0 = compute_degr(1.0f, 0.0f, 0, 0.0f);    // residual = 0
    uint8_t d1 = compute_degr(1.0f, 0.5f, 0, 0.0f);    // residual = 0.5 => score 3
    uint8_t d2 = compute_degr(1.0f, 1.0f, 0, 0.0f);    // residual = 1.0 → score 5
    
    ASSERT(d0 < d1, "SVD residual increases DEGR");
    ASSERT(d1 == 3, "SVD residual=0.5 maps to bucket score 3");
    ASSERT(d2 == 5, "SVD residual=1.0 → score 5");
}

void test_degr_age() {
    // Test age contribution (0-3 scale, 365 days per year)
    uint8_t d0 = compute_degr(1.0f, 0.0f, 0, 0.0f);      // age = 0 days
    uint8_t d1 = compute_degr(1.0f, 0.0f, 180, 0.0f);    // age = 180 days (0.5 years)
    uint8_t d2 = compute_degr(1.0f, 0.0f, 365, 0.0f);    // age = 365 days (1 year)
    uint8_t d3 = compute_degr(1.0f, 0.0f, 1095, 0.0f);   // age = 1095 days (3 years) → score 3
    
    ASSERT(d0 == 0, "DEGR=0 for fresh satellite");
    ASSERT(d1 >= d0, "Age score is non-decreasing");
    ASSERT(d2 >= d1, "Age score remains non-decreasing");
    ASSERT(d3 == 3, "Age >= 3 years → score 3");
}

void test_degr_orbit_error() {
    // Test orbit error contribution (0-2 scale, 250m per unit)
    uint8_t d0 = compute_degr(1.0f, 0.0f, 0, 0.0f);      // orbit = 0m
    uint8_t d1 = compute_degr(1.0f, 0.0f, 0, 100.0f);    // orbit = 100m
    uint8_t d2 = compute_degr(1.0f, 0.0f, 0, 250.0f);    // orbit = 250m → score 1
    uint8_t d3 = compute_degr(1.0f, 0.0f, 0, 500.0f);    // orbit = 500m → score 2
    
    ASSERT(d0 == 0, "DEGR=0 for nominal orbit");
    ASSERT(d1 >= d0, "Orbit score is non-decreasing below threshold");
    ASSERT(d2 <= d3, "Orbit score grows with error");
    ASSERT(d3 == 2, "Orbit error >= 500m → score 2");
}

void test_degr_clamping() {
    // Test that DEGR is clamped to [0, 15]
    uint8_t d_high = compute_degr(0.0f, 1.0f, 3650, 2000.0f);
    ASSERT(d_high == 15, "DEGR clamped to 15");
    
    uint8_t d_low = compute_degr(1.0f, 0.0f, 0, 0.0f);
    ASSERT(d_low == 0, "DEGR clamped to 0");
}

int test_degr() {
    g_test_count = 0;
    g_passed_count = 0;

    test_degr_zero_healthy();
    test_degr_fifteen_worst();
    test_degr_intermediate();
    test_degr_k_factor_deviation();
    test_degr_svd_residual();
    test_degr_age();
    test_degr_orbit_error();
    test_degr_clamping();

    std::cout << "DEGR Computation: " << g_passed_count << "/" << g_test_count << std::endl;
    if (g_passed_count != g_test_count) {
        return -1;
    }
    return g_test_count;
}
