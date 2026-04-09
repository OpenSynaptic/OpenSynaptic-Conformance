# OpenSynaptic 测试与认证流程

**版本**：1.0 · 2026-04-09  
**配套文档**：[核心技术白皮书](OpenSynaptic_Technical_Whitepaper.md)  
**适用对象**：OpenSynaptic Core v1.3.x / OSynaptic-FX v1.0.x / OSynaptic-RX v1.0.x / OSynaptic-TX v1.0.x  

---

## 目录

1. [认证体系概述](#1-认证体系概述)
2. [认证等级定义](#2-认证等级定义)
3. [L1 Wire Compatible 认证](#3-l1-wire-compatible-认证)
4. [L2 Protocol Conformant 认证](#4-l2-protocol-conformant-认证)
5. [L3 Fusion Certified 认证](#5-l3-fusion-certified-认证)
6. [L4 Security Validated 认证](#6-l4-security-validated-认证)
7. [L5 Full Ecosystem 认证](#7-l5-full-ecosystem-认证)
8. [跨实现互操作性验证](#8-跨实现互操作性验证)
9. [回归测试与持续认证](#9-回归测试与持续认证)
10. [认证报告模板](#10-认证报告模板)

---

## 1. 认证体系概述

### 1.1 设计原则

OpenSynaptic 认证体系遵循以下核心原则：

1. **极端可验证**：每项认证测试均有确定性的已知答案向量（KAT），任何人可独立重现
2. **分层递进**：从位级兼容（L1）到全生态系统（L5），逐级叠加
3. **跨实现互验**：不信任自测，要求异构实现间交叉验证
4. **零假阴性**：认证测试不允许跳过或降级，仅已知设计限制可标记 SKIP
5. **自动化驱动**：所有认证测试可通过 CI/CD 自动执行

### 1.2 认证矩阵

```
┌─────────────────────────────────────────────────────────────────┐
│                     认证等级递进图                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1 Wire Compatible ──▶ L2 Protocol Conformant                 │
│       (CRC/B62/帧)          (跨实现互验)                         │
│            │                      │                              │
│            │                      ▼                              │
│            │               L3 Fusion Certified                  │
│            │                (FULL/DIFF/HEART)                    │
│            │                      │                              │
│            │                      ▼                              │
│            │               L4 Security Validated                │
│            │                (握手/会话/防重放)                     │
│            │                      │                              │
│            │                      ▼                              │
│            └──────────▶ L5 Full Ecosystem                       │
│                          (穷举/插件/正交)                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 认证适用性

| 待认证实现 | L1 | L2 | L3 | L4 | L5 |
|-----------|:--:|:--:|:--:|:--:|:--:|
| Core (Python) | 必须 | 必须 | 必须 | 必须 | 必须 |
| FX (C99) | 必须 | 必须 | 必须 | 必须 | 可选 |
| RX (C89) | 必须 | 必须 | N/A¹ | N/A | N/A |
| TX (C89) | 必须 | 必须 | N/A² | N/A | N/A |
| 第三方实现 | 必须 | 必须 | 按能力 | 按能力 | 可选 |

¹ RX 仅解码 DATA_FULL，不参与融合策略认证  
² TX 仅编码 DATA_FULL，不参与融合策略认证

---

## 2. 认证等级定义

### L1 — Wire Compatible（线级兼容）

**目标**：证明实现的基础编解码算法与协议线格式位级一致。

**通过标准**：
- 全部 CRC 参考向量通过
- 全部 Base62 参考向量通过
- 帧结构字节序验证通过
- 帧边界条件处理正确

### L2 — Protocol Conformant（协议一致）

**目标**：证明不同实现之间可以交换有效数据包。

**通过标准**：
- 实现 A 编码的帧可被实现 B 正确解码
- 所有字段提取值一致
- CRC 交叉验证通过

### L3 — Fusion Certified（融合认证）

**目标**：证明 FULL/DIFF/HEART 策略选择与模板学习行为与参考实现一致。

**通过标准**：
- 连续 N 轮发送的策略序列与 Core 参考一致
- DIFF 位掩码正确性
- HEART 模板回放一致性

### L4 — Security Validated（安全认证）

**目标**：证明安全子系统（握手、会话、ID 分配）行为正确。

**通过标准**：
- 握手状态机全路径覆盖
- 时间戳防重放功能正确
- ID 分配无冲突、租约管理正确

### L5 — Full Ecosystem（全生态认证）

**目标**：证明与 OpenSynaptic Core 的全功能等价性。

**通过标准**：
- 穷举业务逻辑测试 ≥99.5% 通过
- 插件系统功能正确
- 正交条件组合无回归

---

## 3. L1 Wire Compatible 认证

### 3.1 CRC-8/SMBUS 参考向量测试

#### 测试 L1-CRC8-01：标准检验向量

```
输入：ASCII "123456789" (9 bytes: 0x31 0x32 0x33 0x34 0x35 0x36 0x37 0x38 0x39)
参数：poly = 0x07, init = 0x00
期望：0xF4
```

**验证代码 (C)**：
```c
const uint8_t data[] = { 0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39 };
uint8_t result = crc8(data, 9, 0x07, 0x00);
ASSERT(result == 0xF4);
```

**验证代码 (Python)**：
```python
from opensynaptic.utils.security.security_core import crc8_smbus
assert crc8_smbus(b"123456789") == 0xF4
```

#### 测试 L1-CRC8-02：单字节

```
输入：0x01 (1 byte)
参数：poly = 0x07, init = 0x00
期望：0x07
```

#### 测试 L1-CRC8-03：NULL/空输入

```
输入：NULL 或长度 0
期望：返回 init 值 (0x00)，无崩溃
```

### 3.2 CRC-16/CCITT-FALSE 参考向量测试

#### 测试 L1-CRC16-01：标准检验向量

```
输入：ASCII "123456789"
参数：poly = 0x1021, init = 0xFFFF
期望：0x29B1
```

**验证代码 (C)**：
```c
const uint8_t data[] = { 0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39 };
uint16_t result = crc16(data, 9, 0x1021, 0xFFFF);
ASSERT(result == 0x29B1);
```

**验证代码 (Python)**：
```python
from opensynaptic.utils.security.security_core import crc16_ccitt
assert crc16_ccitt(b"123456789") == 0x29B1
```

#### 测试 L1-CRC16-02：单字节 0x00

```
输入：0x00 (1 byte)
参数：poly = 0x1021, init = 0xFFFF
期望：0xE1F0
```

#### 测试 L1-CRC16-03：单字节 0xFF

```
输入：0xFF (1 byte)
期望：0xFF00
```

#### 测试 L1-CRC16-04：NULL/空输入

```
输入：NULL 或长度 0
期望：返回 init 值 (0xFFFF)，无崩溃
```

### 3.3 Base62 编码参考向量测试

#### 测试 L1-B62-01 至 L1-B62-17：完整参考向量集

| 编号 | 输入值 | 期望编码 | 适用实现 |
|------|--------|---------|---------|
| L1-B62-01 | 0 | `"0"` | Core, FX, TX |
| L1-B62-02 | 1 | `"1"` | Core, FX, TX |
| L1-B62-03 | 9 | `"9"` | Core, FX, TX |
| L1-B62-04 | 10 | `"a"` | Core, FX, TX |
| L1-B62-05 | 35 | `"z"` | Core, FX, TX |
| L1-B62-06 | 36 | `"A"` | Core, FX, TX |
| L1-B62-07 | 61 | `"Z"` | Core, FX, TX |
| L1-B62-08 | 62 | `"10"` | Core, FX, TX |
| L1-B62-09 | 3843 | `"ZZ"` | Core, FX, TX |
| L1-B62-10 | 238328 | `"1000"` (=62³) | Core, FX, TX |
| L1-B62-11 | 215000 | `"TVK"` | Core, FX, TX, RX(dec) |
| L1-B62-12 | -1 | `"-1"` | Core, FX, TX |
| L1-B62-13 | -62 | `"-10"` | Core, FX, TX |
| L1-B62-14 | -61 | `"-Z"` | Core, FX, TX |
| L1-B62-15 | 2147483647 | `"2lkCB1"` | Core, FX, TX |
| L1-B62-16 | -2147483648 | `"-2lkCB2"` | Core, FX, TX |
| L1-B62-17 | -123456789 | `"-8m0Kx"` | Core, FX, TX |

### 3.4 Base62 解码参考向量测试

| 编号 | 输入字符串 | 期望值 | 适用实现 |
|------|-----------|--------|---------|
| L1-B62D-01 | `"0"` | 0 | Core, FX, RX |
| L1-B62D-02 | `"10"` | 62 | Core, FX, RX |
| L1-B62D-03 | `"-1"` | -1 | Core, FX, RX |
| L1-B62D-04 | `"TVK"` | 215000 | Core, FX, RX |
| L1-B62D-05 | `"!bad"` | ERROR (ok=0) | Core, FX, RX |
| L1-B62D-06 | NULL | ERROR (ok=0) | Core, FX, RX |

### 3.5 帧结构字节序测试

#### 测试 L1-FRAME-01：标准帧构建与字段提取

**测试输入**：
```
cmd      = 0x3F (DATA_FULL)
route    = 0x01
aid      = 0x01020304
tid      = 0x07
ts_sec   = 0x00001234  (48-bit: 0x000000001234)
body     = "T1|A01|TVK" (10 bytes)
```

**期望帧（26 字节）**：
```
字节    值 (hex)              说明
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

**验证指令**：
```c
// 帧总长
ASSERT(frame_len == 13 + 10 + 3);  // == 26

// 字节序验证
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

// Body 提取
ASSERT(memcmp(frame + 13, "T1|A01|TVK", 10) == 0);

// CRC-8 验证（仅 body 计算）
uint8_t crc8_body = crc8(frame + 13, 10, 0x07, 0x00);
ASSERT(frame[23] == crc8_body);

// CRC-16 验证（全帧 [0..23] 计算）
uint16_t crc16_all = crc16(frame, 24, 0x1021, 0xFFFF);
ASSERT(frame[24] == (crc16_all >> 8));      // high byte
ASSERT(frame[25] == (crc16_all & 0xFF));    // low byte
```

#### 测试 L1-FRAME-02：最小帧（空 body）

```
body_len = 0
期望帧长 = 13 + 0 + 3 = 16 字节
CRC-8(body={}) = init = 0x00
CRC-16 covers [0..13] (header + crc8)
```

#### 测试 L1-FRAME-03：过短帧拒绝

```
输入：长度 < 16 的字节序列
期望：解码函数返回失败（0 或负数），不产生段错误
```

#### 测试 L1-FRAME-04：NULL 输入拒绝

```
输入：packet = NULL, len = 0
期望：返回 0，不崩溃
```

### 3.6 L1 通过标准

```
┌────────────────────────────────────────────────────────────────┐
│ L1 Wire Compatible 认证通过条件                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ✅ L1-CRC8-01 至 L1-CRC8-03        全部通过（3/3）            │
│  ✅ L1-CRC16-01 至 L1-CRC16-04      全部通过（4/4）            │
│  ✅ L1-B62-01 至 L1-B62-17          全部通过（17/17）           │
│  ✅ L1-B62D-01 至 L1-B62D-06        全部通过（6/6）            │
│  ✅ L1-FRAME-01 至 L1-FRAME-04      全部通过（4/4）            │
│                                                                │
│  合计：34/34 全通过 → L1 认证通过                                │
│                                                                │
│  零容忍：任何一项失败 → L1 认证不通过                             │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. L2 Protocol Conformant 认证

### 4.1 跨实现帧交换测试

L2 认证的核心：一个实现编码的帧必须能被另一个实现正确解码。

#### 测试 L2-XENC-01：TX 编码 → Core 解码

**步骤**：
1. TX 编码以下传感器数据：
   ```
   aid=0x00010203, tid=7, ts_sec=1710000000
   sensor_id="T1", unit="A01"(Cel), scaled=215000 (21.5°C)
   ```
2. 将二进制帧传递给 Core `receive()`
3. 验证 Core 解码结果

**验证**：
```python
decoded = core_node.receive(tx_frame_bytes)
assert decoded is not None
assert decoded.get("error") is None
assert "s1_id" in decoded  # 传感器 ID 字段存在
assert "s1_v" in decoded   # 传感器值字段存在
```

#### 测试 L2-XENC-02：TX 编码 → RX 解码

**步骤**：
1. TX 使用 `ostx_sensor_pack()` 编码帧
2. RX 使用 `osrx_sensor_recv()` 解码同一帧

**验证**：
```c
// TX 端
int tx_len = ostx_sensor_pack(aid, tid, ts, "T1", "A01", 215000, tx_buf);
ASSERT(tx_len > 0);

// RX 端
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

#### 测试 L2-XENC-03：FX 编码 → Core 解码

**步骤**：
1. FX 使用 `osfx_core_encode_sensor_packet()` 编码
2. 通过 UDP/文件 传递帧字节
3. Core `receive()` 解码

**验证**：
```python
decoded = core_node.receive(fx_frame_bytes)
assert decoded is not None
assert abs(decoded["s1_v"] - expected_value) < tolerance
```

#### 测试 L2-XENC-04：FX 编码 → RX 解码

```c
// FX 编码
int fx_len = osfx_core_encode_sensor_packet(
    aid, tid, ts, "T1", 21.5, "Cel", fx_buf, sizeof(fx_buf), &pkt_len);

// RX 解码
int rx_ok = osrx_sensor_recv(fx_buf, pkt_len, &meta, &field);
ASSERT(rx_ok == 1);
ASSERT(field.scaled == 215000);  // 21.5 × 10000
```

#### 测试 L2-XENC-05：Core 编码 → FX 解码

```python
# Core 编码
packet, aid, strategy = core_node.transmit(
    sensors=[['T1', 'OK', 21.5, 'Cel']],
    device_id='TEST', device_status='ONLINE'
)
```

```c
// FX 解码
osfx_packet_meta meta;
char sid[32]; double val; char unit[24];
int ok = osfx_core_decode_sensor_packet_auto(
    &state, packet, packet_len, sid, 32, &val, unit, 24, &meta);
ASSERT(ok == 1);
// 注意：Core 可能已标准化为 K，需要逆标准化比较
```

#### 测试 L2-XENC-06：Core 编码 → RX 解码

```python
packet, _, _ = core_node.transmit(sensors=[['T1', 'OK', 21.5, 'Cel']])
# 写入文件或通过 UDP 传递
```

```c
int ok = osrx_sensor_recv(core_packet, core_len, &meta, &field);
ASSERT(ok == 1);
ASSERT(meta.crc8_ok == 1);
ASSERT(meta.crc16_ok == 1);
```

### 4.2 多传感器帧交换测试

#### 测试 L2-MULTI-01：FX 多传感器 → Core 解码

```c
osfx_core_sensor_input sensors[] = {
    { .sensor_id="T1", .sensor_state="OK", .value=21.5,   .unit="Cel" },
    { .sensor_id="H1", .sensor_state="OK", .value=55.0,   .unit="%" },
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
assert decoded["s1_id"] is not None  # 至少3个传感器
assert decoded["s2_id"] is not None
assert decoded["s3_id"] is not None
```

### 4.3 CRC 交叉验证测试

#### 测试 L2-CRC-CROSS-01：帧级 CRC 交叉

```
1. 实现 A 编码帧，提取 [crc8, crc16]
2. 实现 B 对同一帧内容重新计算 CRC
3. 验证 A.crc8 == B.crc8(body) AND A.crc16 == B.crc16(frame)
```

### 4.4 L2 通过标准

```
┌────────────────────────────────────────────────────────────────┐
│ L2 Protocol Conformant 认证通过条件                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  前置：L1 已通过                                                 │
│                                                                │
│  ✅ L2-XENC-01 至 L2-XENC-06        全部通过（6/6）            │
│  ✅ L2-MULTI-01                      通过                      │
│  ✅ L2-CRC-CROSS-01                  通过                      │
│                                                                │
│  合计：8/8 全通过 → L2 认证通过                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. L3 Fusion Certified 认证

### 5.1 策略序列一致性测试

#### 测试 L3-STRAT-01：FULL → DIFF 切换

**参考行为**（Core `target_sync_count=3`）：

| 轮次 | 温度(°C) | 期望策略 | 期望 CMD |
|------|---------|---------|---------|
| 1 | 21.0 | FULL | 63 (0x3F) |
| 2 | 21.5 | FULL | 63 |
| 3 | 22.0 | FULL | 63 |
| 4 | 22.5 | DIFF | 170 (0xAA) |
| 5 | 23.0 | DIFF | 170 |
| 6 | 23.0 | HEART | 127 (0x7F) |
| 7 | 23.0 | HEART | 127 |
| 8 | 23.5 | DIFF | 170 |

**验证**：
```c
// FX: 8 轮编码
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
# Core: 同样 8 轮
strategies = []
for i in range(8):
    pkt, _, strat = core_node.transmit(
        sensors=[['T1', 'OK', 21.0 + i * 0.5, 'Cel']])
    strategies.append(strat)
assert strategies[:3] == ['FULL_PACKET'] * 3
assert strategies[3] == 'DIFF_PACKET'
```

#### 测试 L3-STRAT-02：配置变更强制 FULL

**步骤**：
1. 发送 3 轮 [T1, Cel]，建立模板
2. 第 4 轮改为 [T1, Cel, H1, %]（增加通道）
3. 验证第 4 轮强制 FULL

**验证**：
```c
// 前 3 轮单传感器
for (int i = 0; i < 3; i++) {
    osfx_easy_encode_sensor_auto(&ctx, ts+i, "T1", 21.0+i*0.5, "Cel",
        buf, sizeof(buf), &len, &cmd);
}
// 第 4 轮多传感器 → 结构变更 → 强制 FULL
sensors[0] = (osfx_core_sensor_input){ .sensor_id="T1", .value=22.5, .unit="Cel" };
sensors[1] = (osfx_core_sensor_input){ .sensor_id="H1", .value=55.0, .unit="%" };
osfx_easy_encode_multi_sensor_auto(&ctx, ts+3, sensors, 2,
    buf, sizeof(buf), &len, &cmd);
ASSERT(cmd == 63);  // 必须是 FULL
```

### 5.2 DIFF 位掩码正确性测试

#### 测试 L3-DIFF-01：单通道变化

```
轮 1 (FULL): T1=21.0, H1=55.0, P1=101325
轮 4 (DIFF): T1=21.5, H1=55.0, P1=101325  (仅 T1 变化)

期望位掩码: 0b00000001 (bit 0 = T1 changed)
DIFF body 仅含 T1 的新 B62 值
```

#### 测试 L3-DIFF-02：多通道变化

```
轮 4 (DIFF): T1=22.0, H1=60.0, P1=101325  (T1 和 H1 变化)

期望位掩码: 0b00000011 (bit 0 = T1, bit 1 = H1)
```

### 5.3 HEART 模板回放测试

#### 测试 L3-HEART-01：值不变时自动 HEART

```
轮 3 (FULL):  T1=21.0 → 学习模板
轮 4 (DIFF):  T1=21.5 → 差异编码
轮 5 (HEART): T1=21.5 → 值未变 → 仅时间戳更新

HEART 体 = 仅时间戳 B64，无传感器字段
解码后数据 与 轮 4 一致（除时间戳外）
```

### 5.4 跨实现策略一致性测试

#### 测试 L3-CROSS-01：FX 与 Core 策略序列一致

```
使用与 L3-STRAT-01 相同的输入序列：
21.0, 21.5, 22.0, 22.5, 23.0, 23.0, 23.0, 23.5 °C

期望：FX 输出命令序列 与 Core 输出命令序列 完全一致
  [63, 63, 63, 170, 170, 127, 127, 170]
```

### 5.5 L3 通过标准

```
┌────────────────────────────────────────────────────────────────┐
│ L3 Fusion Certified 认证通过条件                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  前置：L2 已通过                                                 │
│                                                                │
│  ✅ L3-STRAT-01、L3-STRAT-02        策略序列正确（2/2）          │
│  ✅ L3-DIFF-01、L3-DIFF-02          位掩码正确（2/2）           │
│  ✅ L3-HEART-01                      模板回放正确（1/1）         │
│  ✅ FX 策略序列 == Core 策略序列      跨实现一致                  │
│                                                                │
│  合计：6/6 全通过 → L3 认证通过                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. L4 Security Validated 认证

### 6.1 握手状态机测试

#### 测试 L4-HS-01：完整握手路径

```
步骤                         期望状态
──────────────────────      ──────────────
初始化                       INIT (0)
note_plaintext_sent(aid)     PLAINTEXT_SENT (1)
confirm_dict(aid)            DICT_READY (2)
mark_channel(aid)            SECURE (3)

should_encrypt(aid)          True
get_key(aid)                 32B 非全零密钥
```

#### 测试 L4-HS-02：多 AID 独立性

```
5 个不同 AID 各自独立走完 INIT → SECURE
验证互不干扰：
  AID_A.state == SECURE 不影响 AID_B.state == INIT
```

#### 测试 L4-HS-03：会话过期

```
设 expire_seconds = 60
1. AID_X 进入 SECURE，last_seen = T
2. cleanup(now = T + 61)
3. 验证 AID_X 回退到 INIT
```

### 6.2 时间戳防重放测试

#### 测试 L4-TS-01：正常递增

```
check_and_update(aid, ts=1000) → ACCEPT
check_and_update(aid, ts=1001) → ACCEPT
check_and_update(aid, ts=1002) → ACCEPT
```

#### 测试 L4-TS-02：重放检测

```
check_and_update(aid, ts=1000) → ACCEPT
check_and_update(aid, ts=1000) → REPLAY  (相同时间戳)
```

#### 测试 L4-TS-03：乱序检测

```
check_and_update(aid, ts=1002) → ACCEPT
check_and_update(aid, ts=1001) → OUT_OF_ORDER  (更小时间戳)
```

### 6.3 ID 分配测试

#### 测试 L4-ID-01：顺序分配无重复

```
范围 [1, 9999]，连续分配 200 个 ID
验证：len(set(ids)) == 200 且 all(1 ≤ id ≤ 9999)
```

#### 测试 L4-ID-02：池耗尽

```
范围 [1, 3]，分配 4 次
前 3 次成功，第 4 次失败（返回错误码或抛异常）
```

#### 测试 L4-ID-03：租约过期回收

```
1. 分配 aid=X，lease=60s
2. 标记 offline(X)
3. cleanup(now + 61)
4. 验证 X 可被重新分配
```

#### 测试 L4-ID-04：并发分配（仅 Core/FX 网关模式）

```
20 线程同时调用 allocate()
验证：0 重复 ID，0 race condition 异常
```

### 6.4 握手分发与拒绝测试

#### 测试 L4-DISP-01：畸形帧拒绝

```
输入：长度 = 3 的帧
期望：reject = MALFORMED
```

#### 测试 L4-DISP-02：CRC 失败拒绝

```
输入：有效帧但篡改最后一字节
期望：reject = CRC
```

#### 测试 L4-DISP-03：PING → PONG 响应

```
输入：cmd=9 (PING) 的有效帧
期望：kind=CTRL, has_response=true, response[0]=10 (PONG)
```

### 6.5 L4 通过标准

```
┌────────────────────────────────────────────────────────────────┐
│ L4 Security Validated 认证通过条件                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  前置：L3 已通过（或 L2 对仅解码实现）                             │
│                                                                │
│  ✅ L4-HS-01 至 L4-HS-03          握手状态机（3/3）              │
│  ✅ L4-TS-01 至 L4-TS-03          时间戳防重放（3/3）            │
│  ✅ L4-ID-01 至 L4-ID-04          ID 分配（4/4）               │
│  ✅ L4-DISP-01 至 L4-DISP-03     握手分发（3/3）               │
│                                                                │
│  合计：13/13 全通过 → L4 认证通过                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. L5 Full Ecosystem 认证

### 7.1 穷举业务逻辑测试

参考 OpenSynaptic Core 的 `scripts/exhaustive_business_logic.py`，包含 6 个穷举套件：

#### Suite A：每单位全链路边界值（494 项）

**方法**：遍历 15 个 UCUM 库的全部单位，每个单位取 3-5 个边界值进行完整 transmit → receive 往返。

**验收标准**：
```
relative_error = |received - expected| / max(|expected|, 1e-15)
absolute_error = |received - expected|

PASS: relative_error ≤ 0.001 OR absolute_error ≤ 0.001
SKIP: |standardized_value| > 9.22e14  (Base62 int64 上限)
FAIL: 其他情况
```

**已知 SKIP（2 项）**：
- `mol = 6.022e+23`：超出 Base62 编码范围
- `AU = 1e+06`：经前缀扩展后超出范围

#### Suite B：多传感器跨类组合（350 项）

从 15 个单位库各取代表单位，组合 C(15,k) 通道数 k∈[2,8]，每种取 ≤50 组。

#### Suite C：状态字穷举矩阵（56 项）

7 种设备状态 × 8 种传感器状态 = 56 种组合。

```
设备：ONLINE, OFFLINE, WARN, ERROR, STANDBY, BOOT, MAINT
传感器：OK, WARN, ERR, FAULT, N/A, OFFLINE, OOL, TEST
```

#### Suite D：FULL→DIFF 策略递进（9 项）

同设备连续 8 轮发送（温度递增 0.5°C），验证策略序列。

#### Suite E：批量发送等价性（5 项）

`transmit_batch()` 返回数 = 输入条目数。

#### Suite F：SI 前缀全链路（71 项）

6 个十进制前缀 × 11 基础单位 + 二进制前缀 + 拒绝测试。

### 7.2 插件系统测试（205 项）

| 子套件 | 项数 | 覆盖 |
|--------|------|------|
| DatabaseManager SQLite | 14 | CRUD 操作、事务、查询 |
| PortForwarder 规则管理 | 107 | 规则 CRUD、路由匹配、持久化 |
| TestPlugin | 4 | 组件功能 |
| DisplayAPI 格式化 | 44 | 数据展示 |
| 插件注册表 | 36 | 注册/卸载/重载 |

### 7.3 安全基础设施测试（43 项）

| 子套件 | 项数 | 覆盖 |
|--------|------|------|
| ID 分配器 | 13 | 顺序/随机/去重/释放/池/并发/持久化/耗尽 |
| 握手状态机 | 12 | 全路径/多AID/角色/持久化/PING |
| 环境卫士 | 8 | 资源/错误/状态 |
| 端口转发 | 10 | 防火墙/流量/协议/代理 |

### 7.4 正交设计测试（24 项）

验证不同功能模块之间的交叉影响。

### 7.5 L5 通过标准

```
┌────────────────────────────────────────────────────────────────┐
│ L5 Full Ecosystem 认证通过条件                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  前置：L4 已通过                                                 │
│                                                                │
│  穷举业务：≥985/985 通过（SKIP ≤ 2）                             │
│  插件系统：≥205/205 通过                                         │
│  安全基础：≥43/43 通过                                           │
│  正交设计：≥24/24 通过                                           │
│                                                                │
│  总计：≥1253/1257 通过（通过率 ≥99.5%）                          │
│        SKIP 仅限已知设计限制（KL-01 等）                          │
│                                                                │
│  → L5 认证通过                                                   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 8. 跨实现互操作性验证

### 8.1 黄金帧库

每次 Core 版本发布时，生成标准化的 **黄金帧文件** 作为跨实现验证基准：

```json
{
  "version": "1.3.1",
  "generated": "2026-04-09T00:00:00Z",
  "frames": [
    {
      "test_id": "GOLDEN-001",
      "description": "单传感器 FULL 帧 (TEMP, 21.5°C)",
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
      "description": "三传感器 FULL 帧 (TEMP+HUM+PRESS)"
    },
    {
      "test_id": "GOLDEN-003",
      "description": "负数值帧 (-40°C)"
    },
    {
      "test_id": "GOLDEN-004",
      "description": "极值帧 (最大/最小 int32 缩放值)"
    }
  ]
}
```

### 8.2 验证矩阵

```
                    解码端
                Core    FX      RX
编   Core        ✅     ✅      ✅
码   FX          ✅     ✅      ✅
端   TX          ✅     ✅      ✅
```

每个单元格代表一组 L2-XENC 测试。

### 8.3 自动化互验流程

```
步骤 1: Core 生成黄金帧 → golden_frames.json
步骤 2: FX  构建时加载 golden_frames.json → 解码验证
步骤 3: TX  构建时加载 golden_frames.json → 编码验证（与期望帧比对）
步骤 4: RX  构建时加载 golden_frames.json → 解码验证
步骤 5: FX  编码帧 → Core 解码验证
步骤 6: TX  编码帧 → RX 解码验证
```

### 8.4 CI/CD 集成

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

## 9. 回归测试与持续认证

### 9.1 版本兼容性矩阵

每次子库发布新版本时，必须重新执行以下认证矩阵：

| 变更来源 | 必须重测 |
|---------|---------|
| Core 协议变更 | L1 + L2 + L3（全实现） |
| Core 安全变更 | L4（Core + FX） |
| FX API 变更 | L1 + L2（FX） |
| RX 配置变更 | L1 + L2（RX） |
| TX API 变更 | L1 + L2（TX） |
| 新增 UCUM 单位 | Suite A + Suite F 增量 |

### 9.2 认证有效性

| 认证等级 | 有效期 | 续期条件 |
|---------|--------|---------|
| L1 | 永久（不变算法） | 代码变更时自动 CI 重测 |
| L2 | 直至任一实现版本变更 | 跨实现帧交换重测 |
| L3 | Core 融合参数变更时 | 策略序列重测 |
| L4 | 安全模块变更时 | 全 43 项安全测试重测 |
| L5 | 每季度（或重大变更时） | 完整穷举套件 |

### 9.3 认证撤销条件

- 任何 L1 测试失败 → 全部认证立即撤销
- L2 跨实现测试失败 → L2 及以上撤销
- 安全漏洞发现 → L4 + L5 撤销直至修复

---

## 10. 认证报告模板

### 10.1 L1 认证报告

```
═══════════════════════════════════════════════════════════
  OpenSynaptic L1 Wire Compatible 认证报告
═══════════════════════════════════════════════════════════

  被测实现：[实现名称]
  版本：[版本号]
  测试日期：[YYYY-MM-DD]
  测试环境：[OS / 编译器 / 平台]
  参考实现：OpenSynaptic Core v1.3.1

  ─────────────────────────────────────────────────────────
  测试结果

  CRC-8/SMBUS 参考向量
    L1-CRC8-01  标准检验 (0xF4)         [PASS/FAIL]
    L1-CRC8-02  单字节 (0x07)           [PASS/FAIL]
    L1-CRC8-03  空输入安全性             [PASS/FAIL]

  CRC-16/CCITT-FALSE 参考向量
    L1-CRC16-01 标准检验 (0x29B1)       [PASS/FAIL]
    L1-CRC16-02 单字节 0x00 (0xE1F0)    [PASS/FAIL]
    L1-CRC16-03 单字节 0xFF (0xFF00)    [PASS/FAIL]
    L1-CRC16-04 空输入安全性             [PASS/FAIL]

  Base62 编码参考向量
    L1-B62-01   0 → "0"                 [PASS/FAIL]
    L1-B62-02   1 → "1"                 [PASS/FAIL]
    ...
    L1-B62-17   -123456789 → "-8m0Kx"   [PASS/FAIL/N/A]

  Base62 解码参考向量
    L1-B62D-01  "0" → 0                 [PASS/FAIL]
    ...
    L1-B62D-06  NULL → error            [PASS/FAIL]

  帧结构验证
    L1-FRAME-01 标准帧字节序             [PASS/FAIL]
    L1-FRAME-02 最小帧                   [PASS/FAIL]
    L1-FRAME-03 过短帧拒绝               [PASS/FAIL]
    L1-FRAME-04 NULL 输入拒绝            [PASS/FAIL]

  ─────────────────────────────────────────────────────────
  汇总

  通过：[N] / 34
  失败：[N] / 34
  N/A ：[N] / 34（不适用于该实现的测试项）

  认证结论：[通过 / 未通过]

  ─────────────────────────────────────────────────────────
  签章

  测试执行者：_______________
  评审者：_______________
  日期：_______________
═══════════════════════════════════════════════════════════
```

### 10.2 完整认证摘要报告

```
═══════════════════════════════════════════════════════════
  OpenSynaptic 生态系统认证摘要
═══════════════════════════════════════════════════════════

  认证日期：[YYYY-MM-DD]
  参考版本：Core v1.3.1

  实现           L1    L2    L3    L4    L5
  ─────────────  ───   ───   ───   ───   ───
  Core (Python)  ✅    ✅    ✅    ✅    ✅
  FX (C99)       ✅    ✅    ✅    ✅    N/A
  RX (C89)       ✅    ✅    N/A   N/A   N/A
  TX (C89)       ✅    ✅    N/A   N/A   N/A

  跨实现互验
  ─────────────────────────────────────────
  TX → Core    ✅  (L2-XENC-01)
  TX → RX      ✅  (L2-XENC-02)
  FX → Core    ✅  (L2-XENC-03)
  FX → RX      ✅  (L2-XENC-04)
  Core → FX    ✅  (L2-XENC-05)
  Core → RX    ✅  (L2-XENC-06)

  穷举测试统计
  ─────────────────────────────────────────
  业务逻辑：  985 / 985  (SKIP 2, 已知限制)
  安全基础：  43 / 43
  插件系统：  205 / 205
  正交设计：  24 / 24
  ─────────────────────────────────────────
  总计：     1358 / 1358  通过率 99.85%

═══════════════════════════════════════════════════════════
```

---

## 附录 A：测试执行命令速查

### Core (Python)

```bash
# L1 基础算法
cd OpenSynaptic
python -m pytest tests/unit/test_core_algorithms.py -v

# L5 穷举业务逻辑
python scripts/exhaustive_business_logic.py

# L5 安全基础设施
python scripts/exhaustive_security_infra_test.py

# L5 插件系统
python scripts/exhaustive_plugin_test.py

# 集成测试
python scripts/integration_test.py
```

### FX (C99)

```bash
cd OSynaptic-FX
cmake -B build -DOSFX_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=MinSizeRel
cmake --build build
ctest --test-dir build --output-on-failure
```

**交叉编译** (ESP32 示例)：
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
# 期望输出：39 passed, 0 failed
```

**最小配置测试**：
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
# 期望输出：50 passed, 0 failed
```

---

## 附录 B：认证工具链要求

| 工具 | 最低版本 | 用途 |
|------|---------|------|
| Python | 3.11 | Core 测试运行 |
| pytest | 7.0 | 单元测试框架 |
| CMake | 3.15 | FX/RX/TX 构建 |
| GCC | 9.0 | C89/C99 编译 |
| Clang | 12.0 | 可选编译器 |
| MSVC | 2019 | Windows 构建 |
| avr-gcc | 7.0 | AVR 交叉编译（可选） |
| arm-none-eabi-gcc | 10.0 | Cortex-M 交叉编译（可选） |

---

## 附录 C：认证测试唯一标识符索引

| 测试 ID | 等级 | 类别 | 简述 |
|---------|------|------|------|
| L1-CRC8-01 | L1 | CRC | 标准检验向量 0xF4 |
| L1-CRC8-02 | L1 | CRC | 单字节 0x07 |
| L1-CRC8-03 | L1 | CRC | 空输入安全 |
| L1-CRC16-01 | L1 | CRC | 标准检验向量 0x29B1 |
| L1-CRC16-02 | L1 | CRC | 单字节 0x00 → 0xE1F0 |
| L1-CRC16-03 | L1 | CRC | 单字节 0xFF → 0xFF00 |
| L1-CRC16-04 | L1 | CRC | 空输入安全 |
| L1-B62-01~17 | L1 | Base62 | 编码参考向量 |
| L1-B62D-01~06 | L1 | Base62 | 解码参考向量 |
| L1-FRAME-01 | L1 | 帧 | 标准帧字节序 |
| L1-FRAME-02 | L1 | 帧 | 最小帧 |
| L1-FRAME-03 | L1 | 帧 | 过短帧拒绝 |
| L1-FRAME-04 | L1 | 帧 | NULL 输入 |
| L2-XENC-01~06 | L2 | 互验 | 跨实现帧交换 |
| L2-MULTI-01 | L2 | 互验 | 多传感器帧交换 |
| L2-CRC-CROSS-01 | L2 | 互验 | CRC 交叉验证 |
| L3-STRAT-01~02 | L3 | 融合 | 策略序列 |
| L3-DIFF-01~02 | L3 | 融合 | DIFF 位掩码 |
| L3-HEART-01 | L3 | 融合 | HEART 回放 |
| L4-HS-01~03 | L4 | 安全 | 握手状态机 |
| L4-TS-01~03 | L4 | 安全 | 时间戳防重放 |
| L4-ID-01~04 | L4 | 安全 | ID 分配 |
| L4-DISP-01~03 | L4 | 安全 | 握手分发 |

---

*本文档由 OpenSynaptic 项目自动化认证工具生成和维护。*
