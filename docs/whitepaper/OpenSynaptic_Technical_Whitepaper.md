# OpenSynaptic Core Technical Whitepaper

**Version**: 1.0 · 2026-04-09
**Scope**: OpenSynaptic v1.3.x / OSynaptic-FX v1.0.x / OSynaptic-RX v1.0.x / OSynaptic-TX v1.0.x
**Classification**: Public Technical Document

> 中文版 / Chinese version: [OpenSynaptic_Technical_Whitepaper_zh.md](OpenSynaptic_Technical_Whitepaper_zh.md)

---

## Abstract

OpenSynaptic is a high-performance protocol stack for IoT sensor networks, implementing a **2-N-2 topology** (multiple transmitters → hub → multiple receivers). The protocol core provides a five-stage processing pipeline: standardization (UCUM), compression (Base62), fusion encoding (FULL/DIFF/HEART), secure transport, and persistent storage. Its embedded satellite libraries — **FX** (Full-eXperience encoder), **RX** (compact receive decoder), and **TX** (minimal transmit encoder) — cover the full MCU spectrum from ATtiny25 (2 KB Flash / 128 B RAM) to ESP32 (520 KB SRAM).

This whitepaper defines the OpenSynaptic ecosystem's core protocol specification, cross-platform API contracts, complete certification matrix, and independently reproducible verification procedures.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Wire Protocol Specification](#2-wire-protocol-specification)
3. [Core Algorithms](#3-core-algorithms)
4. [Satellite Library Technical Specifications](#4-satellite-library-technical-specifications)
5. [API Contracts and Alignment Matrices](#5-api-contracts-and-alignment-matrices)
6. [Security Architecture](#6-security-architecture)
7. [UCUM Standardization Engine](#7-ucum-standardization-engine)
8. [Performance Benchmarks](#8-performance-benchmarks)
9. [Testing and Certification System](#9-testing-and-certification-system)
10. [Appendices](#appendices)

---

## 1. System Architecture

### 1.1 Global Topology

```
                          ┌───────────────────────┐
                          │   OpenSynaptic Core   │
                          │  (Python 3.11 + Rust) │
                          │                       │
                          │  ┌─────────────────┐  │
[FX Node] ─── UDP ──────▶│  │ Unified Parser   │  │──▶ SQL / REST API
[FX Node] ─── MQTT ─────▶│  │ (FULL/DIFF/HEART)│  │
[TX Node] ─── UART ─────▶│  │                  │  │──▶ TUI / Web Dashboard
[TX Node] ─── LoRa ─────▶│  │ Standardizer     │  │
                          │  │ (UCUM / Base62)  │  │
                          │  └─────────────────┘  │
                          │          │             │
                          │          ▼             │
                          │  ┌─────────────────┐  │
                          │  │ Dispatch Engine  │  │
                          │  │ (UDP/TCP/MQTT/   │  │
                          │  │  UART/CAN/LoRa)  │  │
                          │  └─────────────────┘  │
                          └──────────┬────────────┘
                                     │
                          ┌──────────▼────────────┐
                          │  [RX Node] 8-bit MCU  │
                          │  (decode-only, no heap)│
                          └───────────────────────┘
```

### 1.2 Encoding Layers and Data Flow

| Stage | Input | Output | Module |
|-------|-------|--------|--------|
| **L1 Acquisition** | Raw sensor readings | `[sid, state, value, unit]` array | Application layer |
| **L2 Standardization** | User unit + value | UCUM canonical unit + SI base value | `OpenSynapticStandardizer` |
| **L3 Compression** | Standardized Fact JSON | Base62 compact string | `OpenSynapticEngine` |
| **L4 Fusion Encoding** | Base62 string | Binary frame (13 B header + body + 3 B CRC) | `OSVisualFusionEngine` |
| **L5 Transport** | Binary frame | Network/physical layer delivery | `TransportManager` |

### 1.3 Component Responsibility Matrix

| Capability | Core (Python) | FX (C99) | RX (C89) | TX (C89) |
|------------|:---:|:---:|:---:|:---:|
| UCUM standardization | ✅ 15 libs full | ✅ 50+ units | ✖ | ✖ |
| Base62 encode | ✅ i64 | ✅ i64 | ✖ | ✅ i32 |
| Base62 decode | ✅ i64 | ✅ i64 | ✅ i32 | ✖ |
| FULL encode | ✅ | ✅ | ✖ | ✅ |
| DIFF encode | ✅ | ✅ | ✖ | ✖ |
| HEART encode | ✅ | ✅ | ✖ | ✖ |
| FULL decode | ✅ | ✅ | ✅ | ✖ |
| DIFF decode | ✅ | ✅ | ✖ | ✖ |
| HEART decode | ✅ | ✅ | ✖ | ✖ |
| CRC-8 (body) | ✅ | ✅ | ✅ | ✅ |
| CRC-16/CCITT | ✅ | ✅ | ✅ | ✅ |
| ID allocation | ✅ adaptive lease | ✅ adaptive lease | ✖ | ✖ |
| Secure session | ✅ AES-128 | ✅ XOR+TSCheck | ✖ | ✖ |
| Handshake control plane | ✅ 14 CMDs | ✅ 14 CMDs | ✖ | ✖ |
| Multi-transport drivers | ✅ UDP/TCP/QUIC/UART/CAN/LoRa/BLE | ✅ protocol matrix | ✖ | ✖ |
| Plugin system | ✅ 6 plugin types | ✅ 3 plugin types | ✖ | ✖ |
| Storage backend | ✅ SQLite/MySQL/PG | ✅ LittleFS | ✖ | ✖ |
| REST API | ✅ | ✖ | ✖ | ✖ |
| TUI/Web UI | ✅ | ✖ | ✖ | ✖ |

---

## 2. Wire Protocol Specification

### 2.1 Frame Structure

```
Offset  Field       Len    Encoding    Description
──────  ─────       ───    ────────    ───────────
[0]     cmd         1 B    uint8       Command byte
[1]     route       1 B    uint8       Route count (fixed = 1)
[2-5]   aid         4 B    BE uint32   Sender assigned ID
[6]     tid         1 B    uint8       Template/transaction ID
[7-12]  timestamp   6 B    BE uint48   Unix timestamp (seconds or milliseconds)
[13..N] body        var    ASCII/B62   Payload
[N+1]   crc8        1 B    uint8       CRC-8(body)
[N+2..N+3] crc16    2 B    BE uint16   CRC-16(full frame [0..N+1])
```

**Minimum frame**: 16 bytes (empty body + CRC)  
**Maximum frame**: determined by `PACKET_MAX` (default 96 B for RX / 256 B for FX / unlimited for Core)

### 2.2 Command Byte Definitions

#### Data Commands (6 types)

| Byte Value | Symbol | Description |
|------------|--------|-------------|
| `0x3F` (63) | `DATA_FULL` | Full-field frame (plaintext) |
| `0x40` (64) | `DATA_FULL_SEC` | Full-field frame (encrypted) |
| `0xAA` (170) | `DATA_DIFF` | Incremental update frame (plaintext) |
| `0xAB` (171) | `DATA_DIFF_SEC` | Incremental update frame (encrypted) |
| `0x7F` (127) | `DATA_HEART` | Heartbeat frame (plaintext) |
| `0x80` (128) | `DATA_HEART_SEC` | Heartbeat frame (encrypted) |

#### Control Commands (12 types)

| Byte Value | Symbol | Direction | Description |
|------------|--------|-----------|-------------|
| 1 | `ID_REQUEST` | C→S | Request AID allocation |
| 2 | `ID_ASSIGN` | S→C | Assign AID + timestamp |
| 3 | `ID_POOL_REQ` | GW→S | Bulk ID request |
| 4 | `ID_POOL_RES` | S→GW | Bulk ID response |
| 5 | `HANDSHAKE_ACK` | S→C | Handshake confirmed |
| 6 | `HANDSHAKE_NACK` | S→C | Handshake rejected |
| 9 | `PING` | bidirectional | Keepalive probe |
| 10 | `PONG` | bidirectional | Keepalive response |
| 11 | `TIME_REQUEST` | C→S | Time sync request |
| 12 | `TIME_RESPONSE` | S→C | Time sync response |
| 13 | `SECURE_DICT_READY` | C→S | Secure dictionary ready |
| 14 | `SECURE_CHANNEL_ACK` | S→C | Secure channel confirmed |

### 2.3 FULL Body Format

Template syntax (pipe-delimited):
```
{NodeID}.{NodeState}.{TS_B64}|{SID}>U.{UnitCode}:{B62Value}|...
```

**Field descriptions**:
- `NodeID`: node identifier (≤ 31 characters)
- `NodeState`: device status code (`U` = ONLINE, 1 character per state)
- `TS_B64`: 6-byte timestamp encoded as Base64url (8 characters, no padding)
- `SID`: sensor identifier (≤ 8 characters)
- `UnitCode`: 3-digit symbol code defined in `OS_Symbols.json` (e.g. `A01` = Cel)
- `B62Value`: Base62-encoded scaled integer (`value × 10000`)

**Example**:
```
NODE01.U.AAAAABI0|TEMP>U.A01:TVK|HUM>U.C00:1rq|
```

### 2.4 DIFF Body Format

```
Offset        Field           Description
──────        ─────           ───────────
[0..K]        TS_B64          Updated timestamp
[K+1]         bitmask         Bit mask (bit i = 1 means channel i has changed)
[K+2..]       changed[]       Changed field sequence: [len:1B][b62_value:varB]
```

**Compression ratio**: 70–80% savings relative to FULL

### 2.5 HEART Body Format

```
[0..K]        TS_B64          Timestamp update only; remaining fields replayed from cached template
```

### 2.6 CRC Verification Specification

| Algorithm | Polynomial | Initial Value | Scope | Reference Vector |
|-----------|------------|---------------|-------|------------------|
| CRC-8/SMBUS | `0x07` | `0x00` | body only | `"123456789"` → `0xF4` |
| CRC-16/CCITT-FALSE | `0x1021` | `0xFFFF` | full frame `[0..crc8]` | `"123456789"` → `0x29B1` |

### 2.7 Strategy Selection Algorithm

```
function select_strategy(aid, sensor_config):
    entry = fusion_registry.lookup(aid)

    if entry is None OR entry.sensor_config ≠ sensor_config:
        entry = fusion_registry.learn(aid, sensor_config)
        entry.sync_count = 0
        return FULL

    entry.sync_count += 1

    if entry.sync_count ≤ target_sync_count:    // default = 3
        return FULL

    if all_values_unchanged(entry):
        return HEART

    return DIFF
```

---

## 3. Core Algorithms

### 3.1 Base62 Encode/Decode

**Character set**: `0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ` (indices 0–61)

**Encoding algorithm** (i64 → string):
```
Input:  signed 64-bit integer v
Output: Base62 string s

1. If v < 0: output '-', v = |v|
2. If v == 0: output "0", return
3. digits = []
4. while v > 0:
       digits.append(CHARSET[v % 62])
       v = v / 62
5. s = reverse(digits)
```

**Encoding range**:
- Core (Python): ±9.22×10¹⁸ (int64)
- FX (C99): ±4.61×10¹⁸ (int64, 63-bit signed magnitude)
- TX/RX (C89): ±2.15×10⁹ (int32)

**Precision scaling**: `scaled_value = round(real_value × SCALE_FACTOR)`
- SCALE_FACTOR = 10000 (unified across Core, FX, TX, and RX)
- Effective precision = 4 decimal places

### 3.2 CRC-8 Bit-Loop Implementation

```c
uint8_t crc8(const uint8_t* data, size_t len, uint16_t poly, uint8_t init) {
    uint8_t crc = init;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc & 0x80) ? ((crc << 1) ^ (uint8_t)poly) : (crc << 1);
        }
    }
    return crc;
}
```

**Flash cost**: ~72 B (no lookup table, suitable for ATtiny-class MCUs)

### 3.3 CRC-16/CCITT Bit-Loop Implementation

```c
uint16_t crc16(const uint8_t* data, size_t len, uint16_t poly, uint16_t init) {
    uint16_t crc = init;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            crc = (crc & 0x8000) ? ((crc << 1) ^ poly) : (crc << 1);
        }
    }
    return crc;
}
```

### 3.4 Base64url Timestamp Encoding

Encodes a 48-bit Unix timestamp as an 8-character Base64url string (no padding).

Character set: `A-Z a-z 0-9 - _` (RFC 4648 §5)

### 3.5 Fusion State Machine

```
                    ┌──────────────┐
                    │   UNKNOWN    │
                    │ (no template)│
                    └──────┬───────┘
                           │ first FULL packet
                           ▼
                    ┌──────────────┐
                    │   LEARNING   │◀──── config change
                    │ sync_count<N │
                    └──────┬───────┘
                           │ sync_count ≥ N
                           ▼
              ┌────────────────────────┐
              │       TRACKING         │
              │ template learned       │
              └───────┬────────┬───────┘
                      │        │
        values changed│        │all values unchanged
                      ▼        ▼
               ┌──────────┐ ┌──────────┐
               │   DIFF   │ │  HEART   │
               │ delta enc│ │ ts only  │
               └──────────┘ └──────────┘
```

---

## 4. Satellite Library Technical Specifications

### 4.1 OSynaptic-FX (Full-eXperience Embedded Encoder)

| Property | Specification |
|----------|---------------|
| **Language standard** | C99 (no C++ dependency) |
| **Target platforms** | ESP32, STM32, RP2040, RISC-V, AVR, Cortex-M, Linux |
| **Default RAM** | ~27 KB DRAM (ESP32 full config) |
| **Source code** | 28 C files + 3000 lines generated data ≈ 11,500 LOC |
| **Layered architecture** | Easy API → Core Facade → Fusion Engine → Protocol Core → Security → Runtime |
| **Transport drivers** | UDP / TCP / UART / CAN with protocol-matrix auto-selection |
| **Storage backend** | Pluggable: default FILE_IO / LittleFS / custom |
| **Arduino support** | One-click install via Library Manager |
| **CMake build** | 9 architecture presets × 3 compilers |

**Key capabilities**:
- Full automatic FULL → DIFF → HEART strategy
- Structural signature matching (`sig_base` + `tag_names`)
- Security session state machine (INIT/PLAINTEXT_SENT/DICT_READY/SECURE)
- Timestamp monotonicity detection (anti-replay)
- 71 device operation codes (TID 0x0E00–0x0E46)
- Plugin system (Transport / Test / PortForwarder)

**API levels**:

| Level | Entry function | Use case |
|-------|----------------|----------|
| Easy | `osfx_easy_encode_multi_sensor_auto()` | Arduino quick-start |
| Core | `osfx_core_encode_multi_sensor_packet_auto()` | Fine-grained control |
| Fusion | `osfx_fusion_encode()` | Custom layer integration |
| Packet | `osfx_packet_encode_full()` | Direct wire-level access |

### 4.2 OSynaptic-RX (Compact Receive Decoder)

| Property | Specification |
|----------|---------------|
| **Language standard** | C89 (avr-gcc / SDCC / IAR / XC8 compatible) |
| **Target platforms** | AVR ATtiny/ATmega, 8051, PIC, STM8, ESP, Cortex-M |
| **Zero heap** | All stack/static allocation |
| **Zero float** | Fixed-point scaled integers (÷10000) |
| **Flash footprint** | 310 B (minimal) ~ 616 B (full) |
| **RAM footprint** | 0 B (direct decode) ~ 102 B (streaming parser) |
| **Peak stack** | 41 B (direct) / 55 B (streaming) |
| **Source code** | 14 files ≈ 650 LOC |

**Dual decode paths**:

| Path | API | Use case | Extra RAM |
|------|-----|----------|-----------|
| Streaming | `osrx_feed_byte()` + `osrx_feed_done()` | UART / RS-485 | 102 B (OSRXParser) |
| Direct | `osrx_sensor_recv()` | UDP / LoRa / SPI | 0 B |

**Configuration presets**:

| Tier | RAM range | Typical MCU | Recommended config |
|------|-----------|-------------|-------------------|
| Ultra | 64–128 B | ATtiny25 | `NO_PARSER=1 NO_TIMESTAMP=1 CRC8=0 CRC16=0` |
| Tight | 128–512 B | ATtiny85, ATmega48 | `NO_PARSER=1` |
| Standard | 512 B–2 KB | ATmega328P | Default |
| Comfort | ≥ 2 KB | ESP32, STM32F4 | Full feature |

### 4.3 OSynaptic-TX (Minimal Transmit Encoder)

| Property | Specification |
|----------|---------------|
| **Language standard** | C89 |
| **Target platforms** | ATtiny25 through ESP32 full range |
| **Minimum Flash** | 2 KB (API C standalone) |
| **Minimum RAM** | 0 B (API C streaming) |
| **Minimum stack** | 21 B (API C) |
| **Source code** | 6 C files ≈ 600 LOC |
| **Unit library** | 80+ UCUM compile-time validation macros |

**Three API tiers**:

| API | Name | Peak stack | Static RAM | Flash | Notes |
|-----|------|------------|-----------|-------|-------|
| **A** | Dynamic | ~137 B | 96 B | ~600 B | Runtime sensor_id / unit |
| **B** | Static | ~51 B | 96 B | ~430 B | Compile-time template `OSTX_STATIC_DEFINE` |
| **C** | Streaming | **21 B** | **0 B** | ~760 B | Zero-buffer `ostx_stream_pack()` |

**Compile-time unit validation**:
```c
OSTX_UNIT(Cel)      // → "A01" ✓ compiles
OSTX_UNIT(Celsius)  // → undefined macro → compile error ✗
```

---

## 5. API Contracts and Alignment Matrices

### 5.1 Wire Protocol Consistency Contract

The following fields **must** be bit-for-bit identical across all implementations:

| Contract ID | Field | Offset | Encoding | Core | FX | RX | TX |
|-------------|-------|--------|----------|:----:|:--:|:--:|:--:|
| W-01 | cmd | [0] | uint8 | ✅ | ✅ | ✅ | ✅ |
| W-02 | route | [1] | uint8 = 1 | ✅ | ✅ | ✅ | ✅ |
| W-03 | aid | [2-5] | BE uint32 | ✅ | ✅ | ✅ | ✅ |
| W-04 | tid | [6] | uint8 | ✅ | ✅ | ✅ | ✅ |
| W-05 | timestamp | [7-12] | BE uint48 | ✅ | ✅ | ✅¹ | ✅² |
| W-06 | body | [13..N] | ASCII | ✅ | ✅ | ✅ | ✅ |
| W-07 | crc8 | [N+1] | CRC-8/SMBUS | ✅ | ✅ | ✅ | ✅ |
| W-08 | crc16 | [N+2..N+3] | CRC-16/CCITT BE | ✅ | ✅ | ✅ | ✅ |

¹ RX exposes only the lower 32 bits (`ts_sec`); can be disabled via config  
² TX holds the upper 2 bytes fixed at 0; effective range is uint32

### 5.2 CRC Reference Vector Contracts

| Contract ID | Algorithm | Input | Expected Output | Core | FX | RX | TX |
|-------------|-----------|-------|----------------|:----:|:--:|:--:|:--:|
| C-01 | CRC-8/SMBUS | `"123456789"` | `0xF4` | ✅ | ✅ | ✅ | ✅ |
| C-02 | CRC-16/CCITT | `"123456789"` | `0x29B1` | ✅ | ✅ | ✅ | ✅ |

### 5.3 Base62 Encode/Decode Contracts

| Contract ID | Input | Encoded Output | Core | FX | TX(enc) | RX(dec) |
|-------------|-------|---------------|:----:|:--:|:------:|:------:|
| B-01 | 0 | `"0"` | ✅ | ✅ | ✅ | ✅ |
| B-02 | 62 | `"10"` | ✅ | ✅ | ✅ | ✅ |
| B-03 | -1 | `"-1"` | ✅ | ✅ | ✅ | ✅ |
| B-04 | 215000 | `"TVK"` | ✅ | ✅ | ✅ | ✅ |
| B-05 | -123456789 | `"-8m0Kx"` | ✅ | ✅ | N/A | N/A |

### 5.4 Command Byte Contracts

| Contract ID | Name | Value | Core | FX | RX | TX |
|-------------|------|-------|:----:|:--:|:--:|:--:|
| CMD-01 | DATA_FULL | 63 | ✅ | ✅ | ✅ | ✅ |
| CMD-02 | DATA_FULL_SEC | 64 | ✅ | ✅ | — | — |
| CMD-03 | DATA_DIFF | 170 | ✅ | ✅ | — | — |
| CMD-04 | DATA_DIFF_SEC | 171 | ✅ | ✅ | — | — |
| CMD-05 | DATA_HEART | 127 | ✅ | ✅ | — | — |
| CMD-06 | DATA_HEART_SEC | 128 | ✅ | ✅ | — | — |
| CMD-07 | ID_REQUEST | 1 | ✅ | ✅ | — | — |
| CMD-08 | ID_ASSIGN | 2 | ✅ | ✅ | — | — |
| CMD-09 | PING | 9 | ✅ | ✅ | — | — |
| CMD-10 | PONG | 10 | ✅ | ✅ | — | — |
| CMD-11 | TIME_REQUEST | 11 | ✅ | ✅ | — | — |
| CMD-12 | TIME_RESPONSE | 12 | ✅ | ✅ | — | — |

### 5.5 Unit Symbol Code Contracts

All implementations **must** use the same mapping codes defined in `OS_Symbols.json`:

| Contract ID | Unit | Symbol Code | Core | FX | RX | TX |
|-------------|------|-------------|:----:|:--:|:--:|:--:|
| U-01 | K (Kelvin) | `A00` | ✅ | ✅ | ✅ | ✅ |
| U-02 | Cel (Celsius) | `A01` | ✅ | ✅ | ✅ | ✅ |
| U-03 | degF (Fahrenheit) | `A02` | ✅ | ✅ | ✅ | ✅ |
| U-04 | Pa (Pascal) | `900` | ✅ | ✅ | ✅ | ✅ |
| U-05 | % (percent) | `C00` | ✅ | ✅ | ✅ | ✅ |
| U-06 | m (metre) | `600` | ✅ | ✅ | ✅ | ✅ |
| U-07 | Hz (hertz) | `400` | ✅ | ✅ | ✅ | ✅ |
| U-08 | V (volt) | `200` | ✅ | ✅ | ✅ | ✅ |

### 5.6 Scale Factor Contracts

| Contract ID | Parameter | Value | Description |
|-------------|-----------|-------|-------------|
| S-01 | `VALUE_SCALE` | 10000 | Unified across all implementations |
| S-02 | Precision | 4 decimal places | `21.5°C → 215000` |
| S-03 | Encoding range (i32) | ±214748.3647 | TX/RX limit |
| S-04 | Encoding range (i64) | ±9.22×10¹⁴ | Core/FX limit |

---

## 6. Security Architecture

### 6.1 Secure Session State Machine

```
      ┌────────────────────────────────────────────────────────┐
      │                                                        │
      │    ┌──────┐  note_plaintext  ┌──────────────┐          │
      │    │ INIT │ ──────────────▶ │PLAINTEXT_SENT │          │
      │    └──────┘                 └──────┬───────┘          │
      │         ▲                          │                   │
      │         │                  confirm_dict                │
      │    expire/reset                    │                   │
      │         │                          ▼                   │
      │    ┌────┴────┐  mark_channel  ┌────────────┐          │
      │    │         │◀──────────────│ DICT_READY  │          │
      │    │ SECURE  │               └────────────┘          │
      │    └─────────┘                                        │
      │                                                        │
      └────────────────────────────────────────────────────────┘
```

### 6.2 Timestamp Anti-Replay

| Result | Condition | Action |
|--------|-----------|--------|
| `TS_ACCEPT` | `ts > last_data_timestamp` | Update `last_data_timestamp`, accept |
| `TS_REPLAY` | `ts == last_data_timestamp` | Reject, log warning |
| `TS_OUT_OF_ORDER` | `ts < last_data_timestamp` | Reject, log warning |

### 6.3 Handshake Dispatch Rejection Reasons

| Reason Code | Description |
|-------------|-------------|
| `MALFORMED` | Incomplete frame structure |
| `CRC` | CRC-8 or CRC-16 verification failed |
| `REPLAY` | Timestamp replay detected |
| `OUT_OF_ORDER` | Timestamp out-of-order |
| `NO_SESSION` | No established secure session |
| `UNSUPPORTED` | Unknown command type |

---

## 7. UCUM Standardization Engine

### 7.1 Supported Unit Libraries (15 categories)

| Category | Base unit | Derived unit examples |
|----------|-----------|----------------------|
| Temperature | K | Cel, degF, degRe |
| Pressure | Pa | bar, psi, mmHg, atm |
| Length | m | in, ft, yd, mi, AU |
| Mass | g | lb, oz, t, u |
| Time | s | min, h, d, wk |
| Electric current | A | — |
| Frequency | Hz | rpm, deg/s, rad/s |
| Energy / Power | W, J | cal, hp |
| Voltage / Impedance | V, Ω, F | — |
| Humidity | % | — |
| Informatics | bit, By | Bd |
| Amount of substance | mol | eq, osm |
| Luminous intensity | cd | cp, hk |
| Device operations | cmd | pow_on, pow_off, mv_up, mv_dn, ... |

### 7.2 Prefix Support

| Prefix | Factor | Example |
|--------|--------|---------|
| G | 10⁹ | GHz |
| M | 10⁶ | MPa |
| k | 10³ | kPa, kHz |
| m | 10⁻³ | mm, ms |
| u (μ) | 10⁻⁶ | uV |
| n | 10⁻⁹ | nm |
| Ki | 2¹⁰ | KiBy |
| Mi | 2²⁰ | MiBy |
| Gi | 2³⁰ | GiBy |

### 7.3 Standardization Rules

| Input unit | Input value | Standardized unit | Standardized value |
|------------|-------------|-------------------|--------------------|
| kPa | 101.325 | Pa | 101325.0 |
| degF | 77.0 | K | 298.15 |
| Cel | 25.0 | K | 298.15 |
| mmHg | 760.0 | Pa | 101325.0 |
| kHz | 1.0 | Hz | 1000.0 |

---

## 8. Performance Benchmarks

### 8.1 Core (Python 3.11 + optional Rust)

| Metric | Value |
|--------|-------|
| transmit() throughput | ~1000 pps |
| dispatch(UDP) | ~2000 pps |
| receive() decompression | ~1500 pps |
| Pipeline latency | 2–5 ms |
| Storage overhead | ~1 KB/packet |

### 8.2 FX (ESP32 @ 240 MHz)

| Metric | Value |
|--------|-------|
| FULL encode | < 1 ms |
| DIFF encode | < 0.5 ms |
| Default DRAM | ~27 KB |
| Minimum config | ~1 KB (AVR 4 entries) |

### 8.3 TX (ATmega328P @ 16 MHz)

| Metric | Value |
|--------|-------|
| Frame encode latency | ~0.6 ms |
| Throughput (115200 baud) | ~380 fps |
| API C peak stack | 21 B |
| API C minimum Flash | 2 KB |

### 8.4 RX (AVR @ 16 MHz)

| Metric | Value |
|--------|-------|
| Decode latency | < 0.5 ms |
| Flash footprint (minimal) | 310 B |
| Flash footprint (full) | 616 B |
| Streaming parser RAM | 102 B |
| Direct decode stack | 41 B |

### 8.5 Encoding Efficiency

| Mode | Typical frame size | Relative to raw JSON |
|------|--------------------|----------------------|
| FULL | 40–80 B | ~30% of original |
| DIFF | 20–40 B | ~10–15% of original |
| HEART | 15–25 B | ~5–8% of original |

---

## 9. Testing and Certification System

> See companion document: [OpenSynaptic Testing and Certification Process](OpenSynaptic_Certification_Process.md)

### 9.1 Test Matrix Overview

| Test Domain | Core | FX | RX | TX | Total |
|------------|-----:|---:|---:|---:|------:|
| CRC reference vectors | 1 | 1 | 4 | 5 | **11** |
| Base62 round-trip | 1 | 1 | 6 | 17 | **25** |
| Frame encode/decode | 1 | 2 | 11 | 19 | **33** |
| Sensor parsing | — | — | 3 | — | **3** |
| Streaming parser | — | — | 15 | — | **15** |
| Template syntax | — | 1 | — | — | **1** |
| Fusion strategy | — | 1 | — | — | **1** |
| Standardization | — | 1 | — | — | **1** |
| Handshake construction | — | 1 | — | — | **1** |
| Integration pipeline | 9 | 1 | — | — | **10** |
| Exhaustive business logic | 985 | — | — | — | **985** |
| Security infrastructure | 43 | — | — | — | **43** |
| Plugin system | 205 | — | — | — | **205** |
| Orthogonal design | 24 | — | — | — | **24** |
| **Total** | **1269** | **9** | **39** | **41** | **1358** |

### 9.2 Certification Levels

| Level | Name | Requirement | Pass Criteria |
|-------|------|-------------|---------------|
| **L1** | Wire Compatible | CRC + Base62 + frame structure reference vectors | 69/69 vectors pass |
| **L2** | Protocol Conformant | L1 + cross-implementation frame exchange | FX encode ↔ Core decode passes |
| **L3** | Fusion Certified | L2 + FULL/DIFF/HEART strategy correctness | Strategy sequence matches Core reference |
| **L4** | Security Validated | L3 + handshake/session/anti-replay | All 43 security tests pass |
| **L5** | Full Ecosystem | L4 + full exhaustive test suite | 1353/1358 (≥99.5%) |

---

## Appendices

### Appendix A: Protocol Version Compatibility

| Protocol version | Core | FX | RX | TX | Notes |
|-----------------|------|-----|-----|-----|-------|
| v1.0 | ✅ | ✅ | ✅ | ✅ | Current version |

### Appendix B: Known Design Limitations

| ID | Limitation | Scope | Disposition |
|----|------------|-------|-------------|
| KL-01 | Base62 int64 upper limit 9.22×10¹⁴ | mol = 6.022e+23 skipped | Design decision: SKIP |
| KL-02 | RX exposes only 32-bit timestamp | Overflow after year 2106 | Acceptable |
| KL-03 | TX/RX int32 range | Value domain ±214748.3647 | Covers 99% of sensor ranges |
| KL-04 | RX supports DATA_FULL decode only | No DIFF/HEART support | Design decision: minimal footprint |

### Appendix C: Glossary

| Term | Definition |
|------|-----------|
| AID | Assigned ID — 32-bit device identifier allocated by the hub |
| TID | Template/Transaction ID — template or transaction identifier |
| UCUM | Unified Code for Units of Measure — international unit coding standard |
| Fusion | Fusion Engine — FULL/DIFF/HEART strategy selection module |
| Base62 | Positional encoding system using 62-character set (0–9a–zA–Z) |
| Wire Frame | Wire-level frame — complete byte sequence representation of a binary packet |

### Appendix D: References

1. UCUM Specification: https://ucum.org/ucum
2. CRC-16/CCITT-FALSE: ITU-T V.41
3. Base64url: RFC 4648 §5
4. OpenSynaptic GitHub: https://github.com/OpenSynaptic

---

*This document is generated and maintained by the OpenSynaptic project automated certification tooling.*
