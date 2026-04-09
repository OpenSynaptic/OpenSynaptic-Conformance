# OpenSynaptic 核心技术白皮书

**版本**：1.0 · 2026-04-09  
**适用范围**：OpenSynaptic v1.3.x / OSynaptic-FX v1.0.x / OSynaptic-RX v1.0.x / OSynaptic-TX v1.0.x  
**分级**：公开技术文档  

---

## 摘要

OpenSynaptic 是面向物联网传感器网络的高性能协议栈，实现 **2-N-2 拓扑**（多发送器 → 中枢 → 多接收器）架构。协议核心提供五层处理管道：标准化（UCUM）、压缩（Base62）、融合编码（FULL/DIFF/HEART）、安全传输及持久化存储。其嵌入式卫星库 **FX**（Full-eXperience 编码器）、**RX**（精简接收解码器）、**TX**（极简发送编码器）覆盖从 ATtiny25（2 KB Flash / 128 B RAM）到 ESP32（520 KB SRAM）的全谱系 MCU 平台。

本白皮书定义了 OpenSynaptic 生态系统的核心协议规范、跨平台 API 合约、完整认证矩阵，以及可独立重现的验证流程。

---

## 目录

1. [系统架构](#1-系统架构)
2. [线协议规范](#2-线协议规范)
3. [核心算法](#3-核心算法)
4. [卫星库技术规格](#4-卫星库技术规格)
5. [API 合约与对齐矩阵](#5-api-合约与对齐矩阵)
6. [安全架构](#6-安全架构)
7. [UCUM 标准化引擎](#7-ucum-标准化引擎)
8. [性能基准](#8-性能基准)
9. [测试与认证体系](#9-测试与认证体系)
10. [附录](#附录)

---

## 1. 系统架构

### 1.1 全局拓扑

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

### 1.2 编码层次与数据流

| 阶段 | 输入 | 输出 | 模块 |
|------|------|------|------|
| **L1 采集** | 传感器原始读数 | `[sid, state, value, unit]` 数组 | 用户应用层 |
| **L2 标准化** | 用户单位+数值 | UCUM 规范单位+SI 基值 | `OpenSynapticStandardizer` |
| **L3 压缩** | 标准化 Fact JSON | Base62 紧凑字符串 | `OpenSynapticEngine` |
| **L4 融合编码** | Base62 字符串 | 二进制帧（13B 头 + 体 + 3B CRC） | `OSVisualFusionEngine` |
| **L5 传输** | 二进制帧 | 网络/物理层投递 | `TransportManager` |

### 1.3 组件职责矩阵

| 能力 | Core (Python) | FX (C99) | RX (C89) | TX (C89) |
|------|:---:|:---:|:---:|:---:|
| UCUM 标准化 | ✅ 15库完整 | ✅ 50+单位 | ✖ | ✖ |
| Base62 编码 | ✅ i64 | ✅ i64 | ✖ | ✅ i32 |
| Base62 解码 | ✅ i64 | ✅ i64 | ✅ i32 | ✖ |
| FULL 编码 | ✅ | ✅ | ✖ | ✅ |
| DIFF 编码 | ✅ | ✅ | ✖ | ✖ |
| HEART 编码 | ✅ | ✅ | ✖ | ✖ |
| FULL 解码 | ✅ | ✅ | ✅ | ✖ |
| DIFF 解码 | ✅ | ✅ | ✖ | ✖ |
| HEART 解码 | ✅ | ✅ | ✖ | ✖ |
| CRC-8 (body) | ✅ | ✅ | ✅ | ✅ |
| CRC-16/CCITT | ✅ | ✅ | ✅ | ✅ |
| ID 分配 | ✅ 自适应租约 | ✅ 自适应租约 | ✖ | ✖ |
| 安全会话 | ✅ AES-128 | ✅ XOR+TSCheck | ✖ | ✖ |
| 握手控制面 | ✅ 14种CMD | ✅ 14种CMD | ✖ | ✖ |
| 多传输驱动 | ✅ UDP/TCP/QUIC/UART/CAN/LoRa/BLE | ✅ 协议矩阵 | ✖ | ✖ |
| 插件系统 | ✅ 6种插件 | ✅ 3种插件 | ✖ | ✖ |
| 存储后端 | ✅ SQLite/MySQL/PG | ✅ LittleFS | ✖ | ✖ |
| REST API | ✅ | ✖ | ✖ | ✖ |
| TUI/Web UI | ✅ | ✖ | ✖ | ✖ |

---

## 2. 线协议规范

### 2.1 帧结构

```
偏移   字段        长度   编码       说明
────   ─────      ────   ────       ────
[0]    cmd         1B    uint8      命令字节
[1]    route       1B    uint8      路由计数（固定=1）
[2-5]  aid         4B    BE uint32  发送端分配ID
[6]    tid         1B    uint8      模板/事务ID
[7-12] timestamp   6B    BE uint48  Unix时间戳（秒或毫秒）
[13..N] body       var   ASCII/B62  有效载荷
[N+1]  crc8        1B    uint8      CRC-8(body)
[N+2..N+3] crc16   2B    BE uint16  CRC-16(全帧[0..N+1])
```

**最小帧**：16 字节（空 body + CRC）  
**最大帧**：由 `PACKET_MAX` 决定（默认 96B RX / 256B FX / 无限 Core）

### 2.2 命令字节定义

#### 数据命令（6种）

| 字节值 | 符号 | 说明 |
|--------|------|------|
| `0x3F` (63) | `DATA_FULL` | 完整字段帧（明文） |
| `0x40` (64) | `DATA_FULL_SEC` | 完整字段帧（加密） |
| `0xAA` (170) | `DATA_DIFF` | 增量更新帧（明文） |
| `0xAB` (171) | `DATA_DIFF_SEC` | 增量更新帧（加密） |
| `0x7F` (127) | `DATA_HEART` | 心跳帧（明文） |
| `0x80` (128) | `DATA_HEART_SEC` | 心跳帧（加密） |

#### 控制命令（12种）

| 字节值 | 符号 | 方向 | 说明 |
|--------|------|------|------|
| 1 | `ID_REQUEST` | C→S | 请求分配 AID |
| 2 | `ID_ASSIGN` | S→C | 分配 AID + 时间戳 |
| 3 | `ID_POOL_REQ` | GW→S | 批量 ID 请求 |
| 4 | `ID_POOL_RES` | S→GW | 批量 ID 响应 |
| 5 | `HANDSHAKE_ACK` | S→C | 握手确认 |
| 6 | `HANDSHAKE_NACK` | S→C | 握手拒绝 |
| 9 | `PING` | 双向 | 心跳探测 |
| 10 | `PONG` | 双向 | 心跳响应 |
| 11 | `TIME_REQUEST` | C→S | 时间同步请求 |
| 12 | `TIME_RESPONSE` | S→C | 时间同步响应 |
| 13 | `SECURE_DICT_READY` | C→S | 安全字典就绪 |
| 14 | `SECURE_CHANNEL_ACK` | S→C | 安全通道确认 |

### 2.3 FULL 数据体格式

模板语法（管道分隔）：
```
{NodeID}.{NodeState}.{TS_B64}|{SID}>U.{UnitCode}:{B62Value}|...
```

**字段说明**：
- `NodeID`：节点标识（≤31字符）
- `NodeState`：设备状态码（`U`=ONLINE, 每种状态1字符映射）
- `TS_B64`：6字节时间戳的 Base64url 编码（8字符，无填充）
- `SID`：传感器标识（≤8字符）
- `UnitCode`：OS_Symbols.json 定义的3位符号码（如 `A01`=Cel）
- `B62Value`：Base62 编码的缩放整数值（`value × 10000`）

**示例**：
```
NODE01.U.AAAAABI0|TEMP>U.A01:TVK|HUM>U.C00:1rq|
```

### 2.4 DIFF 数据体格式

```
偏移       字段           说明
────       ─────         ────
[0..K]     TS_B64        更新后的时间戳
[K+1]      bitmask       位掩码（第i位=1表示第i通道有变化）
[K+2..]    changed[]     变化字段序列：[len:1B][b62_value:varB]
```

**压缩比**：相对 FULL 节省 70-80%

### 2.5 HEART 数据体格式

```
[0..K]     TS_B64        仅更新时间戳，其余字段回放缓存模板
```

### 2.6 CRC 校验规范

| 算法 | 多项式 | 初始值 | 校验范围 | 参考向量 |
|------|--------|--------|----------|----------|
| CRC-8/SMBUS | `0x07` | `0x00` | body only | `"123456789"` → `0xF4` |
| CRC-16/CCITT-FALSE | `0x1021` | `0xFFFF` | 全帧 `[0..crc8]` | `"123456789"` → `0x29B1` |

### 2.7 策略选择算法

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

## 3. 核心算法

### 3.1 Base62 编解码

**字符集**：`0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ`（索引 0-61）

**编码算法**（i64 → string）：
```
输入：有符号 64 位整数 v
输出：Base62 字符串 s

1. 若 v < 0：输出 '-'，v = |v|
2. 若 v == 0：输出 "0"，返回
3. digits = []
4. while v > 0:
       digits.append(CHARSET[v % 62])
       v = v / 62
5. s = reverse(digits)
```

**编码范围**：
- Core (Python)：±9.22×10¹⁸（int64）
- FX (C99)：±4.61×10¹⁸（int64，63位符号量级）
- TX/RX (C89)：±2.15×10⁹（int32）

**精度缩放**：`scaled_value = round(real_value × SCALE_FACTOR)`
- SCALE_FACTOR = 10000（Core + FX + TX + RX 统一）
- 有效精度 = 4 位小数

### 3.2 CRC-8 位循环实现

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

**Flash 成本**：~72 B（无查找表，适合 ATtiny 级 MCU）

### 3.3 CRC-16/CCITT 位循环实现

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

### 3.4 Base64url 时间戳编码

将 48 位 Unix 时间戳编码为 8 字符 Base64url 字符串（无填充）。

字符集：`A-Z a-z 0-9 - _`（RFC 4648 §5）

### 3.5 融合状态机

```
                    ┌──────────────┐
                    │   UNKNOWN    │
                    │ (无模板缓存) │
                    └──────┬───────┘
                           │ 首次 FULL 包
                           ▼
                    ┌──────────────┐
                    │   LEARNING   │◀──── 配置变更
                    │ sync_count<N │
                    └──────┬───────┘
                           │ sync_count ≥ N
                           ▼
              ┌────────────────────────┐
              │       TRACKING         │
              │ 模板已学习，差异追踪    │
              └───────┬────────┬───────┘
                      │        │
        值有变化       │        │  所有值相同
                      ▼        ▼
               ┌──────────┐ ┌──────────┐
               │   DIFF   │ │  HEART   │
               │ 增量编码  │ │ 仅时间戳  │
               └──────────┘ └──────────┘
```

---

## 4. 卫星库技术规格

### 4.1 OSynaptic-FX（Full-eXperience 嵌入式编码器）

| 属性 | 规格 |
|------|------|
| **语言标准** | C99（无 C++ 依赖） |
| **目标平台** | ESP32, STM32, RP2040, RISC-V, AVR, Cortex-M, Linux |
| **默认 RAM** | ~27 KB DRAM（ESP32 完整配置） |
| **源代码** | 28 个 C 文件 + 3000 行生成数据 ≈ 11,500 LOC |
| **分层架构** | Easy API → Core Facade → Fusion Engine → Protocol Core → Security → Runtime |
| **传输驱动** | UDP / TCP / UART / CAN，协议矩阵自动选择 |
| **存储后端** | 可插拔：默认 FILE_IO / LittleFS / 自定义 |
| **Arduino 支持** | Library Manager 一键安装 |
| **CMake 构建** | 9种架构预设 × 3种编译器 |

**关键能力**：
- 完整 FULL → DIFF → HEART 自动策略
- 结构签名匹配（`sig_base` + `tag_names`）
- 安全会话状态机（INIT/PLAINTEXT_SENT/DICT_READY/SECURE）
- 时间戳单调性检测（防重放）
- 71 种设备操作码（TID 0x0E00-0x0E46）
- 插件系统（Transport / Test / PortForwarder）

**API 层级**：

| 层级 | 入口函数 | 适用场景 |
|------|---------|---------|
| Easy | `osfx_easy_encode_multi_sensor_auto()` | Arduino 快速上手 |
| Core | `osfx_core_encode_multi_sensor_packet_auto()` | 精细控制 |
| Fusion | `osfx_fusion_encode()` | 自定义层接入 |
| Packet | `osfx_packet_encode_full()` | 直接线级操作 |

### 4.2 OSynaptic-RX（精简接收解码器）

| 属性 | 规格 |
|------|------|
| **语言标准** | C89（avr-gcc / SDCC / IAR / XC8 兼容） |
| **目标平台** | AVR ATtiny/ATmega, 8051, PIC, STM8, ESP, Cortex-M |
| **零堆分配** | 全部栈/静态分配 |
| **零浮点** | 定点缩放整数（÷10000） |
| **Flash 占用** | 310 B（最小）~ 616 B（完整） |
| **RAM 占用** | 0 B（直接解码）~ 102 B（流式解析器） |
| **栈峰值** | 41 B（直接）/ 55 B（流式） |
| **源代码** | 14 个文件 ≈ 650 LOC |

**双解码路径**：

| 路径 | API | 适用场景 | 额外 RAM |
|------|-----|---------|---------|
| 流式 | `osrx_feed_byte()` + `osrx_feed_done()` | UART / RS-485 | 102 B（OSRXParser） |
| 直接 | `osrx_sensor_recv()` | UDP / LoRa / SPI | 0 B |

**配置预设**：

| 等级 | RAM 范围 | 典型 MCU | 推荐配置 |
|------|---------|---------|---------|
| Ultra | 64-128 B | ATtiny25 | `NO_PARSER=1 NO_TIMESTAMP=1 CRC8=0 CRC16=0` |
| Tight | 128-512 B | ATtiny85, ATmega48 | `NO_PARSER=1` |
| Standard | 512 B-2 KB | ATmega328P | 默认配置 |
| Comfort | ≥2 KB | ESP32, STM32F4 | 全功能 |

### 4.3 OSynaptic-TX（极简发送编码器）

| 属性 | 规格 |
|------|------|
| **语言标准** | C89 |
| **目标平台** | ATtiny25 ~ ESP32 全覆盖 |
| **最小 Flash** | 2 KB（API C 单独） |
| **最小 RAM** | 0 B（API C 流式） |
| **最小栈** | 21 B（API C） |
| **源代码** | 6 个 C 文件 ≈ 600 LOC |
| **单位库** | 80+ UCUM 编译时验证宏 |

**三档 API**：

| API | 名称 | 栈峰值 | 静态 RAM | Flash | 特点 |
|-----|------|--------|---------|-------|------|
| **A** | 动态 | ~137 B | 96 B | ~600 B | 运行时 sensor_id / unit |
| **B** | 静态 | ~51 B | 96 B | ~430 B | 编译时模板 `OSTX_STATIC_DEFINE` |
| **C** | 流式 | **21 B** | **0 B** | ~760 B | 零缓冲 `ostx_stream_pack()` |

**编译时单位验证**：
```c
OSTX_UNIT(Cel)      // → "A01" ✓ 编译通过
OSTX_UNIT(Celsius)  // → 未定义宏 → 编译错误 ✗
```

---

## 5. API 合约与对齐矩阵

### 5.1 线协议一致性合约

以下字段在所有实现中 **必须** 位级一致：

| 合约编号 | 字段 | 偏移 | 编码 | Core | FX | RX | TX |
|---------|------|------|------|:----:|:--:|:--:|:--:|
| W-01 | cmd | [0] | uint8 | ✅ | ✅ | ✅ | ✅ |
| W-02 | route | [1] | uint8 = 1 | ✅ | ✅ | ✅ | ✅ |
| W-03 | aid | [2-5] | BE uint32 | ✅ | ✅ | ✅ | ✅ |
| W-04 | tid | [6] | uint8 | ✅ | ✅ | ✅ | ✅ |
| W-05 | timestamp | [7-12] | BE uint48 | ✅ | ✅ | ✅¹ | ✅² |
| W-06 | body | [13..N] | ASCII | ✅ | ✅ | ✅ | ✅ |
| W-07 | crc8 | [N+1] | CRC-8/SMBUS | ✅ | ✅ | ✅ | ✅ |
| W-08 | crc16 | [N+2..N+3] | CRC-16/CCITT BE | ✅ | ✅ | ✅ | ✅ |

¹ RX 仅暴露低 32 位（`ts_sec`），可配置关闭  
² TX 上 2 字节固定为 0，有效范围 uint32

### 5.2 CRC 参考向量合约

| 合约编号 | 算法 | 输入 | 期望输出 | Core | FX | RX | TX |
|---------|------|------|----------|:----:|:--:|:--:|:--:|
| C-01 | CRC-8/SMBUS | `"123456789"` | `0xF4` | ✅ | ✅ | ✅ | ✅ |
| C-02 | CRC-16/CCITT | `"123456789"` | `0x29B1` | ✅ | ✅ | ✅ | ✅ |

### 5.3 Base62 编解码合约

| 合约编号 | 输入值 | 编码输出 | Core | FX | TX(enc) | RX(dec) |
|---------|--------|---------|:----:|:--:|:------:|:------:|
| B-01 | 0 | `"0"` | ✅ | ✅ | ✅ | ✅ |
| B-02 | 62 | `"10"` | ✅ | ✅ | ✅ | ✅ |
| B-03 | -1 | `"-1"` | ✅ | ✅ | ✅ | ✅ |
| B-04 | 215000 | `"TVK"` | ✅ | ✅ | ✅ | ✅ |
| B-05 | -123456789 | `"-8m0Kx"` | ✅ | ✅ | N/A | N/A |

### 5.4 命令字节合约

| 合约编号 | 命名 | 值 | Core | FX | RX | TX |
|---------|------|---|:----:|:--:|:--:|:--:|
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

### 5.5 单位符号码合约

所有实现 **必须** 使用 `OS_Symbols.json` 定义的相同映射码：

| 合约编号 | 单位 | 符号码 | Core | FX | RX | TX |
|---------|------|--------|:----:|:--:|:--:|:--:|
| U-01 | K (开尔文) | `A00` | ✅ | ✅ | ✅ | ✅ |
| U-02 | Cel (摄氏度) | `A01` | ✅ | ✅ | ✅ | ✅ |
| U-03 | degF (华氏度) | `A02` | ✅ | ✅ | ✅ | ✅ |
| U-04 | Pa (帕斯卡) | `900` | ✅ | ✅ | ✅ | ✅ |
| U-05 | % (百分比) | `C00` | ✅ | ✅ | ✅ | ✅ |
| U-06 | m (米) | `600` | ✅ | ✅ | ✅ | ✅ |
| U-07 | Hz (赫兹) | `400` | ✅ | ✅ | ✅ | ✅ |
| U-08 | V (伏特) | `200` | ✅ | ✅ | ✅ | ✅ |

### 5.6 缩放因子合约

| 合约编号 | 参数 | 值 | 说明 |
|---------|------|---|------|
| S-01 | `VALUE_SCALE` | 10000 | 所有实现统一 |
| S-02 | 精度 | 4位小数 | `21.5°C → 215000` |
| S-03 | 编码范围 (i32) | ±214748.3647 | TX/RX 限制 |
| S-04 | 编码范围 (i64) | ±9.22×10¹⁴ | Core/FX 限制 |

---

## 6. 安全架构

### 6.1 安全会话状态机

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

### 6.2 时间戳防重放

| 检查结果 | 条件 | 动作 |
|---------|------|------|
| `TS_ACCEPT` | `ts > last_data_timestamp` | 更新 `last_data_timestamp`，放行 |
| `TS_REPLAY` | `ts == last_data_timestamp` | 拒绝，记录告警 |
| `TS_OUT_OF_ORDER` | `ts < last_data_timestamp` | 拒绝，记录告警 |

### 6.3 握手分发拒绝原因

| 原因码 | 说明 |
|--------|------|
| `MALFORMED` | 帧结构不完整 |
| `CRC` | CRC-8 或 CRC-16 校验失败 |
| `REPLAY` | 时间戳重放检测 |
| `OUT_OF_ORDER` | 时间戳乱序 |
| `NO_SESSION` | 无已建立的安全会话 |
| `UNSUPPORTED` | 未知命令类型 |

---

## 7. UCUM 标准化引擎

### 7.1 支持的单位库（15类）

| 类别 | 基础单位 | 派生单位示例 |
|------|---------|-------------|
| 温度 | K | Cel, degF, degRe |
| 压力 | Pa | bar, psi, mmHg, atm |
| 长度 | m | in, ft, yd, mi, AU |
| 质量 | g | lb, oz, t, u |
| 时间 | s | min, h, d, wk |
| 电流 | A | — |
| 频率 | Hz | rpm, deg/s, rad/s |
| 能量/功率 | W, J | cal, hp |
| 电压/阻抗 | V, Ω, F | — |
| 湿度 | % | — |
| 信息学 | bit, By | Bd |
| 物质量 | mol | eq, osm |
| 发光强度 | cd | cp, hk |
| 设备操作 | cmd | pow_on, pow_off, mv_up, mv_dn, ... |

### 7.2 前缀支持

| 前缀 | 因子 | 示例 |
|------|------|------|
| G | 10⁹ | GHz |
| M | 10⁶ | MPa |
| k | 10³ | kPa, kHz |
| m | 10⁻³ | mm, ms |
| u (μ) | 10⁻⁶ | uV |
| n | 10⁻⁹ | nm |
| Ki | 2¹⁰ | KiBy |
| Mi | 2²⁰ | MiBy |
| Gi | 2³⁰ | GiBy |

### 7.3 标准化规则

| 输入单位 | 输入值 | 标准化单位 | 标准化值 |
|---------|--------|-----------|---------|
| kPa | 101.325 | Pa | 101325.0 |
| degF | 77.0 | K | 298.15 |
| Cel | 25.0 | K | 298.15 |
| mmHg | 760.0 | Pa | 101325.0 |
| kHz | 1.0 | Hz | 1000.0 |

---

## 8. 性能基准

### 8.1 Core（Python 3.11 + 可选 Rust）

| 指标 | 数值 |
|------|------|
| transmit() 吞吐 | ~1000 pps |
| dispatch(UDP) | ~2000 pps |
| receive() 解压 | ~1500 pps |
| 管道延迟 | 2-5 ms |
| 存储开销 | ~1 KB/packet |

### 8.2 FX（ESP32 @ 240 MHz）

| 指标 | 数值 |
|------|------|
| FULL 编码 | <1 ms |
| DIFF 编码 | <0.5 ms |
| 默认 DRAM | ~27 KB |
| 最小配置 | ~1 KB（AVR 4 entries） |

### 8.3 TX（ATmega328P @ 16 MHz）

| 指标 | 数值 |
|------|------|
| 帧编码延迟 | ~0.6 ms |
| 传输速率 (115200 baud) | ~380 fps |
| API C 栈峰值 | 21 B |
| API C 最小 Flash | 2 KB |

### 8.4 RX（AVR @ 16 MHz）

| 指标 | 数值 |
|------|------|
| 解码延迟 | <0.5 ms |
| Flash 占用（最小） | 310 B |
| Flash 占用（完整） | 616 B |
| 流式解析器 RAM | 102 B |
| 直接解码栈 | 41 B |

### 8.5 编码效率

| 模式 | 典型帧大小 | 相对原始 JSON |
|------|-----------|-------------|
| FULL | 40-80 B | ~30% 原始大小 |
| DIFF | 20-40 B | ~10-15% 原始大小 |
| HEART | 15-25 B | ~5-8% 原始大小 |

---

## 9. 测试与认证体系

> 详见配套文档：[OpenSynaptic 测试与认证流程](OpenSynaptic_Certification_Process.md)

### 9.1 测试矩阵总览

| 测试域 | Core | FX | RX | TX | 总计 |
|--------|-----:|----:|----:|----:|-----:|
| CRC 参考向量 | 1 | 1 | 4 | 5 | **11** |
| Base62 往返 | 1 | 1 | 6 | 17 | **25** |
| 帧编解码 | 1 | 2 | 11 | 19 | **33** |
| 传感器解析 | — | — | 3 | — | **3** |
| 流式解析器 | — | — | 15 | — | **15** |
| 模板语法 | — | 1 | — | — | **1** |
| 融合状态 | — | 1 | — | — | **1** |
| 标准化 | — | 1 | — | — | **1** |
| 握手构建 | — | 1 | — | — | **1** |
| 集成管道 | 9 | 1 | — | — | **10** |
| 穷举业务 | 985 | — | — | — | **985** |
| 安全基础 | 43 | — | — | — | **43** |
| 插件系统 | 205 | — | — | — | **205** |
| 正交设计 | 24 | — | — | — | **24** |
| **合计** | **1269** | **9** | **39** | **41** | **1358** |

### 9.2 认证等级

| 等级 | 名称 | 要求 | 通过标准 |
|------|------|------|---------|
| **L1** | Wire Compatible | CRC + Base62 + 帧结构参考向量 | 69/69 向量全通过 |
| **L2** | Protocol Conformant | L1 + 跨实现帧交换互验 | FX 编码 ↔ Core 解码通过 |
| **L3** | Fusion Certified | L2 + FULL/DIFF/HEART 策略正确性 | 策略序列与 Core 参考一致 |
| **L4** | Security Validated | L3 + 握手/会话/防重放 | 43 项安全测试全通过 |
| **L5** | Full Ecosystem | L4 + 全穷举测试套件 | 1353/1358（≥99.5%） |

---

## 附录

### 附录 A：协议版本兼容性

| 协议版本 | Core | FX | RX | TX | 说明 |
|---------|------|-----|-----|-----|------|
| v1.0 | ✅ | ✅ | ✅ | ✅ | 当前版本 |

### 附录 B：已知设计限制

| 编号 | 限制 | 影响范围 | 处置 |
|------|------|---------|------|
| KL-01 | Base62 int64 上限 9.22×10¹⁴ | mol=6.022e+23 被跳过 | 设计决策：SKIP |
| KL-02 | RX 仅暴露 32 位时间戳 | 2106 年后溢出 | 可接受 |
| KL-03 | TX/RX int32 范围 | 值域 ±214748.3647 | 覆盖 99% 传感器量程 |
| KL-04 | RX 仅支持 DATA_FULL 解码 | 无 DIFF/HEART | 设计决策：最小足迹 |

### 附录 C：术语表

| 术语 | 定义 |
|------|------|
| AID | Assigned ID，由中枢分配的 32 位设备标识 |
| TID | Template/Transaction ID，模板或事务标识 |
| UCUM | Unified Code for Units of Measure，国际通用计量单位规范 |
| Fusion | 融合引擎，FULL/DIFF/HEART 策略选择模块 |
| Base62 | 使用 62 字符集（0-9a-zA-Z）的位置编码系统 |
| Wire Frame | 线级帧，二进制数据包的完整字节序列表示 |

### 附录 D：参考文献

1. UCUM 规范：https://ucum.org/ucum
2. CRC-16/CCITT-FALSE：ITU-T V.41
3. Base64url：RFC 4648 §5
4. OpenSynaptic GitHub：https://github.com/OpenSynaptic

---

*本文档由 OpenSynaptic 项目自动化认证工具生成和维护。*
