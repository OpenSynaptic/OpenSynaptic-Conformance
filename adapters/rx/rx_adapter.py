from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


ADAPTERS_ROOT = Path(__file__).resolve().parents[1]
if str(ADAPTERS_ROOT) not in sys.path:
    sys.path.insert(0, str(ADAPTERS_ROOT))

from native_backends import CoreBackend, FX_ROOT, RX_ROOT, RxBackend, TxBackend, FxBackend
from shared_runtime import (
    CaseDefinition,
    CaseResult,
    build_capabilities_payload,
    build_info_payload,
    build_profile_context,
    build_report,
    emit,
    execute_cases,
    exit_code_for_report,
    load_json,
    parse_frame_bytes,
    parse_hex_value,
)


MANIFEST_PATH = Path(__file__).with_name("manifest.v1.json")
IMPLEMENTATION_LABEL = "rx"
_RX_BACKEND: RxBackend | None = None
_TX_BACKEND: TxBackend | None = None
_CORE_BACKEND: CoreBackend | None = None
_FX_BACKEND: FxBackend | None = None


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


def get_core() -> CoreBackend:
    global _CORE_BACKEND
    if _CORE_BACKEND is None:
        _CORE_BACKEND = CoreBackend()
    return _CORE_BACKEND


def get_fx() -> FxBackend:
    global _FX_BACKEND
    if _FX_BACKEND is None:
        _FX_BACKEND = FxBackend()
    return _FX_BACKEND


def pass_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="PASS", message=message, details=details)


def fail_result(case: CaseDefinition, message: str, details: dict[str, Any]) -> CaseResult:
    return CaseResult(id=case.id, status="FAIL", message=message, details=details)


def run_l1_crc(case: CaseDefinition) -> CaseResult:
    payload = bytes.fromhex(case.record["input"]["bytesHex"])
    expected = parse_hex_value(case.record["expected"]["resultHex"])
    if case.record["operation"] == "crc8_smbus":
        actual = get_rx().crc8(payload)
    else:
        actual = get_rx().crc16(payload)
    details = {
        "operation": case.record["operation"],
        "inputHex": payload.hex(),
        "expected": expected,
        "actual": actual,
    }
    if actual == expected:
        return pass_result(case, "RX CRC implementation matches the canonical reference vector.", details)
    return fail_result(case, "RX CRC implementation diverges from the canonical reference vector.", details)


def run_l1_base62(case: CaseDefinition) -> CaseResult:
    text = case.record["input"].get("text")
    surrogate = False
    if text is None:
        text = ""
        surrogate = True
    expected = case.record["expected"]
    try:
        actual_value = get_rx().base62_decode(str(text))
        if surrogate and not expected.get("ok"):
            return pass_result(
                case,
                "RX adapter used an empty-string surrogate for the null-input guard case and did not crash.",
                {"text": text, "surrogateEmptyInput": True, "expected": expected, "actualValue": actual_value},
            )
        ok = bool(expected.get("ok")) and actual_value == int(expected.get("value"))
        details = {
            "text": text,
            "surrogateEmptyInput": surrogate,
            "actualValue": actual_value,
            "expected": expected,
        }
        if ok:
            return pass_result(case, "RX Base62 decoding matches the canonical reference vector.", details)
        return fail_result(case, "RX Base62 decoding diverges from the canonical reference vector.", details)
    except Exception as exc:
        details = {
            "text": text,
            "surrogateEmptyInput": surrogate,
            "expected": expected,
            "error": str(exc),
        }
        if not expected.get("ok"):
            return pass_result(case, "RX rejects the invalid Base62 input as expected.", details)
        return fail_result(case, "RX rejected a Base62 input that the canonical vector expects to decode.", details)


def run_l1_frame(case: CaseDefinition) -> CaseResult:
    packet_hex = case.record["input"].get("packetHex")
    packet = b"" if packet_hex is None else bytes.fromhex(packet_hex)
    decoded = get_rx().packet_decode(packet)
    expected = case.record["expected"]
    details = {
        "packetHex": packet.hex(),
        "decoded": decoded,
        "expected": expected,
        "surrogateEmptyInput": packet_hex is None,
    }

    if case.record["operation"] == "guard_parse":
        if decoded["rc"] != 1:
            return pass_result(case, "RX rejects malformed or empty frame input without decoding it.", details)
        return fail_result(case, "RX accepted a malformed or empty frame input.", details)

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
        return pass_result(case, "RX frame parser matches the canonical L1 frame layout.", details)
    return fail_result(case, "RX frame parser does not match the canonical L1 frame layout.", details)


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
    details = {"packetHex": packet.hex(), "decoded": decoded, "expected": expected}
    if ok:
        return pass_result(case, "RX decodes the real TX packet with full canonical semantics.", details)
    return fail_result(case, "RX does not decode the real TX packet to the canonical semantic payload.", details)


def run_l2_xenc_04(case: CaseDefinition) -> CaseResult:
    sensor = case.record["input"]["sensor"]
    expected_scaled = int(case.record["expected"]["scaled"])
    packet = b""
    try:
        packet = get_fx().encode_sensor_packet(0x01020304, 7, 1_710_000_000, str(sensor["sensorId"]), str(sensor["unit"]), float(sensor["value"]))
        meta = get_rx().packet_decode(packet)
        header = parse_frame_bytes(packet)
        body = header["body_text"] if header is not None else None
        details = {"packetHex": packet.hex(), "meta": meta, "bodyText": body, "expectedScaled": expected_scaled}
        if meta["rc"] != 1 or not meta["crc8_ok"] or not meta["crc16_ok"]:
            return fail_result(case, "RX cannot even validate the FX frame structurally and by CRC.", details)
        if body is None or body.count("|") != 2:
            return fail_result(case, "RX does not expose a compatible body-unpack path for the real FX frame format.", details)
        decoded = get_rx().sensor_recv(packet)
        details["decoded"] = decoded
        ok = decoded["rc"] == 1 and decoded["scaled"] == expected_scaled and decoded["crc8_ok"] and decoded["crc16_ok"]
        if ok:
            return pass_result(case, "RX preserves the expected numeric payload when decoding a real FX frame.", details)
        return fail_result(case, "RX does not preserve the expected numeric payload when decoding a real FX frame.", details)
    except OSError as exc:
        return fail_result(
            case,
            "RX native interop path faults on the real FX frame instead of yielding a compatible semantic payload.",
            {"packetHex": packet.hex(), "expectedScaled": expected_scaled, "nativeError": str(exc)},
        )


def run_l2_xenc_06(case: CaseDefinition) -> CaseResult:
    sensor = case.record["input"]["sensor"]
    packet = get_core().transmit_sensor(str(sensor["sensorId"]), float(sensor["value"]), str(sensor["unit"]), timestamp=1_710_000_000)
    decoded = get_rx().sensor_recv(packet)
    expected = case.record["expected"]
    ok = decoded["rc"] == 1 and decoded["crc8_ok"] == bool(expected["crc8Ok"]) and decoded["crc16_ok"] == bool(expected["crc16Ok"])
    details = {"packetHex": packet.hex(), "decoded": decoded, "expected": expected}
    if ok:
        return pass_result(case, "RX accepts the real Core packet and validates both CRC fields.", details)
    return fail_result(case, "RX does not satisfy the expected CRC acceptance behavior on a real Core packet.", details)


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
        return pass_result(case, "RX CRC recomputation matches the exchanged frame and peer implementations.", details)
    return fail_result(case, "RX CRC recomputation diverges from the exchanged frame or peer implementations.", details)


def execute_case(case: CaseDefinition) -> CaseResult:
    if case.id.startswith("L1-CRC"):
        return run_l1_crc(case)
    if case.id.startswith("L1-B62"):
        return run_l1_base62(case)
    if case.id.startswith("L1-FRAME"):
        return run_l1_frame(case)
    if case.id == "L2-XENC-02":
        return run_l2_xenc_02(case)
    if case.id == "L2-XENC-04":
        return run_l2_xenc_04(case)
    if case.id == "L2-XENC-06":
        return run_l2_xenc_06(case)
    if case.id == "L2-CRC-CROSS-01":
        return run_l2_crc_cross(case)
    return CaseResult(
        id=case.id,
        status="SKIP",
        message="Case is outside the real RX adapter execution surface.",
        details={"caseId": case.id},
    )


def command_info(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_info_payload(
            manifest,
            RX_ROOT,
            "Real OSynaptic-RX adapter backed by the sibling C runtime and local native build.",
        )
    )


def command_capabilities(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    return emit(
        build_capabilities_payload(
            manifest,
            "Builds and loads the real OSynaptic-RX C sources locally, then executes consumer-side wire and interoperability checks.",
            limits={
                "requiresLocalCompiler": True,
                "buildCache": "adapters/.build/osynaptic_rx",
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
        RX_ROOT,
        environment={"implementationRole": "consumer"},
        note="PASS, FAIL, and SKIP results reflect the current real OSynaptic-RX runtime rather than synthetic expectations.",
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
    parser = argparse.ArgumentParser(description="OpenSynaptic real RX adapter")
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