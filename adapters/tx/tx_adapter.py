from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


ADAPTERS_ROOT = Path(__file__).resolve().parents[1]
if str(ADAPTERS_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_ROOT))

from native_backends import CoreBackend, RxBackend, TX_ROOT, TxBackend
from shared_runtime import (
    CaseDefinition,
    CaseResult,
    build_capabilities_payload,
    build_info_payload,
    build_profile_context,
    build_report,
    core_sensor_entry,
    emit,
    execute_cases,
    exit_code_for_report,
    load_json,
    parse_frame_bytes,
    parse_hex_value,
)


MANIFEST_PATH = Path(__file__).with_name("manifest.v1.json")
IMPLEMENTATION_LABEL = "tx"
_TX_BACKEND: TxBackend | None = None
_RX_BACKEND: RxBackend | None = None
_CORE_BACKEND: CoreBackend | None = None


def get_tx() -> TxBackend:
    global _TX_BACKEND
    if _TX_BACKEND is None:
        _TX_BACKEND = TxBackend()
    return _TX_BACKEND


def get_rx() -> RxBackend:
    global _RX_BACKEND
    if _RX_BACKEND is None:
        _RX_BACKEND = RxBackend()
    return _RX_BACKEND


def get_core() -> CoreBackend:
    global _CORE_BACKEND
    if _CORE_BACKEND is None:
        _CORE_BACKEND = CoreBackend()
    return _CORE_BACKEND


def pass_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="PASS", message=message, details=details)


def fail_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="FAIL", message=message, details=details)


def run_l1_crc(case: CaseDefinition) -> CaseResult:
    payload = bytes.fromhex(case.record["input"]["bytesHex"])
    expected = parse_hex_value(case.record["expected"]["resultHex"])
    if case.record["operation"] == "crc8_smbus":
        actual = get_tx().crc8(payload)
    else:
        actual = get_tx().crc16(payload)
    details = {
        "operation": case.record["operation"],
        "inputHex": payload.hex(),
        "expected": expected,
        "actual": actual,
    }
    if actual == expected:
        return pass_result(case, "TX CRC implementation matches the canonical reference vector.", details)
    return fail_result(case, "TX CRC implementation diverges from the canonical reference vector.", details)


def run_l1_base62(case: CaseDefinition) -> CaseResult:
    value = int(case.record["input"]["value"])
    expected = str(case.record["expected"]["text"])
    actual = get_tx().base62_encode(value)
    details = {
        "value": value,
        "expected": expected,
        "actual": actual,
    }
    if actual == expected:
        return pass_result(case, "TX Base62 encoding matches the canonical reference vector.", details)
    return fail_result(case, "TX Base62 encoding diverges from the canonical reference vector.", details)


def run_l1_frame(case: CaseDefinition) -> CaseResult:
    operation = case.record["operation"]
    if operation == "guard_parse":
        return CaseResult(
            id=case.id,
            status="SKIP",
            message="TX does not expose decode-side guard parsing behavior.",
            details={"operation": operation, "reason": "producer-only implementation"},
        )

    input_packet = bytes.fromhex(case.record["input"]["packetHex"])
    expected = case.record["expected"]
    header = parse_frame_bytes(input_packet)
    if header is None:
        return fail_result(case, "Canonical frame could not be parsed by the adapter harness.", {"packetHex": input_packet.hex()})

    try:
        rebuilt = get_tx().packet_build(
            header["cmd"],
            header["aid"],
            header["tid"],
            header["timestamp_raw"],
            header["body"],
        )
    except RuntimeError as exc:
        return fail_result(
            case,
            "TX packet builder could not reproduce the canonical L1 frame.",
            {"packetHex": input_packet.hex(), "error": str(exc), "expected": expected},
        )
    actual = parse_frame_bytes(rebuilt)
    details = {
        "expectedPacketHex": input_packet.hex(),
        "actualPacketHex": rebuilt.hex(),
        "actualHeader": actual,
    }
    if rebuilt == input_packet and actual is not None and actual["crc8"] == parse_hex_value(expected["crc8Hex"]) and actual["crc16"] == parse_hex_value(expected["crc16Hex"]):
        return pass_result(case, "TX frame assembly reproduces the canonical L1 packet exactly.", details)
    return fail_result(case, "TX frame assembly does not reproduce the canonical L1 packet.", details)


def run_l2_xenc_01(case: CaseDefinition) -> CaseResult:
    input_data = case.record["input"]
    sensor = input_data["sensor"]
    packet = get_tx().sensor_pack(
        parse_hex_value(input_data["aidHex"]),
        int(input_data["tid"]),
        int(input_data["tsSec"]),
        str(sensor["sensorId"]),
        str(sensor["unit"]),
        int(sensor["scaled"]),
    )
    decoded = get_core().receive_packet(packet)
    sensor_view = core_sensor_entry(decoded)
    packet_meta = decoded.get("__packet_meta__", {})
    expected_value = int(sensor["scaled"]) / 10000.0
    ok = (
        packet_meta.get("cmd") == parse_hex_value(case.record["expected"]["cmdHex"])
        and packet_meta.get("source_aid") == parse_hex_value(case.record["expected"]["aidHex"])
        and int(packet_meta.get("tid", "0"), 16) == int(case.record["expected"]["tid"])
        and sensor_view["sensorId"] == case.record["expected"]["sensorId"]
        and str(sensor_view["unit"]).lower() == "cel"
        and abs(float(sensor_view["value"]) - expected_value) <= 1e-6
        and bool(packet_meta.get("crc8_ok"))
        and bool(packet_meta.get("crc16_ok"))
    )
    details = {
        "packetHex": packet.hex(),
        "decoded": decoded,
        "expectedScaled": int(sensor["scaled"]),
        "normalizedExpectedValue": expected_value,
    }
    if ok:
        return pass_result(case, "TX-produced packet is decoded successfully by the real Core runtime.", details)
    return fail_result(case, "TX-produced packet does not decode to the expected semantic payload in Core.", details)


def run_l2_xenc_02(case: CaseDefinition) -> CaseResult:
    input_data = case.record["input"]
    sensor = input_data["sensor"]
    packet = get_tx().sensor_pack(
        parse_hex_value(input_data["aidHex"]),
        int(input_data["tid"]),
        int(input_data["tsSec"]),
        str(sensor["sensorId"]),
        str(sensor["unit"]),
        int(sensor["scaled"]),
    )
    decoded = get_rx().sensor_recv(packet)
    expected = case.record["expected"]
    ok = (
        decoded["rc"] == 1
        and decoded["cmd"] == parse_hex_value(expected["cmdHex"])
        and decoded["source_aid"] == parse_hex_value(expected["aidHex"])
        and decoded["tid"] == int(expected["tid"])
        and decoded["sensorId"] == str(expected["sensorId"])
        and decoded["unit"] == str(expected["unit"])
        and decoded["scaled"] == int(expected["scaled"])
        and decoded["crc8_ok"]
        and decoded["crc16_ok"]
    )
    details = {
        "packetHex": packet.hex(),
        "decoded": decoded,
        "expected": expected,
    }
    if ok:
        return pass_result(case, "TX-produced packet is decoded successfully by the real RX runtime.", details)
    return fail_result(case, "TX-produced packet does not decode to the expected semantic payload in RX.", details)


def run_l2_crc_cross(case: CaseDefinition) -> CaseResult:
    packet = get_tx().sensor_pack(0x00010203, 7, 1_710_000_000, "T1", "A01", 215000)
    meta = get_rx().packet_decode(packet)
    if meta["rc"] != 1:
        return fail_result(case, "Generated TX frame could not be decoded by RX metadata parsing.", {"packetHex": packet.hex(), "meta": meta})
    body_start = int(meta["body_offset"])
    body_end = body_start + int(meta["body_len"])
    body = packet[body_start:body_end]
    crc8_values = {
        "tx": get_tx().crc8(body),
        "rx": get_rx().crc8(body),
        "core": get_core().crc8(body),
    }
    crc16_values = {
        "tx": get_tx().crc16(packet[:-2]),
        "rx": get_rx().crc16(packet[:-2]),
        "core": get_core().crc16(packet[:-2]),
    }
    ok = len(set(crc8_values.values())) == 1 and len(set(crc16_values.values())) == 1 and meta["crc8_ok"] and meta["crc16_ok"]
    details = {
        "packetHex": packet.hex(),
        "rxMeta": meta,
        "crc8Values": crc8_values,
        "crc16Values": crc16_values,
    }
    if ok:
        return pass_result(case, "TX frame CRC values are consistent across real TX, RX, and Core implementations.", details)
    return fail_result(case, "Cross-runtime CRC verification diverges on a TX-produced frame.", details)


def execute_case(case: CaseDefinition) -> CaseResult:
    if case.id.startswith("L1-CRC"):
        return run_l1_crc(case)
    if case.id.startswith("L1-B62"):
        return run_l1_base62(case)
    if case.id.startswith("L1-FRAME"):
        return run_l1_frame(case)
    if case.id == "L2-XENC-01":
        return run_l2_xenc_01(case)
    if case.id == "L2-XENC-02":
        return run_l2_xenc_02(case)
    if case.id == "L2-CRC-CROSS-01":
        return run_l2_crc_cross(case)
    return CaseResult(
        id=case.id,
        status="SKIP",
        message="Case is outside the real TX adapter execution surface.",
        details={"caseId": case.id},
    )


def command_info(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_info_payload(
            manifest,
            TX_ROOT,
            "Real OSynaptic-TX adapter backed by the sibling C runtime and local native build.",
        )
    )


def command_capabilities(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_capabilities_payload(
            manifest,
            "Builds and loads the real OSynaptic-TX C sources locally, then executes producer-side wire and interoperability checks.",
            limits={
                "requiresLocalCompiler": True,
                "buildCache": "adapters/.build/osynaptic_tx",
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
        TX_ROOT,
        environment={"implementationRole": "producer"},
        note="PASS, FAIL, and SKIP results reflect the current real OSynaptic-TX runtime rather than synthetic expectations.",
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
    parser = argparse.ArgumentParser(description="OpenSynaptic real TX adapter")
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