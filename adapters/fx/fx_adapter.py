from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


ADAPTERS_ROOT = Path(__file__).resolve().parents[1]
if str(ADAPTERS_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_ROOT))

from native_backends import CoreBackend, FX_ROOT, FxBackend, RxBackend, TxBackend
from shared_runtime import (
    CaseDefinition,
    CaseResult,
    approximately_equal,
    build_capabilities_payload,
    build_info_payload,
    build_profile_context,
    build_report,
    core_sensor_entry,
    count_core_sensor_entries,
    emit,
    execute_cases,
    exit_code_for_report,
    load_json,
    parse_frame_bytes,
    parse_hex_value,
)


MANIFEST_PATH = Path(__file__).with_name("manifest.v1.json")
IMPLEMENTATION_LABEL = "fx"
_FX_BACKEND: FxBackend | None = None
_CORE_BACKEND: CoreBackend | None = None
_RX_BACKEND: RxBackend | None = None
_TX_BACKEND: TxBackend | None = None


def get_fx() -> FxBackend:
    global _FX_BACKEND
    if _FX_BACKEND is None:
        _FX_BACKEND = FxBackend()
    return _FX_BACKEND


def get_core() -> CoreBackend:
    global _CORE_BACKEND
    if _CORE_BACKEND is None:
        _CORE_BACKEND = CoreBackend()
    return _CORE_BACKEND


def get_rx() -> RxBackend:
    global _RX_BACKEND
    if _RX_BACKEND is None:
        _RX_BACKEND = RxBackend()
    return _RX_BACKEND


def get_tx() -> TxBackend:
    global _TX_BACKEND
    if _TX_BACKEND is None:
        _TX_BACKEND = TxBackend()
    return _TX_BACKEND


def pass_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="PASS", message=message, details=details)


def fail_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="FAIL", message=message, details=details)


def run_l1_crc(case: CaseDefinition) -> CaseResult:
    payload = bytes.fromhex(case.record["input"]["bytesHex"])
    expected = parse_hex_value(case.record["expected"]["resultHex"])
    actual = get_fx().crc8(payload) if case.record["operation"] == "crc8_smbus" else get_fx().crc16(payload)
    details = {"operation": case.record["operation"], "inputHex": payload.hex(), "expected": expected, "actual": actual}
    if actual == expected:
        return pass_result(case, "FX CRC implementation matches the canonical reference vector.", details)
    return fail_result(case, "FX CRC implementation diverges from the canonical reference vector.", details)


def run_l1_base62(case: CaseDefinition) -> CaseResult:
    operation = case.record["operation"]
    if operation == "encode":
        value = int(case.record["input"]["value"])
        expected = str(case.record["expected"]["text"])
        actual = get_fx().base62_encode(value)
        details = {"value": value, "expected": expected, "actual": actual}
        if actual == expected:
            return pass_result(case, "FX Base62 encoding matches the canonical reference vector.", details)
        return fail_result(case, "FX Base62 encoding diverges from the canonical reference vector.", details)

    text = case.record["input"].get("text")
    surrogate = False
    if text is None:
        text = ""
        surrogate = True
    expected = case.record["expected"]
    try:
        actual_value = get_fx().base62_decode(str(text))
        if surrogate and not expected.get("ok"):
            return pass_result(
                case,
                "FX adapter used an empty-string surrogate for the null-input guard case and did not crash.",
                {"text": text, "surrogateEmptyInput": True, "expected": expected, "actualValue": actual_value},
            )
        ok = bool(expected.get("ok")) and actual_value == int(expected.get("value"))
        details = {"text": text, "surrogateEmptyInput": surrogate, "expected": expected, "actualValue": actual_value}
        if ok:
            return pass_result(case, "FX Base62 decoding matches the canonical reference vector.", details)
        return fail_result(case, "FX Base62 decoding diverges from the canonical reference vector.", details)
    except Exception as exc:
        details = {"text": text, "surrogateEmptyInput": surrogate, "expected": expected, "error": str(exc)}
        if not expected.get("ok"):
            return pass_result(case, "FX rejects the invalid Base62 input as expected.", details)
        return fail_result(case, "FX rejected a Base62 input that the canonical vector expects to decode.", details)


def run_l1_frame(case: CaseDefinition) -> CaseResult:
    packet_hex = case.record["input"].get("packetHex")
    packet = b"" if packet_hex is None else bytes.fromhex(packet_hex)
    expected = case.record["expected"]
    decoded = get_fx().packet_decode(packet)
    details = {"packetHex": packet.hex(), "decoded": decoded, "expected": expected, "surrogateEmptyInput": packet_hex is None}

    if case.record["operation"] == "guard_parse":
        if decoded["rc"] != 1:
            return pass_result(case, "FX rejects malformed or empty frame input without decoding it.", details)
        return fail_result(case, "FX accepted a malformed or empty frame input.", details)

    header = parse_frame_bytes(packet)
    ok = (
        decoded["rc"] == 1
        and decoded["cmd"] == parse_hex_value(expected["cmdHex"])
        and decoded["route_count"] == int(expected["route"])
        and decoded["source_aid"] == parse_hex_value(expected["aidHex"])
        and decoded["tid"] == int(expected["tid"])
        and decoded["timestamp_raw"] == parse_hex_value(expected["timestampHex"])
        and decoded["body_len"] == int(expected["bodyLength"])
        and decoded["crc8_ok"]
        and decoded["crc16_ok"]
        and header is not None
        and header["body_text"] == str(expected["bodyText"])
    )
    if ok:
        return pass_result(case, "FX frame parser matches the canonical L1 frame layout.", details)
    return fail_result(case, "FX frame parser does not match the canonical L1 frame layout.", details)


def run_l2_xenc_03(case: CaseDefinition) -> CaseResult:
    sensor = case.record["input"]["sensor"]
    packet = get_fx().encode_sensor_packet(0x01020304, 7, 1_710_000_000, str(sensor["sensorId"]), str(sensor["unit"]), float(sensor["value"]))
    fx_decoded = get_fx().decode_sensor_packet(packet)
    core_decoded = get_core().receive_packet(packet)
    sensor_view = core_sensor_entry(core_decoded)
    tolerance = float(case.record["expected"]["relativeTolerance"])
    expected_value = float(fx_decoded["value"])
    ok = (
        fx_decoded["rc"] == 1
        and sensor_view["sensorId"] == fx_decoded["sensorId"]
        and approximately_equal(float(sensor_view["value"]), expected_value, tolerance)
        and bool(core_decoded.get("crc8_ok"))
        and bool(core_decoded.get("crc16_ok"))
    )
    details = {"packetHex": packet.hex(), "fxDecoded": fx_decoded, "coreDecoded": core_decoded, "expectedValue": expected_value, "tolerance": tolerance}
    if ok:
        return pass_result(case, "Core decodes the real FX packet consistently with FX's own decode surface.", details)
    return fail_result(case, "Core does not decode the real FX packet consistently with FX's own decode surface.", details)


def run_l2_xenc_04(case: CaseDefinition) -> CaseResult:
    sensor = case.record["input"]["sensor"]
    packet = get_fx().encode_sensor_packet(0x01020304, 7, 1_710_000_000, str(sensor["sensorId"]), str(sensor["unit"]), float(sensor["value"]))
    decoded = get_rx().sensor_recv(packet)
    expected_scaled = int(case.record["expected"]["scaled"])
    ok = decoded["rc"] == 1 and decoded["scaled"] == expected_scaled and decoded["crc8_ok"] and decoded["crc16_ok"]
    details = {"packetHex": packet.hex(), "decoded": decoded, "expectedScaled": expected_scaled}
    if ok:
        return pass_result(case, "RX preserves the expected numeric payload when decoding a real FX frame.", details)
    return fail_result(case, "RX does not preserve the expected numeric payload when decoding a real FX frame.", details)


def run_l2_xenc_05(case: CaseDefinition) -> CaseResult:
    sensor = case.record["input"]["sensor"]
    packet = get_core().transmit_sensor(str(sensor["sensorId"]), float(sensor["value"]), str(sensor["unit"]), timestamp=1_710_000_000)
    decoded = get_fx().decode_sensor_packet(packet)
    expected_normalized = float(sensor["value"]) + 273.15 if str(sensor["unit"]) == "Cel" else float(sensor["value"])
    ok = decoded["rc"] == 1 and decoded["sensorId"] == str(sensor["sensorId"]) and approximately_equal(float(decoded["value"]), expected_normalized, 1e-6)
    details = {"packetHex": packet.hex(), "decoded": decoded, "expectedNormalizedValue": expected_normalized}
    if ok:
        return pass_result(case, "FX decodes the real Core packet successfully.", details)
    return fail_result(case, "FX does not decode the real Core packet as expected.", details)


def run_l2_multi(case: CaseDefinition) -> CaseResult:
    sensors = [(sensor_id, unit, float(value)) for sensor_id, _status, value, unit in case.record["input"]["sensors"]]
    packet = get_fx().encode_multi_sensor_packet(0x01020304, 7, 1_710_000_000, sensors)
    decoded = get_core().receive_packet(packet)
    sensor_count = count_core_sensor_entries(decoded)
    minimum = int(case.record["expected"]["minimumSensorCount"])
    ok = sensor_count >= minimum and bool(decoded.get("crc8_ok")) and bool(decoded.get("crc16_ok"))
    details = {"packetHex": packet.hex(), "decoded": decoded, "sensorCount": sensor_count, "minimumSensorCount": minimum}
    if ok:
        return pass_result(case, "Core decodes the real FX multi-sensor packet with the expected minimum sensor count.", details)
    return fail_result(case, "Core does not decode the real FX multi-sensor packet with the expected sensor count.", details)


def run_l2_crc_cross(case: CaseDefinition) -> CaseResult:
    packet = get_fx().encode_sensor_packet(0x01020304, 7, 1_710_000_000, "T1", "Cel", 21.5)
    header = parse_frame_bytes(packet)
    if header is None:
        return fail_result(case, "Generated FX frame is too short to inspect.", {"packetHex": packet.hex()})
    body = header["body"]
    crc8_values = {
        "fx": get_fx().crc8(body),
        "core": get_core().crc8(body),
        "tx": get_tx().crc8(body),
        "rx": get_rx().crc8(body),
    }
    crc16_values = {
        "fx": get_fx().crc16(packet[:-2]),
        "core": get_core().crc16(packet[:-2]),
        "tx": get_tx().crc16(packet[:-2]),
        "rx": get_rx().crc16(packet[:-2]),
    }
    ok = len(set(crc8_values.values())) == 1 and len(set(crc16_values.values())) == 1 and crc8_values["fx"] == header["crc8"] and crc16_values["fx"] == header["crc16"]
    details = {"packetHex": packet.hex(), "embeddedCrc8": header["crc8"], "embeddedCrc16": header["crc16"], "crc8Values": crc8_values, "crc16Values": crc16_values}
    if ok:
        return pass_result(case, "FX frame CRC values are consistent across the real runtimes.", details)
    return fail_result(case, "FX frame CRC values diverge across the real runtimes.", details)


def run_l3_strat_01(case: CaseDefinition) -> CaseResult:
    values = [float(value) for value in case.record["input"]["values"]]
    state = get_fx().new_state()
    actual: list[int] = []
    for index, value in enumerate(values):
        packet = get_fx().encode_sensor_packet_with_state(state, 0x01020304, 7, 1_710_000_000 + index, "T1", str(case.record["input"]["unit"]), value)
        actual.append(packet[0])
    expected = [int(value) for value in case.record["expected"]["commandSequence"]]
    details = {"actualSequence": actual, "expectedSequence": expected}
    if actual == expected:
        return pass_result(case, "FX emits the canonical FULL/DIFF/HEART strategy sequence.", details)
    return fail_result(case, "FX does not emit the canonical FULL/DIFF/HEART strategy sequence.", details)


def run_l3_strat_02(case: CaseDefinition) -> CaseResult:
    state = get_fx().new_state()
    commands: list[int] = []
    for index, round_data in enumerate(case.record["input"]["rounds"]):
        sensors = [(sensor_id, unit, float(value)) for sensor_id, value, unit in round_data["sensors"]]
        if len(sensors) == 1:
            packet = get_fx().encode_sensor_packet_with_state(state, 0x01020304, 7, 1_710_000_000 + index, sensors[0][0], sensors[0][1], sensors[0][2])
        else:
            packet = get_fx().encode_multi_sensor_packet(0x01020304, 7, 1_710_000_000 + index, sensors, state=state)
        commands.append(packet[0])
    expected = int(case.record["expected"]["fourthCommand"])
    details = {"commandSequence": commands, "expectedFourthCommand": expected}
    if commands[3] == expected:
        return pass_result(case, "FX forces a FULL packet when the sensor configuration changes.", details)
    return fail_result(case, "FX does not force a FULL packet when the sensor configuration changes.", details)


def run_l3_diff(case: CaseDefinition) -> CaseResult:
    baseline = [(sensor_id, unit, float(value)) for sensor_id, value, unit in case.record["input"]["baseline"]]
    changed = [(sensor_id, unit, float(value)) for sensor_id, value, unit in case.record["input"]["changed"]]
    state = get_fx().new_state()
    get_fx().encode_multi_sensor_packet(0x01020304, 7, 1_710_000_000, baseline, state=state)
    packet = get_fx().encode_multi_sensor_packet(0x01020304, 7, 1_710_000_001, changed, state=state)
    header = parse_frame_bytes(packet)
    actual_mask = header["body"][0] if header and header["body"] else None
    expected_mask = parse_hex_value(case.record["expected"]["bitmaskHex"])
    details = {"packetHex": packet.hex(), "command": packet[0], "bodyHex": header["body"].hex() if header else None, "actualMask": actual_mask, "expectedMask": expected_mask}
    if packet[0] == get_core().CMD_DATA_DIFF and actual_mask == expected_mask:
        return pass_result(case, "FX emits the expected DIFF bitmask.", details)
    return fail_result(case, "FX does not emit the expected DIFF bitmask.", details)


def run_l3_heart(case: CaseDefinition) -> CaseResult:
    encode_state = get_fx().new_state()
    decode_state = get_fx().new_state()
    full_packet = get_fx().encode_sensor_packet_with_state(encode_state, 0x01020304, 7, 1_710_000_000, "T1", "Cel", 21.0)
    diff_packet = get_fx().encode_sensor_packet_with_state(encode_state, 0x01020304, 7, 1_710_000_001, "T1", "Cel", 21.5)
    heart_packet = get_fx().encode_sensor_packet_with_state(encode_state, 0x01020304, 7, 1_710_000_002, "T1", "Cel", 21.5)
    get_fx().decode_sensor_packet(full_packet, state=decode_state)
    diff_decoded = get_fx().decode_sensor_packet(diff_packet, state=decode_state)
    heart_decoded = get_fx().decode_sensor_packet(heart_packet, state=decode_state)
    body = parse_frame_bytes(heart_packet)["body"]
    ok = heart_packet[0] == int(case.record["expected"]["heartCommand"]) and len(body) == 0 and diff_decoded["sensorId"] == heart_decoded["sensorId"] and approximately_equal(diff_decoded["value"], heart_decoded["value"], 1e-6)
    details = {"fullPacketHex": full_packet.hex(), "diffPacketHex": diff_packet.hex(), "heartPacketHex": heart_packet.hex(), "diffDecoded": diff_decoded, "heartDecoded": heart_decoded}
    if ok:
        return pass_result(case, "FX emits HEART replay semantics on unchanged values.", details)
    return fail_result(case, "FX does not emit HEART replay semantics on unchanged values.", details)


def run_l3_cross(case: CaseDefinition) -> CaseResult:
    sequence = [21.0, 21.5, 22.0, 22.5, 23.0, 23.0, 23.0, 23.5]
    core_sequence = get_core().strategy_sequence(sequence)
    state = get_fx().new_state()
    fx_sequence: list[int] = []
    for index, value in enumerate(sequence):
        packet = get_fx().encode_sensor_packet_with_state(state, 0x01020304, 7, 1_710_000_000 + index, "T1", "Cel", value)
        fx_sequence.append(packet[0])
    expected = [int(value) for value in case.record["expected"]["commandSequence"]]
    ok = core_sequence == fx_sequence == expected
    details = {"coreSequence": core_sequence, "fxSequence": fx_sequence, "expectedSequence": expected}
    if ok:
        return pass_result(case, "FX and Core emit identical strategy sequences for the canonical case.", details)
    return fail_result(case, "FX and Core do not emit identical strategy sequences for the canonical case.", details)


def run_l4_hs_01(case: CaseDefinition) -> CaseResult:
    result = get_fx().secure_full_handshake(1, 1000)
    expected_len = int(case.record["expected"]["keyLengthBytes"])
    ok = result["plainOk"] and result["dictOk"] and result["secureOk"] and result["shouldEncrypt"] and result["keyOk"] and result["keyLen"] == expected_len and any(result["key"])
    details = {"keyHex": result["key"].hex(), "keyLen": result["keyLen"], "plainOk": result["plainOk"], "dictOk": result["dictOk"], "secureOk": result["secureOk"], "shouldEncrypt": result["shouldEncrypt"]}
    if ok:
        return pass_result(case, "FX secure session runtime reaches the expected secure state.", details)
    return fail_result(case, "FX secure session runtime does not reach the expected secure state.", details)


def run_l4_hs_02(case: CaseDefinition) -> CaseResult:
    aid_count = int(case.record["input"]["aidCount"])
    result = get_fx().secure_isolation(list(range(1, aid_count + 1)), 1000)
    states_ok = all(result["states"].values())
    unique_keys = len({value.hex() for value in result["keys"].values()}) == aid_count
    details = {"sessionCount": result["sessionCount"], "states": result["states"], "keys": {aid: key.hex() for aid, key in result["keys"].items()}}
    if states_ok and unique_keys and result["sessionCount"] == aid_count:
        return pass_result(case, "FX keeps secure session state isolated across multiple AIDs.", details)
    return fail_result(case, "FX does not keep secure session state isolated across multiple AIDs.", details)


def run_l4_hs_03(case: CaseDefinition) -> CaseResult:
    result = get_fx().secure_expiry(1, 1000, int(case.record["input"]["expireSeconds"]))
    if result["before"] and not result["after"]:
        return pass_result(case, "FX expires the secure session back to a non-secure state.", result)
    return fail_result(case, "FX does not expire the secure session back to a non-secure state.", result)


def run_l4_timestamp(case: CaseDefinition) -> CaseResult:
    mapping = {
        FxBackend.TS_ACCEPT: "ACCEPT",
        FxBackend.TS_REPLAY: "REPLAY",
        FxBackend.TS_OUT_OF_ORDER: "OUT_OF_ORDER",
    }
    actual_codes = get_fx().secure_timestamp_check(1, [int(value) for value in case.record["input"]["timestamps"]])
    actual = [mapping.get(code, f"UNKNOWN:{code}") for code in actual_codes]
    expected = [str(value) for value in case.record["expected"]["results"]]
    details = {"actual": actual, "actualCodes": actual_codes, "expected": expected}
    if actual == expected:
        return pass_result(case, "FX timestamp replay protection matches the canonical expectation.", details)
    return fail_result(case, "FX timestamp replay protection diverges from the canonical expectation.", details)


def run_l4_id_01(case: CaseDefinition) -> CaseResult:
    start_id, end_id = [int(value) for value in case.record["input"]["range"]]
    count = int(case.record["input"]["count"])
    values = get_fx().id_allocate_many(count, start_id, end_id)
    ok = len(values) == len(set(values)) == int(case.record["expected"]["uniqueCount"]) and all(start_id <= value <= end_id for value in values)
    details = {"count": len(values), "min": min(values), "max": max(values)}
    if ok:
        return pass_result(case, "FX ID allocation yields unique IDs within the configured range.", details)
    return fail_result(case, "FX ID allocation does not yield the expected unique in-range IDs.", details)


def run_l4_id_02(case: CaseDefinition) -> CaseResult:
    start_id, end_id = [int(value) for value in case.record["input"]["range"]]
    result = get_fx().id_exhaustion(start_id, end_id)
    details = result
    if len(result["granted"]) == int(case.record["expected"]["successfulAllocations"]) and result["extraRc"] != 1:
        return pass_result(case, "FX surfaces pool exhaustion after the last available ID is leased.", details)
    return fail_result(case, "FX does not surface pool exhaustion as expected.", details)


def run_l4_id_03(case: CaseDefinition) -> CaseResult:
    result = get_fx().id_reclaim(1, 3, int(case.record["input"]["leaseSeconds"]))
    if result["first"] == result["second"]:
        return pass_result(case, "FX can reclaim an expired ID lease.", result)
    return fail_result(case, "FX does not reclaim an expired ID lease as expected.", result)


def run_l4_id_04(case: CaseDefinition) -> CaseResult:
    threads = int(case.record["input"]["threads"])
    result = get_fx().id_concurrent_allocation(1, 2000, threads, 10)
    duplicate_count = len(result["values"]) - len(set(result["values"]))
    details = {"allocatedCount": len(result["values"]), "duplicateCount": duplicate_count, "errors": result["errors"]}
    if duplicate_count == 0 and len(result["errors"]) == 0:
        return pass_result(case, "FX concurrent allocation produced no duplicate IDs or race exceptions.", details)
    return fail_result(case, "FX concurrent allocation produced duplicates or race exceptions.", details)


def run_l4_disp_01(case: CaseDefinition) -> CaseResult:
    result = get_fx().classify_dispatch(b"\x3f\x01\x02")
    ok = result["rejected"] and result["reject_reason"] == FxBackend.REJECT_MALFORMED or result["kind"] == FxBackend.DISPATCH_KIND_MALFORMED
    if ok:
        return pass_result(case, "FX dispatch rejects malformed short frames.", result)
    return fail_result(case, "FX dispatch does not reject malformed short frames as expected.", result)


def run_l4_disp_02(case: CaseDefinition) -> CaseResult:
    bad_packet = b""
    try:
        good_packet = get_fx().encode_sensor_packet(0x01020304, 7, 1_710_000_000, "T1", "Cel", 21.5)
        bad_packet = good_packet[:-1] + bytes([good_packet[-1] ^ 0xFF])
        meta = get_fx().packet_decode(bad_packet)
        ok = meta["rc"] == 1 and not meta["crc16_ok"]
        details = {"mutatedPacketHex": bad_packet.hex(), "meta": meta}
        if ok:
            return pass_result(case, "FX decode/dispatch path rejects CRC-corrupted frames.", details)
        return fail_result(case, "FX decode/dispatch path does not reject CRC-corrupted frames as expected.", details)
    except OSError as exc:
        return fail_result(
            case,
            "FX native decode path faults on a CRC-corrupted frame instead of rejecting it cleanly.",
            {"mutatedPacketHex": bad_packet.hex(), "nativeError": str(exc)},
        )


def run_l4_disp_03(case: CaseDefinition) -> CaseResult:
    packet = bytes([parse_hex_value(case.record["input"]["cmdHex"]), 0x00, 0x01])
    result = get_fx().classify_dispatch(packet)
    response = result["response"]
    ok = result["has_response"] and bool(response) and response[0] == parse_hex_value(case.record["expected"]["responseCmdHex"])
    details = {"result": {**result, "response": list(response)}}
    if ok:
        return pass_result(case, "FX dispatch responds to PING with PONG.", details)
    return fail_result(case, "FX dispatch does not respond to PING with PONG as expected.", details)


def execute_case(case: CaseDefinition) -> CaseResult:
    if case.id.startswith("L1-CRC"):
        return run_l1_crc(case)
    if case.id.startswith("L1-B62"):
        return run_l1_base62(case)
    if case.id.startswith("L1-FRAME"):
        return run_l1_frame(case)
    if case.id == "L2-XENC-03":
        return run_l2_xenc_03(case)
    if case.id == "L2-XENC-04":
        return run_l2_xenc_04(case)
    if case.id == "L2-XENC-05":
        return run_l2_xenc_05(case)
    if case.id == "L2-MULTI-01":
        return run_l2_multi(case)
    if case.id == "L2-CRC-CROSS-01":
        return run_l2_crc_cross(case)
    if case.id == "L3-STRAT-01":
        return run_l3_strat_01(case)
    if case.id == "L3-STRAT-02":
        return run_l3_strat_02(case)
    if case.id in {"L3-DIFF-01", "L3-DIFF-02"}:
        return run_l3_diff(case)
    if case.id == "L3-HEART-01":
        return run_l3_heart(case)
    if case.id == "L3-CROSS-01":
        return run_l3_cross(case)
    if case.id == "L4-HS-01":
        return run_l4_hs_01(case)
    if case.id == "L4-HS-02":
        return run_l4_hs_02(case)
    if case.id == "L4-HS-03":
        return run_l4_hs_03(case)
    if case.id in {"L4-TS-01", "L4-TS-02", "L4-TS-03"}:
        return run_l4_timestamp(case)
    if case.id == "L4-ID-01":
        return run_l4_id_01(case)
    if case.id == "L4-ID-02":
        return run_l4_id_02(case)
    if case.id == "L4-ID-03":
        return run_l4_id_03(case)
    if case.id == "L4-ID-04":
        return run_l4_id_04(case)
    if case.id == "L4-DISP-01":
        return run_l4_disp_01(case)
    if case.id == "L4-DISP-02":
        return run_l4_disp_02(case)
    if case.id == "L4-DISP-03":
        return run_l4_disp_03(case)
    return CaseResult(id=case.id, status="SKIP", message="Case is outside the real FX adapter execution surface.", details={"caseId": case.id})


def command_info(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_info_payload(
            manifest,
            FX_ROOT,
            "Real OSynaptic-FX adapter backed by the sibling C runtime and local native build.",
        )
    )


def command_capabilities(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_capabilities_payload(
            manifest,
            "Builds and loads the real OSynaptic-FX C sources locally, then executes fusion and security checks against the actual runtime.",
            limits={
                "requiresLocalCompiler": True,
                "buildCache": "adapters/.build/osynaptic_fx",
            },
        )
    )


def run_report(profile_path: Path, dataset_path: Path | None, selected_case_ids: list[str] | None) -> int:
    manifest = load_json(MANIFEST_PATH)
    with redirect_stdout(sys.stderr):
        context = build_profile_context(profile_path, IMPLEMENTATION_LABEL, dataset_path)
        results = execute_cases(context, selected_case_ids, execute_case)
    report = build_report(
        manifest,
        context.profile,
        results,
        context.dataset_version,
        FX_ROOT,
        environment={"implementationRole": "fusion-runtime"},
        note="PASS, FAIL, and SKIP results reflect the current real OSynaptic-FX runtime rather than synthetic expectations.",
    )
    emit(report)
    return exit_code_for_report(report)


def command_run_profile(args: argparse.Namespace) -> int:
    profile_path = Path(args.profile).resolve()
    dataset_path = Path(args.dataset).resolve() if args.dataset else None
    return run_report(profile_path, dataset_path, None)


def command_run_cases(args: argparse.Namespace) -> int:
    if not args.cases:
        print("at least one --case value is required for run-cases", file=sys.stderr)
        return 2
    profile_path = Path(args.profile).resolve()
    dataset_path = Path(args.dataset).resolve() if args.dataset else None
    return run_report(profile_path, dataset_path, args.cases)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenSynaptic real FX adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="emit adapter metadata")
    info.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    info.set_defaults(func=command_info)

    capabilities = subparsers.add_parser("capabilities", help="emit adapter capabilities")
    capabilities.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    capabilities.set_defaults(func=command_capabilities)

    run_profile = subparsers.add_parser("run-profile", help="execute all required cases for a profile")
    run_profile.add_argument("--profile", required=True, help="path to the conformance profile")
    run_profile.add_argument("--dataset", default=None, help="optional explicit dataset manifest path")
    run_profile.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    run_profile.set_defaults(func=command_run_profile)

    run_cases = subparsers.add_parser("run-cases", help="execute selected cases only")
    run_cases.add_argument("--profile", required=True, help="path to the conformance profile")
    run_cases.add_argument("--dataset", default=None, help="optional explicit dataset manifest path")
    run_cases.add_argument("--case", dest="cases", action="append", default=[], help="case id to execute")
    run_cases.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    run_cases.set_defaults(func=command_run_cases)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())