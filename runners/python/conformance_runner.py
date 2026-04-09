from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_SCHEMA_KEYS = {"$schema", "$id", "title"}
REQUIRED_PROFILE_KEYS = {
    "kind",
    "schemaVersion",
    "profileId",
    "version",
    "title",
    "level",
    "status",
    "description",
    "appliesTo",
    "requirements",
    "execution",
    "passCriteria",
    "skipPolicy",
    "report",
}
REQUIRED_VECTOR_SET_KEYS = {
    "kind",
    "schemaVersion",
    "vectorSetId",
    "version",
    "title",
    "description",
    "category",
    "vectors",
}
REQUIRED_VECTOR_KEYS = {"id", "operation", "appliesTo", "input", "expected"}


@dataclass
class AssetStatus:
    kind: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else "PASS"


class AssetValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.assets: dict[str, AssetStatus] = {}
        self.vector_sets: dict[Path, dict[str, Any]] = {}
        self.profiles: dict[Path, dict[str, Any]] = {}
        self.schemas: dict[Path, dict[str, Any]] = {}

    def validate(self) -> tuple[dict[str, AssetStatus], dict[str, Any]]:
        self._load_schemas()
        self._load_vector_sets()
        self._load_profiles()
        self._validate_profile_cross_references()
        report = self._build_report()
        return self.assets, report

    def list_assets(self) -> dict[str, list[tuple[str, str]]]:
        asset_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path in sorted((self.root / "schemas").glob("*.json")):
            data = self._load_json(path)
            asset_map["schemas"].append((self._rel(path), str(data.get("$id", ""))))
        for path in sorted((self.root / "profiles").rglob("*.json")):
            data = self._load_json(path)
            asset_map["profiles"].append((self._rel(path), str(data.get("profileId", ""))))
        for path in sorted((self.root / "vectors").rglob("*.json")):
            data = self._load_json(path)
            asset_map["vectors"].append((self._rel(path), str(data.get("vectorSetId", ""))))
        return asset_map

    def _load_schemas(self) -> None:
        seen_ids: dict[str, str] = {}
        for path in sorted((self.root / "schemas").glob("*.json")):
            rel = self._rel(path)
            data = self._safe_load(path, "schema")
            if data is None:
                continue
            self.schemas[path] = data
            missing = REQUIRED_SCHEMA_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required schema keys: {sorted(missing)}")
            schema_id = data.get("$id")
            if schema_id:
                if schema_id in seen_ids:
                    self._error(rel, f"duplicate schema id also used by {seen_ids[schema_id]}")
                else:
                    seen_ids[schema_id] = rel

    def _load_vector_sets(self) -> None:
        seen_ids: dict[str, str] = {}
        for path in sorted((self.root / "vectors").rglob("*.json")):
            rel = self._rel(path)
            data = self._safe_load(path, "vector-set")
            if data is None:
                continue
            self.vector_sets[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_VECTOR_SET_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required vector-set keys: {sorted(missing)}")
            if data.get("kind") != "vector-set":
                self._error(rel, f"unexpected kind: {data.get('kind')!r}")
            vector_set_id = data.get("vectorSetId")
            if vector_set_id:
                if vector_set_id in seen_ids:
                    self._error(rel, f"duplicate vectorSetId also used by {seen_ids[vector_set_id]}")
                else:
                    seen_ids[vector_set_id] = rel
            seen_vector_ids: set[str] = set()
            for entry in data.get("vectors", []):
                missing_vector_keys = REQUIRED_VECTOR_KEYS.difference(entry)
                if missing_vector_keys:
                    self._error(rel, f"vector entry missing keys: {sorted(missing_vector_keys)}")
                    continue
                vector_id = entry["id"]
                if vector_id in seen_vector_ids:
                    self._error(rel, f"duplicate vector id: {vector_id}")
                seen_vector_ids.add(vector_id)

    def _load_profiles(self) -> None:
        seen_ids: dict[str, str] = {}
        for path in sorted((self.root / "profiles").rglob("*.json")):
            rel = self._rel(path)
            data = self._safe_load(path, "profile")
            if data is None:
                continue
            self.profiles[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_PROFILE_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required profile keys: {sorted(missing)}")
            if data.get("kind") != "conformance-profile":
                self._error(rel, f"unexpected kind: {data.get('kind')!r}")
            profile_id = data.get("profileId")
            if profile_id:
                if profile_id in seen_ids:
                    self._error(rel, f"duplicate profileId also used by {seen_ids[profile_id]}")
                else:
                    seen_ids[profile_id] = rel

    def _validate_profile_cross_references(self) -> None:
        vector_index = {
            self._rel(path): {entry["id"] for entry in data.get("vectors", []) if "id" in entry}
            for path, data in self.vector_sets.items()
        }

        for path, profile in self.profiles.items():
            rel = self._rel(path)
            required_cases_union: set[str] = set()

            report_path = self._resolve_relative(path, profile.get("report", {}).get("schemaPath"))
            if report_path is None:
                self._error(rel, "profile report.schemaPath is missing or invalid")
            elif not report_path.exists():
                self._error(rel, f"missing report schema path: {self._rel(report_path)}")

            for requirement in profile.get("requirements", []):
                req_id = requirement.get("id", "<unknown>")
                required_cases = set(requirement.get("requiredCases", []))
                required_cases_union.update(required_cases)
                target = self._resolve_relative(path, requirement.get("path"))
                if target is None:
                    self._error(rel, f"requirement {req_id} has missing path")
                    continue
                if not target.exists():
                    self._error(rel, f"requirement {req_id} references missing path {self._rel(target)}")
                    continue
                if requirement.get("type") == "vector-set":
                    target_rel = self._rel(target)
                    known_cases = vector_index.get(target_rel)
                    if known_cases is None:
                        self._error(rel, f"requirement {req_id} points to non-loaded vector set {target_rel}")
                        continue
                    missing_cases = sorted(required_cases.difference(known_cases))
                    if missing_cases:
                        self._error(rel, f"requirement {req_id} references unknown vector ids: {missing_cases}")

            for pair in profile.get("execution", {}).get("requiredPairs", []):
                missing_cases = sorted(set(pair.get("cases", [])).difference(required_cases_union))
                if missing_cases:
                    self._error(rel, f"execution pair references cases not declared in requirements: {missing_cases}")

    def _build_report(self) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        passed = 0
        failed = 0

        for rel in sorted(self.assets):
            asset = self.assets[rel]
            if asset.status == "PASS":
                passed += 1
            else:
                failed += 1
            message_parts: list[str] = []
            if asset.errors:
                message_parts.append("errors: " + "; ".join(asset.errors))
            if asset.warnings:
                message_parts.append("warnings: " + "; ".join(asset.warnings))
            results.append(
                {
                    "id": rel,
                    "status": asset.status,
                    "message": " | ".join(message_parts) if message_parts else "asset OK",
                    "details": {
                        "kind": asset.kind,
                        "errors": asset.errors,
                        "warnings": asset.warnings,
                    },
                }
            )

        summary_status = "PASS" if failed == 0 else "FAIL"
        commit = self._detect_git_value(["rev-parse", "--short", "HEAD"])
        return {
            "$schema": "../../schemas/report.schema.json",
            "kind": "conformance-report",
            "schemaVersion": "1.0.0",
            "reportId": f"asset-validation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "repositoryVersion": commit or "working-tree",
            "profileId": "repository-assets",
            "datasetVersion": None,
            "implementation": {
                "name": "repository-assets",
                "version": "1.0.0",
                "adapter": "asset-validator",
                "target": "local-worktree",
                "commit": commit,
            },
            "environment": {
                "pythonVersion": sys.version.split()[0],
                "platform": platform.platform(),
            },
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "skipped": 0,
                "status": summary_status,
            },
            "results": results,
        }

    def _safe_load(self, path: Path, kind: str) -> dict[str, Any] | None:
        rel = self._rel(path)
        try:
            data = self._load_json(path)
        except Exception as exc:  # noqa: BLE001
            self._error(rel, f"failed to parse JSON: {exc}")
            self.assets.setdefault(rel, AssetStatus(kind=kind))
            return None
        self.assets.setdefault(rel, AssetStatus(kind=kind))
        return data

    def _validate_schema_ref(self, path: Path, data: dict[str, Any]) -> None:
        rel = self._rel(path)
        schema_ref = data.get("$schema")
        if not isinstance(schema_ref, str) or not schema_ref:
            self._error(rel, "$schema reference missing")
            return
        if schema_ref.startswith("http://") or schema_ref.startswith("https://"):
            return
        schema_path = self._resolve_relative(path, schema_ref)
        if schema_path is None or not schema_path.exists():
            target = schema_ref if schema_path is None else self._rel(schema_path)
            self._error(rel, f"broken $schema reference: {target}")

    def _resolve_relative(self, source: Path, relative_path: Any) -> Path | None:
        if not isinstance(relative_path, str) or not relative_path:
            return None
        return (source.parent / relative_path).resolve()

    def _load_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _error(self, rel: str, message: str) -> None:
        self.assets.setdefault(rel, AssetStatus(kind="unknown")).errors.append(message)

    def _detect_git_value(self, args: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.root), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return completed.stdout.strip() or None


def command_list_assets(root: Path) -> int:
    validator = AssetValidator(root)
    asset_map = validator.list_assets()
    for group in ("schemas", "profiles", "vectors"):
        print(f"[{group}]")
        for rel, asset_id in asset_map.get(group, []):
            suffix = f" :: {asset_id}" if asset_id else ""
            print(f"- {rel}{suffix}")
    return 0


def command_validate_assets(root: Path, write_report: Path | None) -> int:
    validator = AssetValidator(root)
    assets, report = validator.validate()

    for rel in sorted(assets):
        status = assets[rel]
        print(f"[{status.status}] {rel}")
        for error in status.errors:
            print(f"  error: {error}")
        for warning in status.warnings:
            print(f"  warning: {warning}")

    summary = report["summary"]
    print(
        f"summary: total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} status={summary['status']}"
    )

    if write_report is not None:
        write_report.parent.mkdir(parents=True, exist_ok=True)
        with write_report.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        print(f"wrote report: {write_report.as_posix()}")

    return 0 if summary["failed"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenSynaptic conformance repository asset runner")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root path",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-assets", help="list discovered schemas, profiles, and vectors")

    validate = subparsers.add_parser("validate-assets", help="validate repository JSON assets and references")
    validate.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="optional path for a generated asset-validation report",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "list-assets":
        return command_list_assets(root)
    if args.command == "validate-assets":
        return command_validate_assets(root, args.write_report)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
