from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conformance_runner import command_verify_adapter, load_json_file


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SmokeTarget:
    name: str
    adapter: Path
    profile: Path
    report: Path


SMOKE_TARGETS = (
    SmokeTarget(
        name="opensynaptic-core",
        adapter=Path("adapters/core/manifest.v1.json"),
        profile=Path("profiles/l4-security-validated/l4-security-validated.profile.v1.json"),
        report=Path("reports/generated/core-adapter.l4.smoke.report.json"),
    ),
    SmokeTarget(
        name="osynaptic-fx",
        adapter=Path("adapters/fx/manifest.v1.json"),
        profile=Path("profiles/l4-security-validated/l4-security-validated.profile.v1.json"),
        report=Path("reports/generated/fx-adapter.l4.smoke.report.json"),
    ),
    SmokeTarget(
        name="osynaptic-rx",
        adapter=Path("adapters/rx/manifest.v1.json"),
        profile=Path("profiles/l2-protocol-conformant/l2-protocol-conformant.profile.v1.json"),
        report=Path("reports/generated/rx-adapter.l2.smoke.report.json"),
    ),
    SmokeTarget(
        name="osynaptic-tx",
        adapter=Path("adapters/tx/manifest.v1.json"),
        profile=Path("profiles/l2-protocol-conformant/l2-protocol-conformant.profile.v1.json"),
        report=Path("reports/generated/tx-adapter.l2.smoke.report.json"),
    ),
)


def result_id(entry: dict[str, object]) -> str:
    value = entry.get("id") or entry.get("caseId") or "<unknown>"
    return str(value)


def run_target(target: SmokeTarget) -> tuple[bool, str]:
    adapter_path = ROOT / target.adapter
    profile_path = ROOT / target.profile
    report_path = ROOT / target.report

    print(f"[SMOKE] {target.name} :: {target.profile.as_posix()}")
    exit_code = command_verify_adapter(ROOT, adapter_path, profile_path, None, [], report_path)
    if exit_code not in {0, 1}:
        return False, f"{target.name}: verify-adapter returned unexpected exit code {exit_code}"

    report = load_json_file(report_path)
    summary = report.get("summary", {})
    error_results = [
        result_id(entry)
        for entry in report.get("results", [])
        if isinstance(entry, dict) and str(entry.get("status")) == "ERROR"
    ]
    if str(summary.get("status")) == "ERROR" or error_results:
        return False, f"{target.name}: adapter reported runtime errors in cases {error_results}"

    print(
        f"  summary: status={summary.get('status')} passed={summary.get('passed')} "
        f"failed={summary.get('failed')} skipped={summary.get('skipped')}"
    )
    return True, ""


def main() -> int:
    failures: list[str] = []
    for target in SMOKE_TARGETS:
        ok, message = run_target(target)
        if not ok:
            failures.append(message)

    if failures:
        for message in failures:
            print(f"[FAIL] {message}")
        return 1

    print("[PASS] real adapter smoke completed without adapter execution errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())