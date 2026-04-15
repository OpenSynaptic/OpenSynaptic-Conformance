# OpenSynaptic Testing and Certification Process

**Version**: 1.0 · 2026-04-09
**Companion document**: [Core Technical Whitepaper](OpenSynaptic_Technical_Whitepaper.md)
**Applies to**: OpenSynaptic Core v1.3.x / v1.4.x / OSynaptic-FX v1.0.x / OSynaptic-RX v1.0.x / OSynaptic-TX v1.0.x

> 中文版 / Chinese version: [OpenSynaptic_Certification_Process_zh.md](OpenSynaptic_Certification_Process_zh.md)

---

## Table of Contents

1. [Certification System Overview](#1-certification-system-overview)
2. [Certification Level Definitions](#2-certification-level-definitions)
3. [L1 Wire Compatible Certification](#3-l1-wire-compatible-certification)
4. [L2 Protocol Conformant Certification](#4-l2-protocol-conformant-certification)
5. [L3 Fusion Certified Certification](#5-l3-fusion-certified-certification)
6. [L4 Security Validated Certification](#6-l4-security-validated-certification)
7. [L5 Full Ecosystem Certification](#7-l5-full-ecosystem-certification)
8. [Cross-Implementation Interoperability Verification](#8-cross-implementation-interoperability-verification)
9. [Regression Testing and Continuous Certification](#9-regression-testing-and-continuous-certification)
10. [Certification Report Templates](#10-certification-report-templates)

---

## 1. Certification System Overview

### 1.1 Design Principles

The OpenSynaptic certification system follows these core principles:

1. **Extreme verifiability**: every certification test has a deterministic known-answer vector (KAT) that any party can independently reproduce
2. **Layered progression**: from bit-level compatibility (L1) to full-ecosystem coverage (L5), each level builds on the previous
3. **Cross-implementation cross-checking**: self-testing is not trusted; heterogeneous implementations must cross-validate each other
4. **Zero false negatives**: certification tests may not be skipped or downgraded; only documented design limitations may be marked SKIP
5. **Automation-driven**: all certification tests can be executed automatically via CI/CD

### 1.2 Certification Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│                  Certification Level Progression                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  L1 Wire Compatible ──▶ L2 Protocol Conformant                  │
│    (CRC/B62/frame)         (cross-impl verification)            │
│          │                        │                              │
│          │                        ▼                              │
│          │                L3 Fusion Certified                    │
│          │                 (FULL/DIFF/HEART)                     │
│          │                        │                              │
│          │                        ▼                              │
│          │                L4 Security Validated                  │
│          │               (handshake/session/anti-replay)         │
│          │                        │                              │
│          │                        ▼                              │
│          └──────────▶ L5 Full Ecosystem                         │
│                        (exhaustive/plugins/orthogonal)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Certification Applicability

| Implementation under test | L1 | L2 | L3 | L4 | L5 |
|--------------------------|:--:|:--:|:--:|:--:|:--:|
| Core (Python) | Required | Required | Required | Required | Required |
| FX (C99) | Required | Required | Required | Required | Optional |
| RX (C89) | Required | Required | N/A¹ | N/A | N/A |
| TX (C89) | Required | Required | N/A² | N/A | N/A |
| Third-party implementations | Required | Required | By capability | By capability | Optional |

¹ RX decodes DATA_FULL only and does not participate in fusion strategy certification  
² TX encodes DATA_FULL only and does not participate in fusion strategy certification

---

## 2. Certification Level Definitions

### L1 — Wire Compatible

**Goal**: prove that the implementation's fundamental encode/decode algorithms are bit-for-bit consistent with the protocol wire format.

**Pass criteria**:
- All CRC reference vectors pass
- All Base62 reference vectors pass
- Frame structure byte-order validation passes
- Frame boundary condition handling is correct

### L2 — Protocol Conformant

**Goal**: prove that different implementations can exchange valid packets with each other.

**Pass criteria**:
- A frame encoded by implementation A can be correctly decoded by implementation B
- All extracted field values are consistent
- CRC cross-validation passes

### L3 — Fusion Certified

**Goal**: prove that the FULL/DIFF/HEART strategy selection and template learning behaviour is consistent with the reference implementation.

**Pass criteria**:
- The strategy sequence over N consecutive transmission rounds matches the Core reference
- DIFF bit-mask correctness
- HEART template replay consistency

### L4 — Security Validated

**Goal**: prove that the security subsystem (handshake, session, ID allocation) behaves correctly.

**Pass criteria**:
- Handshake state machine covers all paths
- Timestamp anti-replay functions correctly
- ID allocation is collision-free and lease management is correct

### L5 — Full Ecosystem

**Goal**: prove full-feature equivalence with OpenSynaptic Core.

**Pass criteria**:
- Exhaustive business-logic tests: ≥ 99.5% pass
- Plugin system behaves correctly
- Orthogonal condition combinations show no regressions

---

## 3. L1 Wire Compatible Certification

### 3.1 CRC-8/SMBUS Reference Vector Tests

#### Test L1-CRC8-01: Standard check vector

```
Input:   ASCII "123456789" (9 bytes: 0x31 0x32 0x33 0x34 0x35 0x36 0x37 0x38 0x39)
Params:  poly = 0x07, init = 0x00
Expected: 0xF4
```

**Verification code (C)**:
```c
const uint8_t data[] = { 0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39 };
uint8_t result = crc8(data, 9, 0x07, 0x00);
ASSERT(result == 0xF4);
```

**Verification code (Python)**:
```python
from opensynaptic.utils.security.security_core import crc8_smbus
assert crc8_smbus(b"123456789") == 0xF4
```

#### Test L1-CRC8-02: Single byte

```
Input:   0x01 (1 byte)
Params:  poly = 0x07, init = 0x00
Expected: 0x07
```

#### Test L1-CRC8-03: NULL / empty input

```
Input:   NULL or length 0
Expected: returns init value (0x00), no crash
```

### 3.2 CRC-16/CCITT-FALSE Reference Vector Tests

#### Test L1-CRC16-01: Standard check vector

```
Input:   ASCII "123456789"
Params:  poly = 0x1021, init = 0xFFFF
Expected: 0x29B1
```

**Verification code (C)**:
```c
const uint8_t data[] = { 0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39 };
uint16_t result = crc16(data, 9, 0x1021, 0xFFFF);
ASSERT(result == 0x29B1);
```

**Verification code (Python)**:
```python
from opensynaptic.utils.security.security_core import crc16_ccitt
assert crc16_ccitt(b"123456789") == 0x29B1
```

#### Test L1-CRC16-02: Single byte 0x00

```
Input:   0x00 (1 byte)
Params:  poly = 0x1021, init = 0xFFFF
Expected: 0xE1F0
```

#### Test L1-CRC16-03: Single byte 0xFF

```
Input:   0xFF (1 byte)
Expected: 0xFF00
```

#### Test L1-CRC16-04: NULL / empty input

```
Input:   NULL or length 0
Expected: returns init value (0xFFFF), no crash
```

### 3.3 Base62 Encode Reference Vector Tests

#### Tests L1-B62-01 through L1-B62-17: Complete reference vector set

| ID | Input value | Expected encoding | Applicable implementations |
|----|-------------|------------------|---------------------------|
| L1-B62-01 | 0 | `"0"` | Core, FX, TX |
| L1-B62-02 | 1 | `"1"` | Core, FX, TX |
| L1-B62-03 | 9 | `"9"` | Core, FX, TX |
| L1-B62-04 | 10 | `"a"` | Core, FX, TX |
| L1-B62-05 | 35 | `"z"` | Core, FX, TX |
| L1-B62-06 | 36 | `"A"` | Core, FX, TX |
| L1-B62-07 | 61 | `"Z"` | Core, FX, TX |
| L1-B62-08 | 62 | `"10"` | Core, FX, TX |
| L1-B62-09 | 3843 | `"ZZ"` | Core, FX, TX |
| L1-B62-10 | 238328 | `"1000"` (= 62³) | Core, FX, TX |
| L1-B62-11 | 215000 | `"TVK"` | Core, FX, TX, RX(dec) |
| L1-B62-12 | -1 | `"-1"` | Core, FX, TX |
| L1-B62-13 | -62 | `"-10"` | Core, FX, TX |
| L1-B62-14 | -61 | `"-Z"` | Core, FX, TX |
| L1-B62-15 | 2147483647 | `"2lkCB1"` | Core, FX, TX |
| L1-B62-16 | -2147483648 | `"-2lkCB2"` | Core, FX, TX |
| L1-B62-17 | -123456789 | `"-8m0Kx"` | Core, FX, TX |

### 3.4 Base62 Decode Reference Vector Tests

| ID | Input string | Expected value | Applicable implementations |
|----|-------------|---------------|---------------------------|
| L1-B62D-01 | `"0"` | 0 | Core, FX, RX |
| L1-B62D-02 | `"10"` | 62 | Core, FX, RX |
| L1-B62D-03 | `"-1"` | -1 | Core, FX, RX |
| L1-B62D-04 | `"TVK"` | 215000 | Core, FX, RX |
| L1-B62D-05 | `"!bad"` | ERROR (ok=0) | Core, FX, RX |
| L1-B62D-06 | NULL | ERROR (ok=0) | Core, FX, RX |

### 3.5 Frame Structure Byte-Order Tests

#### Test L1-FRAME-01: Standard frame construction and field extraction

**Test input**:
```
cmd      = 0x3F (DATA_FULL)
route    = 0x01
aid      = 0x01020304
tid      = 0x07
ts_sec   = 0x00001234  (48-bit: 0x000000001234)
body     = "T1|A01|TVK" (10 bytes)
```

**Expected frame (26 bytes)**:
```
Byte    Value (hex)           Description
[0]     3F                    cmd
[1]     01                    route
[2]     01                    aid byte 3 (MSB)
[3]     02                    aid byte 2
[4]     03                    aid byte 1
[5]     04                    aid byte 0 (LSB)
[6]     07                    tid
[7]     00                    ts byte 5 (MSB)
[8]     00                    ts byte 4
[9]     00                    ts byte 3
[10]    00                    ts byte 2
[11]    12                    ts byte 1
[12]    34                    ts byte 0 (LSB)
[13-22] body (10 bytes)       "T1|A01|TVK"
[23]    XX                    CRC-8 (body)
[24]    YY                    CRC-16 high byte
[25]    ZZ                    CRC-16 low byte
```

**Verification assertions**:
```c
// Total frame length
ASSERT(frame_len == 13 + 10 + 3);  // == 26

// Byte-order checks
ASSERT(frame[0]  == 0x3F);          // cmd
ASSERT(frame[1]  == 0x01);          // route
ASSERT(frame[2]  == 0x01);          // aid[3] MSB
ASSERT(frame[3]  == 0x02);          // aid[2]
ASSERT(frame[4]  == 0x03);          // aid[1]
ASSERT(frame[5]  == 0x04);          // aid[0] LSB
ASSERT(frame[6]  == 0x07);          // tid
ASSERT(frame[7]  == 0x00);          // ts[5] MSB
ASSERT(frame[11] == 0x12);          // ts[1]
ASSERT(frame[12] == 0x34);          // ts[0] LSB

// Body extraction
ASSERT(memcmp(frame + 13, "T1|A01|TVK", 10) == 0);

// CRC-8 (body only)
uint8_t crc8_body = crc8(frame + 13, 10, 0x07, 0x00);
ASSERT(frame[23] == crc8_body);

// CRC-16 (full frame [0..23])
uint16_t crc16_all = crc16(frame, 24, 0x1021, 0xFFFF);
ASSERT(frame[24] == (crc16_all >> 8));      // high byte
ASSERT(frame[25] == (crc16_all & 0xFF));    // low byte
```

#### Test L1-FRAME-02: Minimum frame (empty body)

```
body_len = 0
Expected frame length = 13 + 0 + 3 = 16 bytes
CRC-8(body={}) = init = 0x00
CRC-16 covers [0..13] (header + crc8)
```

#### Test L1-FRAME-03: Truncated frame rejection

```
Input:   byte sequence shorter than 16 bytes
Expected: decode function returns failure (0 or negative), no segfault
```

#### Test L1-FRAME-04: NULL input rejection

```
Input:   packet = NULL, len = 0
Expected: returns 0, no crash
```

### 3.6 L1 Pass Criteria

```
┌────────────────────────────────────────────────────────────────┐
│ L1 Wire Compatible — Pass Conditions                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ✅ L1-CRC8-01 through L1-CRC8-03      all pass (3/3)         │
│  ✅ L1-CRC16-01 through L1-CRC16-04    all pass (4/4)         │
│  ✅ L1-B62-01 through L1-B62-17        all pass (17/17)       │
│  ✅ L1-B62D-01 through L1-B62D-06      all pass (6/6)         │
│  ✅ L1-FRAME-01 through L1-FRAME-04    all pass (4/4)         │
│                                                                │
│  Total: 34/34 → L1 certified                                  │
│                                                                │
│  Zero tolerance: any failure → L1 not certified               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. L2 Protocol Conformant Certification

### 4.1 Cross-Implementation Frame Exchange Tests

The core of L2 certification: a frame encoded by one implementation must be correctly decoded by another.

#### Test L2-XENC-01: TX encode → Core decode

**Steps**:
1. TX encodes the following sensor data:
   ```
   aid=0x00010203, tid=7, ts_sec=1710000000
   sensor_id="T1", unit="A01"(Cel), scaled=215000 (21.5°C)
   ```
2. Pass the binary frame to Core `receive()`
3. Verify Core decode result

**Verification**:
```python
decoded = core_node.receive(tx_frame_bytes)
assert decoded is not None
assert decoded.get("error") is None
assert "s1_id" in decoded   # sensor ID field present
assert "s1_v" in decoded    # sensor value field present
```

#### Test L2-XENC-02: TX encode → RX decode

**Steps**:
1. TX uses `ostx_sensor_pack()` to encode the frame
2. RX uses `osrx_sensor_recv()` to decode the same frame

**Verification**:
```c
// TX side
int tx_len = ostx_sensor_pack(aid, tid, ts, "T1", "A01", 215000, tx_buf);
ASSERT(tx_len > 0);

// RX side
osrx_packet_meta rx_meta;
osrx_sensor_field rx_field;
int rx_ok = osrx_sensor_recv(tx_buf, tx_len, &rx_meta, &rx_field);
ASSERT(rx_ok == 1);
ASSERT(rx_meta.cmd == 0x3F);
ASSERT(rx_meta.aid == aid);
ASSERT(rx_meta.tid == tid);
ASSERT(strcmp(rx_field.sensor_id, "T1") == 0);
ASSERT(strcmp(rx_field.unit, "A01") == 0);
ASSERT(rx_field.scaled == 215000);
```

#### Test L2-XENC-03: FX encode → Core decode

**Steps**:
1. FX uses `osfx_core_encode_sensor_packet()` to encode
2. Transfer frame bytes via UDP or file
3. Core `receive()` decodes

**Verification**:
```python
decoded = core_node.receive(fx_frame_bytes)
assert decoded is not None
assert abs(decoded["s1_v"] - expected_value) < tolerance
```

#### Test L2-XENC-04: FX encode → RX decode

```c
// FX encode
int fx_len = osfx_core_encode_sensor_packet(
    aid, tid, ts, "T1", 21.5, "Cel", fx_buf, sizeof(fx_buf), &pkt_len);

// RX decode
int rx_ok = osrx_sensor_recv(fx_buf, pkt_len, &meta, &field);
ASSERT(rx_ok == 1);
ASSERT(field.scaled == 215000);  // 21.5 × 10000
```

#### Test L2-XENC-05: Core encode → FX decode

```python
# Core encode
packet, aid, strategy = core_node.transmit(
    sensors=[['T1', 'OK', 21.5, 'Cel']],
    device_id='TEST', device_status='ONLINE'
)
```

```c
// FX decode
osfx_packet_meta meta;
char sid[32]; double val; char unit[24];
int ok = osfx_core_decode_sensor_packet_auto(
    &state, packet, packet_len, sid, 32, &val, unit, 24, &meta);
ASSERT(ok == 1);
// Note: Core may have standardized to K; reverse-standardize before comparison
```

#### Test L2-XENC-06: Core encode → RX decode

```python
packet, _, _ = core_node.transmit(sensors=[['T1', 'OK', 21.5, 'Cel']])
# Write to file or pass via UDP
```

```c
int ok = osrx_sensor_recv(core_packet, core_len, &meta, &field);
ASSERT(ok == 1);
ASSERT(meta.crc8_ok == 1);
ASSERT(meta.crc16_ok == 1);
```

### 4.2 Multi-Sensor Frame Exchange Tests

#### Test L2-MULTI-01: FX multi-sensor → Core decode

```c
osfx_core_sensor_input sensors[] = {
    { .sensor_id="T1", .sensor_state="OK", .value=21.5,    .unit="Cel" },
    { .sensor_id="H1", .sensor_state="OK", .value=55.0,    .unit="%" },
    { .sensor_id="P1", .sensor_state="OK", .value=101.325, .unit="kPa" }
};
int len;
uint8_t cmd;
osfx_core_encode_multi_sensor_packet_auto(
    &state, aid, tid, ts, "NODE1", "ONLINE",
    sensors, 3, buf, sizeof(buf), &len, &cmd);
```

```python
decoded = core_node.receive(fx_multi_packet)
assert decoded["s1_id"] is not None  # at least 3 sensors
assert decoded["s2_id"] is not None
assert decoded["s3_id"] is not None
```

### 4.3 CRC Cross-Validation Test

#### Test L2-CRC-CROSS-01: Frame-level CRC cross-check

```
1. Implementation A encodes a frame; extract [crc8, crc16]
2. Implementation B recomputes CRC on the same frame content
3. Verify A.crc8 == B.crc8(body) AND A.crc16 == B.crc16(frame)
```

### 4.4 L2 Pass Criteria

```
┌────────────────────────────────────────────────────────────────┐
│ L2 Protocol Conformant — Pass Conditions                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Prerequisite: L1 passed                                       │
│                                                                │
│  ✅ L2-XENC-01 through L2-XENC-06     all pass (6/6)          │
│  ✅ L2-MULTI-01                        pass                    │
│  ✅ L2-CRC-CROSS-01                    pass                    │
│                                                                │
│  Total: 8/8 → L2 certified                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. L3 Fusion Certified Certification

### 5.1 Strategy Sequence Consistency Tests

#### Test L3-STRAT-01: FULL → DIFF transition

**Reference behaviour** (Core `target_sync_count=3`):

| Round | Temperature (°C) | Expected strategy | Expected CMD |
|-------|-----------------|-------------------|--------------|
| 1 | 21.0 | FULL | 63 (0x3F) |
| 2 | 21.5 | FULL | 63 |
| 3 | 22.0 | FULL | 63 |
| 4 | 22.5 | DIFF | 170 (0xAA) |
| 5 | 23.0 | DIFF | 170 |
| 6 | 23.0 | HEART | 127 (0x7F) |
| 7 | 23.0 | HEART | 127 |
| 8 | 23.5 | DIFF | 170 |

**Verification**:
```c
// FX: 8 rounds of encoding
uint8_t cmd_sequence[8];
for (int i = 0; i < 8; i++) {
    osfx_easy_encode_sensor_auto(&ctx, ts + i,
        "T1", 21.0 + i * 0.5, "Cel",
        buf, sizeof(buf), &len, &cmd_sequence[i]);
}
ASSERT(cmd_sequence[0] == 63);   // FULL
ASSERT(cmd_sequence[1] == 63);   // FULL
ASSERT(cmd_sequence[2] == 63);   // FULL
ASSERT(cmd_sequence[3] == 170);  // DIFF
```

```python
# Core: same 8 rounds
strategies = []
for i in range(8):
    pkt, _, strat = core_node.transmit(
        sensors=[['T1', 'OK', 21.0 + i * 0.5, 'Cel']])
    strategies.append(strat)
assert strategies[:3] == ['FULL_PACKET'] * 3
assert strategies[3] == 'DIFF_PACKET'
```

#### Test L3-STRAT-02: Configuration change forces FULL

**Steps**:
1. Send 3 rounds of [T1, Cel] to establish template
2. Round 4: change to [T1, Cel, H1, %] (add a channel)
3. Verify round 4 is forced to FULL

**Verification**:
```c
// First 3 rounds: single sensor
for (int i = 0; i < 3; i++) {
    osfx_easy_encode_sensor_auto(&ctx, ts+i, "T1", 21.0+i*0.5, "Cel",
        buf, sizeof(buf), &len, &cmd);
}
// Round 4: multi-sensor → structure change → forced FULL
sensors[0] = (osfx_core_sensor_input){ .sensor_id="T1", .value=22.5, .unit="Cel" };
sensors[1] = (osfx_core_sensor_input){ .sensor_id="H1", .value=55.0, .unit="%" };
osfx_easy_encode_multi_sensor_auto(&ctx, ts+3, sensors, 2,
    buf, sizeof(buf), &len, &cmd);
ASSERT(cmd == 63);  // must be FULL
```

### 5.2 DIFF Bit-Mask Correctness Tests

#### Test L3-DIFF-01: Single channel changed

```
Round 1 (FULL): T1=21.0, H1=55.0, P1=101325
Round 4 (DIFF): T1=21.5, H1=55.0, P1=101325  (only T1 changed)

Expected bitmask: 0b00000001 (bit 0 = T1 changed)
DIFF body contains only the new B62 value for T1
```

#### Test L3-DIFF-02: Multiple channels changed

```
Round 4 (DIFF): T1=22.0, H1=60.0, P1=101325  (T1 and H1 changed)

Expected bitmask: 0b00000011 (bit 0 = T1, bit 1 = H1)
```

### 5.3 HEART Template Replay Tests

#### Test L3-HEART-01: Automatic HEART when values unchanged

```
Round 3 (FULL):  T1=21.0 → template learned
Round 4 (DIFF):  T1=21.5 → delta encoded
Round 5 (HEART): T1=21.5 → no change → timestamp update only

HEART body = timestamp B64 only, no sensor fields
Decoded data matches round 4 (except timestamp)
```

### 5.4 Cross-Implementation Strategy Consistency Test

#### Test L3-CROSS-01: FX and Core strategy sequences match

```
Use the same input sequence as L3-STRAT-01:
21.0, 21.5, 22.0, 22.5, 23.0, 23.0, 23.0, 23.5 °C

Expected: FX output command sequence is identical to Core output sequence
  [63, 63, 63, 170, 170, 127, 127, 170]
```

### 5.5 L3 Pass Criteria

```
┌────────────────────────────────────────────────────────────────┐
│ L3 Fusion Certified — Pass Conditions                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Prerequisite: L2 passed                                       │
│                                                                │
│  ✅ L3-STRAT-01, L3-STRAT-02    strategy sequences (2/2)      │
│  ✅ L3-DIFF-01, L3-DIFF-02      bit-mask correctness (2/2)    │
│  ✅ L3-HEART-01                  template replay (1/1)         │
│  ✅ FX strategy seq == Core      cross-impl consistent         │
│                                                                │
│  Total: 6/6 → L3 certified                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. L4 Security Validated Certification

### 6.1 Handshake State Machine Tests

#### Test L4-HS-01: Complete handshake path

```
Step                          Expected state
────────────────────          ──────────────
Initialise                    INIT (0)
note_plaintext_sent(aid)      PLAINTEXT_SENT (1)
confirm_dict(aid)             DICT_READY (2)
mark_channel(aid)             SECURE (3)

should_encrypt(aid)           True
get_key(aid)                  32 B non-zero key
```

#### Test L4-HS-02: Multiple AIDs are independent

```
5 different AIDs each independently traverse INIT → SECURE
Verify no interference:
  AID_A.state == SECURE does not affect AID_B.state == INIT
```

#### Test L4-HS-03: Session expiry

```
Set expire_seconds = 60
1. AID_X enters SECURE, last_seen = T
2. cleanup(now = T + 61)
3. Verify AID_X reverts to INIT
```

### 6.2 Timestamp Anti-Replay Tests

#### Test L4-TS-01: Normal monotonic increase

```
check_and_update(aid, ts=1000) → ACCEPT
check_and_update(aid, ts=1001) → ACCEPT
check_and_update(aid, ts=1002) → ACCEPT
```

#### Test L4-TS-02: Replay detection

```
check_and_update(aid, ts=1000) → ACCEPT
check_and_update(aid, ts=1000) → REPLAY  (same timestamp)
```

#### Test L4-TS-03: Out-of-order detection

```
check_and_update(aid, ts=1002) → ACCEPT
check_and_update(aid, ts=1001) → OUT_OF_ORDER  (smaller timestamp)
```

### 6.3 ID Allocation Tests

#### Test L4-ID-01: Sequential allocation, no duplicates

```
Range [1, 9999], allocate 200 IDs consecutively
Verify: len(set(ids)) == 200 AND all(1 ≤ id ≤ 9999)
```

#### Test L4-ID-02: Pool exhaustion

```
Range [1, 3], allocate 4 times
First 3 succeed; 4th fails (returns error code or raises exception)
```

#### Test L4-ID-03: Lease expiry and reclamation

```
1. Allocate aid=X, lease=60s
2. Mark offline(X)
3. cleanup(now + 61)
4. Verify X can be reallocated
```

#### Test L4-ID-04: Concurrent allocation (Core/FX gateway mode only)

```
20 threads call allocate() simultaneously
Verify: 0 duplicate IDs, 0 race-condition exceptions
```

### 6.4 Handshake Dispatch and Rejection Tests

#### Test L4-DISP-01: Malformed frame rejection

```
Input:   frame of length 3
Expected: reject = MALFORMED
```

#### Test L4-DISP-02: CRC failure rejection

```
Input:   valid frame with last byte tampered
Expected: reject = CRC
```

#### Test L4-DISP-03: PING → PONG response

```
Input:   valid frame with cmd=9 (PING)
Expected: kind=CTRL, has_response=true, response[0]=10 (PONG)
```

### 6.5 L4 Pass Criteria

```
┌────────────────────────────────────────────────────────────────┐
│ L4 Security Validated — Pass Conditions                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Prerequisite: L3 passed (or L2 for decode-only implementations)│
│                                                                │
│  ✅ L4-HS-01 through L4-HS-03      handshake state (3/3)      │
│  ✅ L4-TS-01 through L4-TS-03      timestamp anti-replay (3/3) │
│  ✅ L4-ID-01 through L4-ID-04      ID allocation (4/4)        │
│  ✅ L4-DISP-01 through L4-DISP-03  handshake dispatch (3/3)   │
│                                                                │
│  Total: 13/13 → L4 certified                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. L5 Full Ecosystem Certification

### 7.1 Exhaustive Business Logic Tests

Reference `scripts/exhaustive_business_logic.py` in OpenSynaptic Core. Contains 6 exhaustive suites:

#### Suite A: Per-unit full-pipeline boundary values (494 items)

**Method**: traverse all units in all 15 UCUM libraries; for each unit take 3–5 boundary values through a complete transmit → receive round-trip.

**Acceptance criteria**:
```
relative_error = |received - expected| / max(|expected|, 1e-15)
absolute_error = |received - expected|

PASS: relative_error ≤ 0.001 OR absolute_error ≤ 0.001
SKIP: |standardized_value| > 9.22e14  (Base62 int64 upper limit)
FAIL: all other cases
```

**Known SKIPs (2 items)**:
- `mol = 6.022e+23`: exceeds Base62 encoding range
- `AU = 1e+06`: exceeds range after prefix expansion

#### Suite B: Multi-sensor cross-category combinations (350 items)

Select one representative unit from each of the 15 unit libraries; form combinations C(15,k) for channel counts k ∈ [2, 8], taking ≤ 50 groups per combination.

#### Suite C: State code exhaustive matrix (56 items)

7 device states × 8 sensor states = 56 combinations.

```
Device:  ONLINE, OFFLINE, WARN, ERROR, STANDBY, BOOT, MAINT
Sensor:  OK, WARN, ERR, FAULT, N/A, OFFLINE, OOL, TEST
```

#### Suite D: FULL → DIFF strategy progression (9 items)

Same device sends 8 consecutive rounds (temperature incremented by 0.5 °C); verify strategy sequence.

#### Suite E: Batch transmit equivalence (5 items)

`transmit_batch()` return count equals input entry count.

#### Suite F: SI prefix full pipeline (71 items)

6 decimal prefixes × 11 base units + binary prefixes + rejection tests.

### 7.2 Plugin System Tests (205 items)

| Sub-suite | Items | Coverage |
|-----------|-------|---------|
| DatabaseManager SQLite | 14 | CRUD, transactions, queries |
| PortForwarder rule management | 107 | Rule CRUD, routing match, persistence |
| TestPlugin | 4 | Component function |
| DisplayAPI formatting | 44 | Data presentation |
| Plugin registry | 36 | Register / unregister / reload |

### 7.3 Security Infrastructure Tests (43 items)

| Sub-suite | Items | Coverage |
|-----------|-------|---------|
| ID allocator | 13 | Sequential/random/dedup/release/pool/concurrent/persistent/exhausted |
| Handshake state machine | 12 | All paths/multi-AID/roles/persistence/PING |
| Environment guard | 8 | Resources/errors/state |
| Port forwarding | 10 | Firewall/traffic/protocol/proxy |

### 7.4 Orthogonal Design Tests (24 items)

Verifies cross-module interaction effects between different functional subsystems.

### 7.5 L5 Pass Criteria

```
┌────────────────────────────────────────────────────────────────┐
│ L5 Full Ecosystem — Pass Conditions                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Prerequisite: L4 passed                                       │
│                                                                │
│  Exhaustive business: ≥ 985/985 pass (SKIP ≤ 2)              │
│  Plugin system:       ≥ 205/205 pass                          │
│  Security infra:      ≥ 43/43 pass                            │
│  Orthogonal design:   ≥ 24/24 pass                            │
│                                                                │
│  Total: ≥ 1253/1257 pass (pass rate ≥ 99.5%)                 │
│         SKIP restricted to known design limitations (KL-01+)   │
│                                                                │
│  → L5 certified                                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 8. Cross-Implementation Interoperability Verification

### 8.1 Golden Frame Library

Each time a Core version is released, generate standardised **golden frame files** as the cross-implementation verification baseline:

```json
{
  "version": "1.3.1",
  "generated": "2026-04-09T00:00:00Z",
  "frames": [
    {
      "test_id": "GOLDEN-001",
      "description": "Single-sensor FULL frame (TEMP, 21.5°C)",
      "input": {
        "aid": 16909060,
        "tid": 7,
        "ts_sec": 1710000000,
        "sensors": [["T1", "OK", 21.5, "Cel"]],
        "device_id": "NODE01",
        "device_status": "ONLINE"
      },
      "expected_frame_hex": "3F0101020304070000000065E55B80...",
      "expected_decode": {
        "cmd": 63,
        "aid": 16909060,
        "tid": 7,
        "s1_id": "T1",
        "s1_v_scaled": 215000
      }
    },
    {
      "test_id": "GOLDEN-002",
      "description": "Three-sensor FULL frame (TEMP+HUM+PRESS)"
    },
    {
      "test_id": "GOLDEN-003",
      "description": "Negative-value frame (-40°C)"
    },
    {
      "test_id": "GOLDEN-004",
      "description": "Extremes frame (max/min int32 scaled values)"
    }
  ]
}
```

### 8.2 Verification Matrix

```
               Decoder
            Core    FX      RX
Enc  Core    ✅     ✅      ✅
oder FX      ✅     ✅      ✅
     TX      ✅     ✅      ✅
```

Each cell represents a set of L2-XENC tests.

### 8.3 Automated Cross-Verification Workflow

```
Step 1: Core generates golden frames → golden_frames.json
Step 2: FX  loads golden_frames.json at build time → decode verification
Step 3: TX  loads golden_frames.json at build time → encode verification (compare against expected frames)
Step 4: RX  loads golden_frames.json at build time → decode verification
Step 5: FX  encodes frames → Core decode verification
Step 6: TX  encodes frames → RX decode verification
```

### 8.4 CI/CD Integration

```yaml
# .github/workflows/certification.yml
name: OpenSynaptic Cross-Implementation Certification

on:
  push:
    branches: [main]
  pull_request:

jobs:
  l1-wire-compatible:
    strategy:
      matrix:
        impl: [core, fx, rx, tx]
    steps:
      - uses: actions/checkout@v4
      - name: Run L1 tests
        run: |
          case "${{ matrix.impl }}" in
            core) cd OpenSynaptic && python -m pytest tests/ -k "crc or base62 or packet";;
            fx)   cd OSynaptic-FX && cmake -B build -DOSFX_BUILD_TESTS=ON && cmake --build build && ctest --test-dir build;;
            rx)   cd OSynaptic-RX && cmake -B build -DOSRX_BUILD_TESTS=ON && cmake --build build && ctest --test-dir build;;
            tx)   cd OSynaptic-TX && cmake -B build -DOSTX_BUILD_TESTS=ON && cmake --build build && ctest --test-dir build;;
          esac

  l2-cross-validation:
    needs: l1-wire-compatible
    steps:
      - name: Generate golden frames (Core)
        run: cd OpenSynaptic && python scripts/generate_golden_frames.py

      - name: Validate FX against golden frames
        run: cd OSynaptic-FX && cmake -B build -DOSFX_BUILD_TESTS=ON -DGOLDEN_FRAMES=../golden_frames.json && ctest --test-dir build

      - name: Validate TX→RX roundtrip
        run: |
          cd tests/cross_impl
          cmake -B build
          cmake --build build
          ctest --test-dir build --output-on-failure

  l5-exhaustive:
    needs: l2-cross-validation
    steps:
      - name: Run exhaustive business logic
        run: cd OpenSynaptic && python scripts/exhaustive_business_logic.py
      - name: Run security tests
        run: cd OpenSynaptic && python scripts/exhaustive_security_infra_test.py
      - name: Run plugin tests
        run: cd OpenSynaptic && python scripts/exhaustive_plugin_test.py
```

---

## 9. Regression Testing and Continuous Certification

### 9.1 Version Compatibility Matrix

Each time a sub-library releases a new version, the following certification matrix must be re-executed:

| Change source | Must re-test |
|---------------|-------------|
| Core protocol change | L1 + L2 + L3 (all implementations) |
| Core security change | L4 (Core + FX) |
| FX API change | L1 + L2 (FX) |
| RX config change | L1 + L2 (RX) |
| TX API change | L1 + L2 (TX) |
| New UCUM units added | Suite A + Suite F incremental |

### 9.2 Certification Validity

| Certification level | Valid until | Renewal condition |
|--------------------|-------------|------------------|
| L1 | Permanent (invariant algorithms) | Automatic CI re-test on code change |
| L2 | Until any implementation version changes | Cross-impl frame exchange re-test |
| L3 | When Core fusion parameters change | Strategy sequence re-test |
| L4 | When security module changes | Full 43-item security test re-run |
| L5 | Quarterly (or on major changes) | Full exhaustive suite |

### 9.3 Certification Revocation Conditions

- Any L1 test fails → all certifications immediately revoked
- L2 cross-implementation test fails → L2 and above revoked
- Security vulnerability discovered → L4 + L5 revoked until fixed

---

## 10. Certification Report Templates

### 10.1 L1 Certification Report

```
═══════════════════════════════════════════════════════════
  OpenSynaptic L1 Wire Compatible Certification Report
═══════════════════════════════════════════════════════════

  Implementation under test: [implementation name]
  Version: [version string]
  Test date: [YYYY-MM-DD]
  Test environment: [OS / compiler / platform]
  Reference implementation: OpenSynaptic Core v1.4.0

  ─────────────────────────────────────────────────────────
  Test Results

  CRC-8/SMBUS Reference Vectors
    L1-CRC8-01  Standard check (0xF4)              [PASS/FAIL]
    L1-CRC8-02  Single byte (0x07)                 [PASS/FAIL]
    L1-CRC8-03  Empty input safety                 [PASS/FAIL]

  CRC-16/CCITT-FALSE Reference Vectors
    L1-CRC16-01 Standard check (0x29B1)            [PASS/FAIL]
    L1-CRC16-02 Single byte 0x00 (0xE1F0)          [PASS/FAIL]
    L1-CRC16-03 Single byte 0xFF (0xFF00)          [PASS/FAIL]
    L1-CRC16-04 Empty input safety                 [PASS/FAIL]

  Base62 Encode Reference Vectors
    L1-B62-01   0 → "0"                            [PASS/FAIL]
    L1-B62-02   1 → "1"                            [PASS/FAIL]
    ...
    L1-B62-17   -123456789 → "-8m0Kx"              [PASS/FAIL/N/A]

  Base62 Decode Reference Vectors
    L1-B62D-01  "0" → 0                            [PASS/FAIL]
    ...
    L1-B62D-06  NULL → error                       [PASS/FAIL]

  Frame Structure Verification
    L1-FRAME-01 Standard frame byte order          [PASS/FAIL]
    L1-FRAME-02 Minimum frame                      [PASS/FAIL]
    L1-FRAME-03 Truncated frame rejection          [PASS/FAIL]
    L1-FRAME-04 NULL input rejection               [PASS/FAIL]

  ─────────────────────────────────────────────────────────
  Summary

  Passed: [N] / 34
  Failed: [N] / 34
  N/A:    [N] / 34  (tests not applicable to this implementation)

  Certification result: [PASS / FAIL]

  ─────────────────────────────────────────────────────────
  Signatures

  Tester: _______________
  Reviewer: _______________
  Date: _______________
═══════════════════════════════════════════════════════════
```

### 10.2 Full Certification Summary Report

```
═══════════════════════════════════════════════════════════
  OpenSynaptic Ecosystem Certification Summary
═══════════════════════════════════════════════════════════

  Certification date: [YYYY-MM-DD]
  Reference version: Core v1.4.0

  Implementation      L1    L2    L3    L4    L5
  ─────────────────   ───   ───   ───   ───   ───
  Core (Python)        ✅    ✅    ✅    ✅    ✅
  FX (C99)             ✅    ✅    ✅    ✅    N/A
  RX (C89)             ✅    ✅    N/A   N/A   N/A
  TX (C89)             ✅    ✅    N/A   N/A   N/A

  Cross-Implementation Verification
  ─────────────────────────────────────────
  TX → Core    ✅  (L2-XENC-01)
  TX → RX      ✅  (L2-XENC-02)
  FX → Core    ✅  (L2-XENC-03)
  FX → RX      ✅  (L2-XENC-04)
  Core → FX    ✅  (L2-XENC-05)
  Core → RX    ✅  (L2-XENC-06)

  Exhaustive Test Statistics
  ─────────────────────────────────────────
  Business logic:   985 / 985  (SKIP 2, known limitations)
  Security infra:    43 / 43
  Plugin system:    205 / 205
  Orthogonal design: 24 / 24
  ─────────────────────────────────────────
  Total:  1358 / 1358  pass rate 99.85%

═══════════════════════════════════════════════════════════
```

---

## Appendix A: Test Execution Quick Reference

### Core (Python)

```bash
# L1 core algorithms
cd OpenSynaptic
python -m pytest tests/unit/test_core_algorithms.py -v

# L5 exhaustive business logic
python scripts/exhaustive_business_logic.py

# L5 security infrastructure
python scripts/exhaustive_security_infra_test.py

# L5 plugin system
python scripts/exhaustive_plugin_test.py

# Integration tests
python scripts/integration_test.py
```

### FX (C99)

```bash
cd OSynaptic-FX
cmake -B build -DOSFX_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=MinSizeRel
cmake --build build
ctest --test-dir build --output-on-failure
```

**Cross-compilation** (ESP32 example):
```bash
cmake -B build-esp32 \
  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/esp32.cmake \
  -DOSFX_ARCH_PRESET=esp32 \
  -DOSFX_BUILD_TESTS=ON
```

### RX (C89)

```bash
cd OSynaptic-RX
cmake -B build -DOSRX_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=MinSizeRel
cmake --build build
ctest --test-dir build --output-on-failure
# Expected output: 39 passed, 0 failed
```

**Minimal configuration test**:
```bash
cmake -B build-minimal \
  -DOSRX_BUILD_TESTS=ON \
  -DOSRX_PACKET_MAX=64 \
  -DOSRX_NO_PARSER=1 \
  -DOSRX_NO_TIMESTAMP=1
cmake --build build-minimal
ctest --test-dir build-minimal --output-on-failure
```

### TX (C89)

```bash
cd OSynaptic-TX
cmake -B build -DOSTX_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=MinSizeRel
cmake --build build
ctest --test-dir build --output-on-failure
# Expected output: 50 passed, 0 failed
```

---

## Appendix B: Certification Toolchain Requirements

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| Python | 3.11 | Core test runner |
| pytest | 7.0 | Unit test framework |
| CMake | 3.15 | FX/RX/TX build |
| GCC | 9.0 | C89/C99 compile |
| Clang | 12.0 | Optional compiler |
| MSVC | 2019 | Windows build |
| avr-gcc | 7.0 | AVR cross-compile (optional) |
| arm-none-eabi-gcc | 10.0 | Cortex-M cross-compile (optional) |

---

## Appendix C: Certification Test Unique Identifier Index

| Test ID | Level | Category | Description |
|---------|-------|----------|-------------|
| L1-CRC8-01 | L1 | CRC | Standard check vector 0xF4 |
| L1-CRC8-02 | L1 | CRC | Single byte 0x07 |
| L1-CRC8-03 | L1 | CRC | Empty input safety |
| L1-CRC16-01 | L1 | CRC | Standard check vector 0x29B1 |
| L1-CRC16-02 | L1 | CRC | Single byte 0x00 → 0xE1F0 |
| L1-CRC16-03 | L1 | CRC | Single byte 0xFF → 0xFF00 |
| L1-CRC16-04 | L1 | CRC | Empty input safety |
| L1-B62-01~17 | L1 | Base62 | Encode reference vectors |
| L1-B62D-01~06 | L1 | Base62 | Decode reference vectors |
| L1-FRAME-01 | L1 | Frame | Standard frame byte order |
| L1-FRAME-02 | L1 | Frame | Minimum frame |
| L1-FRAME-03 | L1 | Frame | Truncated frame rejection |
| L1-FRAME-04 | L1 | Frame | NULL input |
| L2-XENC-01~06 | L2 | Interop | Cross-implementation frame exchange |
| L2-MULTI-01 | L2 | Interop | Multi-sensor frame exchange |
| L2-CRC-CROSS-01 | L2 | Interop | CRC cross-validation |
| L3-STRAT-01~02 | L3 | Fusion | Strategy sequences |
| L3-DIFF-01~02 | L3 | Fusion | DIFF bit-mask |
| L3-HEART-01 | L3 | Fusion | HEART replay |
| L4-HS-01~03 | L4 | Security | Handshake state machine |
| L4-TS-01~03 | L4 | Security | Timestamp anti-replay |
| L4-ID-01~04 | L4 | Security | ID allocation |
| L4-DISP-01~03 | L4 | Security | Handshake dispatch |

---

*This document is generated and maintained by the OpenSynaptic project automated certification tooling.*
