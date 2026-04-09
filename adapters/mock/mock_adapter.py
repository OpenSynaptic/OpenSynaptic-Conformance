from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("manifest.v1.json")
SCHEMA_BASE = "https://github.com/OpenSynaptic/OpenSynaptic-Conformance/blob/main/schemas"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"
    return completed.stdout.strip() or "working-tree"


def resolve_relative(source: Path, relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    return (source.parent / relative_path).resolve()


def collect_required_case_ids(profile: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for requirement in profile.get("requirements", []):
        for case_id in requirement.get("requiredCases", []):
            if case_id not in seen:
                seen.add(case_id)
                ordered.append(case_id)
    return ordered


def detect_dataset_path(profile_path: Path, profile: dict[str, Any], explicit_dataset: Path | None) -> Path | None:
    if explicit_dataset is not None:
        return explicit_dataset
    dataset_paths: list[Path] = []
    for requirement in profile.get("requirements", []):
        if requirement.get("type") != "dataset":
            continue
        dataset_path = resolve_relative(profile_path, requirement.get("path"))
        if dataset_path is not None and dataset_path not in dataset_paths:
            dataset_paths.append(dataset_path)
    if len(dataset_paths) == 1:
        return dataset_paths[0]
    return None


def build_report(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    case_ids: list[str],
    dataset_version: str | None,
    mode: str,
) -> dict[str, Any]:
    commit = detect_git_commit()
    results = [
        {
            "id": case_id,
            "status": "PASS",
            "message": f"Synthetic contract pass via mock adapter ({mode}).",
            "durationMs": 0.0,
            "details": {
                "adapterMode": mode,
                "source": "repository-mock-adapter",
            },
        }
        for case_id in case_ids
    ]

    return {
        "$schema": f"{SCHEMA_BASE}/report.schema.json",
        "kind": "conformance-report",
        "schemaVersion": "1.0.0",
        "reportId": f"mock-{mode}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        "environment": {
            "pythonVersion": sys.version.split()[0],
            "runner": "mock-adapter",
        },
        "summary": {
            "total": len(results),
            "passed": len(results),
            "failed": 0,
            "skipped": 0,
            "status": "PASS",
            "note": "Repository-local synthetic pass used for contract validation.",
        },
        "results": results,
    }


def emit(payload: dict[str, Any]) -> int:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


def command_info(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    payload = {
        "$schema": f"{SCHEMA_BASE}/adapter-info.schema.json",
        "kind": "adapter-info",
        "schemaVersion": "1.0.0",
        "adapterId": manifest["adapterId"],
        "implementation": {
            "name": manifest["implementation"]["name"],
            "version": manifest["version"],
            "repository": manifest["implementation"]["repository"],
            "target": manifest["implementation"]["target"],
            "commit": detect_git_commit(),
        },
        "protocolVersion": manifest["interface"]["protocolVersion"],
        "transport": manifest["interface"]["transport"],
        "note": "Repository-owned mock adapter for contract verification.",
    }
    return emit(payload)


def command_capabilities(_args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    payload = {
        "$schema": f"{SCHEMA_BASE}/adapter-capabilities.schema.json",
        "kind": "adapter-capabilities",
        "schemaVersion": "1.0.0",
        "adapterId": manifest["adapterId"],
        "roles": manifest["roles"],
        "supportedProfiles": manifest["supportedProfiles"],
        "commands": [command["name"] for command in manifest["interface"]["requiredCommands"]],
        "capabilities": manifest.get("capabilities", {}),
        "limits": {
            "maxRequestedCases": 4096,
            "supportsSyntheticPassOnly": True,
        },
        "note": "This adapter intentionally returns deterministic PASS results for contract and CI smoke testing.",
    }
    return emit(payload)


def command_run_profile(args: argparse.Namespace) -> int:
    manifest = load_json(MANIFEST_PATH)
    profile_path = Path(args.profile).resolve()
    profile = load_json(profile_path)
    dataset_path = detect_dataset_path(profile_path, profile, Path(args.dataset).resolve() if args.dataset else None)
    dataset_version = None
    if dataset_path is not None:
        dataset_version = load_json(dataset_path).get("version")
    report = build_report(manifest, profile, collect_required_case_ids(profile), dataset_version, "run-profile")
    return emit(report)


def command_run_cases(args: argparse.Namespace) -> int:
    if not args.cases:
        print("at least one --case value is required for run-cases", file=sys.stderr)
        return 2

    manifest = load_json(MANIFEST_PATH)
    profile_path = Path(args.profile).resolve()
    profile = load_json(profile_path)
    available_case_ids = collect_required_case_ids(profile)
    unknown_case_ids = sorted(set(args.cases).difference(available_case_ids))
    if unknown_case_ids:
        print(f"unknown case ids: {unknown_case_ids}", file=sys.stderr)
        return 2

    dataset_path = detect_dataset_path(profile_path, profile, Path(args.dataset).resolve() if args.dataset else None)
    dataset_version = None
    if dataset_path is not None:
        dataset_version = load_json(dataset_path).get("version")
    report = build_report(manifest, profile, args.cases, dataset_version, "run-cases")
    return emit(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenSynaptic mock adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="emit adapter metadata")
    info.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    info.set_defaults(func=command_info)

    capabilities = subparsers.add_parser("capabilities", help="emit adapter capabilities")
    capabilities.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    capabilities.set_defaults(func=command_capabilities)

    run_profile = subparsers.add_parser("run-profile", help="emit a synthetic PASS report for a full profile")
    run_profile.add_argument("--profile", required=True, help="path to the conformance profile")
    run_profile.add_argument("--dataset", default=None, help="optional explicit dataset manifest path")
    run_profile.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    run_profile.set_defaults(func=command_run_profile)

    run_cases = subparsers.add_parser("run-cases", help="emit a synthetic PASS report for selected cases")
    run_cases.add_argument("--profile", required=True, help="path to the conformance profile")
    run_cases.add_argument("--dataset", default=None, help="optional explicit dataset manifest path")
    run_cases.add_argument("--case", dest="cases", action="append", default=[], help="case id to execute")
    run_cases.add_argument("--json", action="store_true", help="reserved for contract compatibility")
    run_cases.set_defaults(func=command_run_cases)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())