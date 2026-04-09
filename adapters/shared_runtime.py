from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


CONFORMANCE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = CONFORMANCE_ROOT.parent
SCHEMA_BASE = "https://github.com/OpenSynaptic/OpenSynaptic-Conformance/blob/main/schemas"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, set):
        return [json_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def emit(payload: dict[str, Any]) -> int:
    json.dump(json_safe(payload), sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


def resolve_relative(source: Path, relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    return (source.parent / relative_path).resolve()


def detect_git_commit(repo_path: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"
    return completed.stdout.strip() or "working-tree"


def collect_required_case_ids(profile: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for requirement in profile.get("requirements", []):
        for case_id in requirement.get("requiredCases", []):
            if case_id not in seen:
                seen.add(case_id)
                ordered.append(case_id)
    return ordered


def detect_profile_dataset_path(
    profile_path: Path,
    profile: dict[str, Any],
    explicit_dataset_path: Path | None,
) -> Path | None:
    if explicit_dataset_path is not None:
        return explicit_dataset_path

    dataset_paths: list[Path] = []
    for requirement in profile.get("requirements", []):
        if requirement.get("type") != "dataset":
            continue
        resolved = resolve_relative(profile_path, requirement.get("path"))
        if resolved is not None and resolved not in dataset_paths:
            dataset_paths.append(resolved)

    if len(dataset_paths) == 1:
        return dataset_paths[0]
    return None


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hex_value(value: int, width: int = 0) -> str:
    if width > 0:
        return f"0x{int(value) & ((1 << (width * 4)) - 1):0{width}X}"
    return f"0x{int(value):X}"


def parse_hex_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16 if value.lower().startswith("0x") else 10)
    raise ValueError(f"unsupported numeric value: {value!r}")


def approximately_equal(actual: float, expected: float, tolerance: float = 1e-6) -> bool:
    return abs(float(actual) - float(expected)) <= float(tolerance)


def parse_frame_bytes(packet: bytes) -> dict[str, Any] | None:
    if packet is None or len(packet) < 16:
        return None
    body = packet[13:-3]
    return {
        "cmd": packet[0],
        "route": packet[1],
        "aid": int.from_bytes(packet[2:6], "big"),
        "tid": packet[6],
        "timestamp_raw": int.from_bytes(packet[7:13], "big"),
        "body": body,
        "body_text": body.decode("utf-8", errors="ignore"),
        "crc8": packet[-3],
        "crc16": int.from_bytes(packet[-2:], "big"),
        "length": len(packet),
    }


def parse_minimal_sensor_body(body: bytes) -> dict[str, Any] | None:
    try:
        parts = body.decode("utf-8", errors="strict").split("|")
    except UnicodeDecodeError:
        return None
    if len(parts) != 3:
        return None
    return {
        "sensorId": parts[0],
        "unit": parts[1],
        "base62": parts[2],
    }


def count_core_sensor_entries(decoded: dict[str, Any]) -> int:
    count = 0
    while f"s{count + 1}_id" in decoded:
        count += 1
    return count


def core_sensor_entry(decoded: dict[str, Any], index: int = 1) -> dict[str, Any]:
    prefix = f"s{index}_"
    return {
        "sensorId": decoded.get(f"{prefix}id"),
        "status": decoded.get(f"{prefix}s"),
        "unit": decoded.get(f"{prefix}u"),
        "value": decoded.get(f"{prefix}v"),
    }


def truncate_text(text: str, max_lines: int = 20, max_chars: int = 4000) -> str:
    lines = text.splitlines()
    trimmed = lines[:max_lines]
    body = "\n".join(trimmed)
    if len(body) > max_chars:
        body = body[: max_chars - 3] + "..."
    if len(lines) > max_lines:
        suffix = f"\n... ({len(lines) - max_lines} more lines)"
        if len(body) + len(suffix) > max_chars:
            body = body[: max(0, max_chars - len(suffix) - 3)] + "..."
        body += suffix
    return body


@dataclass(frozen=True)
class CaseDefinition:
    id: str
    requirement_id: str
    requirement_type: str
    source_path: Path
    source_id: str
    record: dict[str, Any]
    applicable: bool


@dataclass
class ProfileContext:
    profile_path: Path
    profile: dict[str, Any]
    dataset_path: Path | None
    dataset_version: str | None
    ordered_case_ids: list[str]
    case_map: dict[str, CaseDefinition]


@dataclass
class CaseResult:
    id: str
    status: str
    message: str
    duration_ms: float = 0.0
    vector_set_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_report_entry(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "durationMs": round(float(self.duration_ms), 3),
        }
        if self.vector_set_id is not None:
            payload["vectorSetId"] = self.vector_set_id
        payload["details"] = self.details or {}
        return payload


def build_profile_context(
    profile_path: Path,
    implementation_label: str,
    explicit_dataset_path: Path | None = None,
) -> ProfileContext:
    profile = load_json(profile_path)
    dataset_path = detect_profile_dataset_path(profile_path, profile, explicit_dataset_path)
    dataset_version = load_json(dataset_path).get("version") if dataset_path is not None else None
    ordered_case_ids = collect_required_case_ids(profile)
    case_map: dict[str, CaseDefinition] = {}

    for requirement in profile.get("requirements", []):
        source_path = resolve_relative(profile_path, requirement.get("path"))
        if source_path is None:
            raise ValueError(f"requirement path is invalid for {requirement.get('id')}")
        source = load_json(source_path)
        requirement_type = str(requirement.get("type") or "")
        fallback_applies_to = source.get("appliesTo", profile.get("appliesTo", []))

        if requirement_type == "vector-set":
            source_records = {entry["id"]: entry for entry in source.get("vectors", [])}
            source_id = str(source.get("vectorSetId") or source_path.name)
        elif requirement_type == "dataset":
            source_records = {entry["id"]: entry for entry in source.get("cases", [])}
            source_id = str(source.get("datasetId") or source_path.name)
        else:
            raise ValueError(f"unsupported requirement type: {requirement_type!r}")

        for case_id in requirement.get("requiredCases", []):
            record = source_records.get(case_id)
            if record is None:
                raise ValueError(f"case id {case_id!r} not found in {source_path.as_posix()}")
            applies_to = record.get("appliesTo", fallback_applies_to)
            applicable = implementation_label in applies_to if isinstance(applies_to, list) else False
            case_map[case_id] = CaseDefinition(
                id=case_id,
                requirement_id=str(requirement.get("id") or case_id),
                requirement_type=requirement_type,
                source_path=source_path,
                source_id=source_id,
                record=record,
                applicable=applicable,
            )

    return ProfileContext(
        profile_path=profile_path,
        profile=profile,
        dataset_path=dataset_path,
        dataset_version=dataset_version,
        ordered_case_ids=ordered_case_ids,
        case_map=case_map,
    )


def execute_cases(
    context: ProfileContext,
    selected_case_ids: list[str] | None,
    executor: Callable[[CaseDefinition], CaseResult],
) -> list[CaseResult]:
    case_ids = selected_case_ids[:] if selected_case_ids else context.ordered_case_ids[:]
    unknown = [case_id for case_id in case_ids if case_id not in context.case_map]
    if unknown:
        raise ValueError(f"unknown case ids for profile {context.profile.get('profileId')}: {unknown}")

    results: list[CaseResult] = []
    for case_id in case_ids:
        definition = context.case_map[case_id]
        if not definition.applicable:
            results.append(
                CaseResult(
                    id=case_id,
                    status="SKIP",
                    message=f"Case is not applicable to this adapter role ({case_id}).",
                    vector_set_id=definition.source_id if definition.requirement_type == "vector-set" else None,
                    details={
                        "applicable": False,
                        "requirementType": definition.requirement_type,
                        "source": definition.source_id,
                    },
                )
            )
            continue

        started = time.perf_counter()
        try:
            result = executor(definition)
        except Exception as exc:
            result = CaseResult(
                id=case_id,
                status="ERROR",
                message=f"Unhandled adapter exception: {type(exc).__name__}: {exc}",
                vector_set_id=definition.source_id if definition.requirement_type == "vector-set" else None,
                details={
                    "exceptionType": type(exc).__name__,
                    "traceback": truncate_text(traceback.format_exc()),
                },
            )
        result.id = case_id
        if result.vector_set_id is None and definition.requirement_type == "vector-set":
            result.vector_set_id = definition.source_id
        result.duration_ms = (time.perf_counter() - started) * 1000.0
        results.append(result)
    return results


def build_info_payload(manifest: dict[str, Any], implementation_repo: Path, note: str) -> dict[str, Any]:
    return {
        "$schema": f"{SCHEMA_BASE}/adapter-info.schema.json",
        "kind": "adapter-info",
        "schemaVersion": "1.0.0",
        "adapterId": manifest["adapterId"],
        "implementation": {
            "name": manifest["implementation"]["name"],
            "version": manifest["version"],
            "repository": manifest["implementation"]["repository"],
            "target": manifest["implementation"]["target"],
            "commit": detect_git_commit(implementation_repo),
        },
        "protocolVersion": manifest["interface"]["protocolVersion"],
        "transport": manifest["interface"]["transport"],
        "note": note,
    }


def build_capabilities_payload(
    manifest: dict[str, Any],
    note: str,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "$schema": f"{SCHEMA_BASE}/adapter-capabilities.schema.json",
        "kind": "adapter-capabilities",
        "schemaVersion": "1.0.0",
        "adapterId": manifest["adapterId"],
        "roles": manifest["roles"],
        "supportedProfiles": manifest["supportedProfiles"],
        "commands": [command["name"] for command in manifest["interface"]["requiredCommands"]],
        "capabilities": manifest.get("capabilities", {}),
        "limits": limits or {},
        "note": note,
    }


def build_report(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    results: list[CaseResult],
    dataset_version: str | None,
    implementation_repo: Path,
    environment: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    passed = sum(1 for item in results if item.status == "PASS")
    failed = sum(1 for item in results if item.status in {"FAIL", "ERROR"})
    skipped = sum(1 for item in results if item.status == "SKIP")
    if any(item.status == "ERROR" for item in results):
        status = "ERROR"
    elif failed:
        status = "FAIL"
    elif skipped:
        status = "PARTIAL"
    else:
        status = "PASS"

    summary: dict[str, Any] = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "status": status,
    }
    if note:
        summary["note"] = note

    report_environment = {
        "platform": platform.platform(),
        "pythonVersion": sys.version.split()[0],
        "adapterRuntime": "python",
    }
    if environment:
        report_environment.update(environment)

    commit = detect_git_commit(implementation_repo)
    return {
        "$schema": f"{SCHEMA_BASE}/report.schema.json",
        "kind": "conformance-report",
        "schemaVersion": "1.0.0",
        "reportId": f"{manifest['adapterId']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "createdAt": utcnow_iso(),
        "repositoryVersion": commit,
        "profileId": profile["profileId"],
        "datasetVersion": dataset_version,
        "implementation": {
            "name": manifest["implementation"]["name"],
            "version": manifest["version"],
            "adapter": manifest["adapterId"],
            "target": manifest["implementation"]["target"],
            "commit": commit,
        },
        "environment": report_environment,
        "summary": summary,
        "results": [item.to_report_entry() for item in results],
    }


def exit_code_for_report(report: dict[str, Any]) -> int:
    return 1 if report.get("summary", {}).get("status") in {"FAIL", "ERROR"} else 0