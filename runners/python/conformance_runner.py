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
ALLOWED_PROFILE_KEYS = REQUIRED_PROFILE_KEYS | {"$schema", "prerequisites"}
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
ALLOWED_VECTOR_SET_KEYS = REQUIRED_VECTOR_SET_KEYS | {"$schema", "metadata", "note"}
REQUIRED_VECTOR_KEYS = {"id", "operation", "appliesTo", "input", "expected"}
REQUIRED_DATASET_KEYS = {
    "kind",
    "schemaVersion",
    "datasetId",
    "version",
    "title",
    "description",
    "datasetClass",
    "source",
    "cases",
}
ALLOWED_DATASET_KEYS = REQUIRED_DATASET_KEYS | {"$schema", "appliesTo"}
REQUIRED_DATASET_CASE_KEYS = {"id", "title", "category"}
REQUIRED_ADAPTER_KEYS = {
    "kind",
    "schemaVersion",
    "adapterId",
    "version",
    "title",
    "status",
    "implementation",
    "roles",
    "supportedProfiles",
    "interface",
}
ALLOWED_ADAPTER_KEYS = REQUIRED_ADAPTER_KEYS | {"$schema", "capabilities", "invocation", "note"}
REQUIRED_ADAPTER_COMMAND_KEYS = {"name", "purpose", "stdoutKind"}
REQUIRED_ADAPTER_COMMAND_NAMES = {"info", "capabilities", "run-profile", "run-cases"}
REQUIRED_ADAPTER_INFO_KEYS = {
    "kind",
    "schemaVersion",
    "adapterId",
    "implementation",
    "protocolVersion",
    "transport",
}
REQUIRED_ADAPTER_INFO_IMPL_KEYS = {"name", "version", "target"}
REQUIRED_ADAPTER_CAPABILITIES_KEYS = {
    "kind",
    "schemaVersion",
    "adapterId",
    "roles",
    "supportedProfiles",
    "commands",
}
REQUIRED_REPORT_KEYS = {
    "kind",
    "schemaVersion",
    "reportId",
    "createdAt",
    "repositoryVersion",
    "profileId",
    "implementation",
    "summary",
    "results",
}
REQUIRED_REPORT_IMPLEMENTATION_KEYS = {"name", "adapter", "target"}
REQUIRED_REPORT_SUMMARY_KEYS = {"total", "passed", "failed", "skipped", "status"}
REQUIRED_REPORT_RESULT_KEYS = {"id", "status"}


@dataclass
class AssetStatus:
    kind: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else "PASS"


@dataclass
class AdapterCommandOutcome:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    payload: dict[str, Any] | None


class AssetValidator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.assets: dict[str, AssetStatus] = {}
        self.vector_sets: dict[Path, dict[str, Any]] = {}
        self.dataset_manifests: dict[Path, dict[str, Any]] = {}
        self.profiles: dict[Path, dict[str, Any]] = {}
        self.adapter_manifests: dict[Path, dict[str, Any]] = {}
        self.schemas: dict[Path, dict[str, Any]] = {}

    @staticmethod
    def _should_skip_generated_json(path: Path) -> bool:
        return any(part in {".build", "__pycache__"} for part in path.parts)

    def validate(self) -> tuple[dict[str, AssetStatus], dict[str, Any]]:
        self._load_schemas()
        self._load_vector_sets()
        self._load_dataset_manifests()
        self._load_profiles()
        self._load_adapter_manifests()
        self._validate_profile_cross_references()
        self._validate_adapter_cross_references()
        report = self._build_report()
        return self.assets, report

    def list_assets(self) -> dict[str, list[tuple[str, str]]]:
        asset_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path in sorted((self.root / "schemas").glob("*.json")):
            data = self._load_json(path)
            asset_map["schemas"].append((self._rel(path), str(data.get("$id", ""))))
        for path in sorted((self.root / "profiles").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            data = self._load_json(path)
            asset_map["profiles"].append((self._rel(path), str(data.get("profileId", ""))))
        for path in sorted((self.root / "vectors").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            data = self._load_json(path)
            asset_map["vectors"].append((self._rel(path), str(data.get("vectorSetId", ""))))
        for path in sorted((self.root / "datasets").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            data = self._load_json(path)
            asset_map["datasets"].append((self._rel(path), str(data.get("datasetId", ""))))
        for path in sorted((self.root / "adapters").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            data = self._load_json(path)
            asset_map["adapters"].append((self._rel(path), str(data.get("adapterId", ""))))
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
            if self._should_skip_generated_json(path):
                continue
            rel = self._rel(path)
            data = self._safe_load(path, "vector-set")
            if data is None:
                continue
            self.vector_sets[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_VECTOR_SET_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required vector-set keys: {sorted(missing)}")
            unknown = sorted(set(data).difference(ALLOWED_VECTOR_SET_KEYS))
            if unknown:
                self._error(rel, f"unexpected vector-set keys: {unknown}")
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
            if self._should_skip_generated_json(path):
                continue
            rel = self._rel(path)
            data = self._safe_load(path, "profile")
            if data is None:
                continue
            self.profiles[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_PROFILE_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required profile keys: {sorted(missing)}")
            unknown = sorted(set(data).difference(ALLOWED_PROFILE_KEYS))
            if unknown:
                self._error(rel, f"unexpected profile keys: {unknown}")
            if data.get("kind") != "conformance-profile":
                self._error(rel, f"unexpected kind: {data.get('kind')!r}")
            profile_id = data.get("profileId")
            if profile_id:
                if profile_id in seen_ids:
                    self._error(rel, f"duplicate profileId also used by {seen_ids[profile_id]}")
                else:
                    seen_ids[profile_id] = rel

    def _load_dataset_manifests(self) -> None:
        seen_ids: dict[str, str] = {}
        for path in sorted((self.root / "datasets").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            rel = self._rel(path)
            data = self._safe_load(path, "dataset-manifest")
            if data is None:
                continue
            self.dataset_manifests[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_DATASET_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required dataset-manifest keys: {sorted(missing)}")
            unknown = sorted(set(data).difference(ALLOWED_DATASET_KEYS))
            if unknown:
                self._error(rel, f"unexpected dataset-manifest keys: {unknown}")
            if data.get("kind") != "dataset-manifest":
                self._error(rel, f"unexpected kind: {data.get('kind')!r}")
            dataset_id = data.get("datasetId")
            if dataset_id:
                if dataset_id in seen_ids:
                    self._error(rel, f"duplicate datasetId also used by {seen_ids[dataset_id]}")
                else:
                    seen_ids[dataset_id] = rel

            source = data.get("source")
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                self._error(rel, "dataset manifest source.path is missing or invalid")
            else:
                source_path = self._resolve_relative(path, source["path"])
                if source_path is None or not source_path.exists():
                    target = source["path"] if source_path is None else self._rel(source_path)
                    self._error(rel, f"broken dataset source path: {target}")

            seen_case_ids: set[str] = set()
            for entry in data.get("cases", []):
                missing_case_keys = REQUIRED_DATASET_CASE_KEYS.difference(entry)
                if missing_case_keys:
                    self._error(rel, f"dataset case missing keys: {sorted(missing_case_keys)}")
                    continue
                case_id = entry["id"]
                if case_id in seen_case_ids:
                    self._error(rel, f"duplicate dataset case id: {case_id}")
                seen_case_ids.add(case_id)

    def _load_adapter_manifests(self) -> None:
        seen_ids: dict[str, str] = {}
        for path in sorted((self.root / "adapters").rglob("*.json")):
            if self._should_skip_generated_json(path):
                continue
            rel = self._rel(path)
            data = self._safe_load(path, "adapter-manifest")
            if data is None:
                continue
            self.adapter_manifests[path] = data
            self._validate_schema_ref(path, data)
            missing = REQUIRED_ADAPTER_KEYS.difference(data)
            if missing:
                self._error(rel, f"missing required adapter-manifest keys: {sorted(missing)}")
            unknown = sorted(set(data).difference(ALLOWED_ADAPTER_KEYS))
            if unknown:
                self._error(rel, f"unexpected adapter-manifest keys: {unknown}")
            if data.get("kind") != "adapter-manifest":
                self._error(rel, f"unexpected kind: {data.get('kind')!r}")
            adapter_id = data.get("adapterId")
            if adapter_id:
                if adapter_id in seen_ids:
                    self._error(rel, f"duplicate adapterId also used by {seen_ids[adapter_id]}")
                else:
                    seen_ids[adapter_id] = rel

            interface = data.get("interface", {})
            stdout = interface.get("stdout", {})
            for schema_key, label in (
                ("infoSchemaPath", "adapter info"),
                ("capabilitiesSchemaPath", "adapter capabilities"),
                ("reportSchemaPath", "adapter report"),
            ):
                schema_ref = stdout.get(schema_key)
                schema_path = self._resolve_relative(path, schema_ref)
                if schema_path is None or not schema_path.exists():
                    target = schema_ref if schema_path is None else self._rel(schema_path)
                    self._error(rel, f"broken {label} schema path: {target}")

            seen_command_names: set[str] = set()
            for command in interface.get("requiredCommands", []):
                missing_command_keys = REQUIRED_ADAPTER_COMMAND_KEYS.difference(command)
                if missing_command_keys:
                    self._error(rel, f"adapter command missing keys: {sorted(missing_command_keys)}")
                    continue
                command_name = command["name"]
                if command_name in seen_command_names:
                    self._error(rel, f"duplicate adapter command name: {command_name}")
                seen_command_names.add(command_name)
            missing_command_names = sorted(REQUIRED_ADAPTER_COMMAND_NAMES.difference(seen_command_names))
            if missing_command_names:
                self._error(rel, f"adapter manifest missing required commands: {missing_command_names}")

            invocation = data.get("invocation")
            if data.get("status") == "active":
                if not isinstance(invocation, dict):
                    self._error(rel, "active adapter manifest must declare an invocation block")
                else:
                    self._validate_invocation(path, rel, invocation)
            elif isinstance(invocation, dict):
                self._validate_invocation(path, rel, invocation)

    def _validate_invocation(self, manifest_path: Path, rel: str, invocation: dict[str, Any]) -> None:
        invocation_type = invocation.get("type")
        if invocation_type == "python-script":
            script_path = self._resolve_relative(manifest_path, invocation.get("path"))
            if script_path is None or not script_path.exists():
                target = invocation.get("path") if script_path is None else self._rel(script_path)
                self._error(rel, f"broken adapter invocation script path: {target}")
        elif invocation_type == "command":
            command = invocation.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
                self._error(rel, "command invocation must define a non-empty command array")
        else:
            self._error(rel, f"unsupported invocation type: {invocation_type!r}")

        working_directory = invocation.get("workingDirectory")
        if working_directory is not None:
            working_directory_path = self._resolve_relative(manifest_path, working_directory)
            if working_directory_path is None or not working_directory_path.exists() or not working_directory_path.is_dir():
                target = working_directory if working_directory_path is None else self._rel(working_directory_path)
                self._error(rel, f"broken adapter working directory path: {target}")

        args = invocation.get("args")
        if args is not None and (not isinstance(args, list) or not all(isinstance(item, str) for item in args)):
            self._error(rel, "adapter invocation args must be an array of strings")

    def _validate_profile_cross_references(self) -> None:
        vector_index = {
            self._rel(path): {entry["id"] for entry in data.get("vectors", []) if "id" in entry}
            for path, data in self.vector_sets.items()
        }
        dataset_index = {
            self._rel(path): {entry["id"] for entry in data.get("cases", []) if "id" in entry}
            for path, data in self.dataset_manifests.items()
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
                if requirement.get("type") == "dataset":
                    target_rel = self._rel(target)
                    known_cases = dataset_index.get(target_rel)
                    if known_cases is None:
                        self._error(rel, f"requirement {req_id} points to non-loaded dataset manifest {target_rel}")
                        continue
                    missing_cases = sorted(required_cases.difference(known_cases))
                    if missing_cases:
                        self._error(rel, f"requirement {req_id} references unknown dataset case ids: {missing_cases}")

            for pair in profile.get("execution", {}).get("requiredPairs", []):
                missing_cases = sorted(set(pair.get("cases", [])).difference(required_cases_union))
                if missing_cases:
                    self._error(rel, f"execution pair references cases not declared in requirements: {missing_cases}")

    def _validate_adapter_cross_references(self) -> None:
        known_profile_ids = {data.get("profileId") for data in self.profiles.values() if data.get("profileId")}
        for path, manifest in self.adapter_manifests.items():
            rel = self._rel(path)
            missing_profiles = sorted(set(manifest.get("supportedProfiles", [])).difference(known_profile_ids))
            if missing_profiles:
                self._error(rel, f"supportedProfiles reference unknown profile ids: {missing_profiles}")

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


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_cli_path(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def resolve_relative(source: Path, relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    return (source.parent / relative_path).resolve()


def relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def collect_required_case_ids(profile: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for requirement in profile.get("requirements", []):
        for case_id in requirement.get("requiredCases", []):
            if case_id not in seen:
                seen.add(case_id)
                ordered.append(case_id)
    return ordered


def detect_profile_dataset_path(profile_path: Path, profile: dict[str, Any], explicit_dataset_path: Path | None) -> Path | None:
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


def build_adapter_command(manifest_path: Path, manifest: dict[str, Any]) -> tuple[list[str], Path]:
    invocation = manifest.get("invocation")
    if not isinstance(invocation, dict):
        raise ValueError("adapter manifest does not declare an invocation block")

    invocation_type = invocation.get("type")
    if invocation_type == "python-script":
        script_path = resolve_relative(manifest_path, invocation.get("path"))
        if script_path is None:
            raise ValueError("adapter invocation path is missing")
        command = [sys.executable, str(script_path)]
    elif invocation_type == "command":
        configured_command = invocation.get("command")
        if not isinstance(configured_command, list) or not configured_command:
            raise ValueError("adapter invocation command is missing")
        command = configured_command[:]
        first = command[0]
        if first.startswith(".") or "/" in first or "\\" in first:
            command[0] = str(resolve_relative(manifest_path, first) or first)
    else:
        raise ValueError(f"unsupported adapter invocation type: {invocation_type!r}")

    extra_args = invocation.get("args", [])
    if isinstance(extra_args, list):
        command.extend(str(item) for item in extra_args)

    working_directory = resolve_relative(manifest_path, invocation.get("workingDirectory"))
    if working_directory is None:
        working_directory = manifest_path.parent
    return command, working_directory


def invoke_adapter_command(
    manifest_path: Path,
    manifest: dict[str, Any],
    logical_command: str,
    extra_args: list[str],
) -> AdapterCommandOutcome:
    base_command, working_directory = build_adapter_command(manifest_path, manifest)
    command = [*base_command, logical_command, "--json", *extra_args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=working_directory,
    )

    stdout = completed.stdout.strip()
    payload: dict[str, Any] | None = None
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None

    return AdapterCommandOutcome(
        command=logical_command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        payload=payload,
    )


def validate_adapter_info_payload(payload: Any, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["info output is not a JSON object"]

    missing = REQUIRED_ADAPTER_INFO_KEYS.difference(payload)
    if missing:
        errors.append(f"info output missing keys: {sorted(missing)}")
    if payload.get("kind") != "adapter-info":
        errors.append(f"unexpected info kind: {payload.get('kind')!r}")
    if payload.get("adapterId") != manifest.get("adapterId"):
        errors.append("info adapterId does not match manifest")
    if payload.get("protocolVersion") != manifest.get("interface", {}).get("protocolVersion"):
        errors.append("info protocolVersion does not match manifest")
    if payload.get("transport") != manifest.get("interface", {}).get("transport"):
        errors.append("info transport does not match manifest")

    implementation = payload.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("info implementation field is missing or invalid")
    else:
        missing_impl = REQUIRED_ADAPTER_INFO_IMPL_KEYS.difference(implementation)
        if missing_impl:
            errors.append(f"info implementation missing keys: {sorted(missing_impl)}")
        if implementation.get("name") != manifest.get("implementation", {}).get("name"):
            errors.append("info implementation name does not match manifest")
        if implementation.get("target") != manifest.get("implementation", {}).get("target"):
            errors.append("info implementation target does not match manifest")

    return errors


def validate_adapter_capabilities_payload(payload: Any, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["capabilities output is not a JSON object"]

    missing = REQUIRED_ADAPTER_CAPABILITIES_KEYS.difference(payload)
    if missing:
        errors.append(f"capabilities output missing keys: {sorted(missing)}")
    if payload.get("kind") != "adapter-capabilities":
        errors.append(f"unexpected capabilities kind: {payload.get('kind')!r}")
    if payload.get("adapterId") != manifest.get("adapterId"):
        errors.append("capabilities adapterId does not match manifest")

    payload_roles = set(payload.get("roles", []))
    missing_roles = sorted(set(manifest.get("roles", [])).difference(payload_roles))
    if missing_roles:
        errors.append(f"capabilities missing roles declared by manifest: {missing_roles}")

    payload_profiles = set(payload.get("supportedProfiles", []))
    missing_profiles = sorted(set(manifest.get("supportedProfiles", [])).difference(payload_profiles))
    if missing_profiles:
        errors.append(f"capabilities missing supportedProfiles declared by manifest: {missing_profiles}")

    payload_commands = set(payload.get("commands", []))
    missing_commands = sorted(REQUIRED_ADAPTER_COMMAND_NAMES.difference(payload_commands))
    if missing_commands:
        errors.append(f"capabilities missing required commands: {missing_commands}")

    return errors


def validate_report_payload(
    payload: Any,
    manifest: dict[str, Any],
    profile: dict[str, Any],
    expected_case_ids: list[str],
    dataset_version: str | None,
    require_exact_case_match: bool,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["report output is not a JSON object"]

    missing = REQUIRED_REPORT_KEYS.difference(payload)
    if missing:
        errors.append(f"report output missing keys: {sorted(missing)}")
    if payload.get("kind") != "conformance-report":
        errors.append(f"unexpected report kind: {payload.get('kind')!r}")
    if payload.get("profileId") != profile.get("profileId"):
        errors.append("report profileId does not match selected profile")
    if dataset_version != payload.get("datasetVersion"):
        errors.append("report datasetVersion does not match selected dataset context")

    implementation = payload.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("report implementation field is missing or invalid")
    else:
        missing_impl = REQUIRED_REPORT_IMPLEMENTATION_KEYS.difference(implementation)
        if missing_impl:
            errors.append(f"report implementation missing keys: {sorted(missing_impl)}")
        if implementation.get("adapter") != manifest.get("adapterId"):
            errors.append("report implementation.adapter does not match manifest")

    summary = payload.get("summary")
    aggregate_summary = payload.get("aggregateSummary")
    if not isinstance(summary, dict):
        errors.append("report summary field is missing or invalid")
    else:
        missing_summary = REQUIRED_REPORT_SUMMARY_KEYS.difference(summary)
        if missing_summary:
            errors.append(f"report summary missing keys: {sorted(missing_summary)}")
    if aggregate_summary is not None:
        if not isinstance(aggregate_summary, dict):
            errors.append("report aggregateSummary field is invalid")
        else:
            required_aggregate_keys = {"total", "passed", "failed", "skipped"}
            missing_aggregate = required_aggregate_keys.difference(aggregate_summary)
            if missing_aggregate:
                errors.append(f"report aggregateSummary missing keys: {sorted(missing_aggregate)}")

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        errors.append("report results must be a non-empty array")
        return errors

    seen_result_ids: set[str] = set()
    result_ids: list[str] = []
    failing_statuses = {"FAIL", "ERROR"}
    failed_result_count = 0
    for entry in results:
        if not isinstance(entry, dict):
            errors.append("report result entry must be an object")
            continue
        missing_result_keys = REQUIRED_REPORT_RESULT_KEYS.difference(entry)
        if missing_result_keys:
            errors.append(f"report result missing keys: {sorted(missing_result_keys)}")
            continue
        result_id = entry["id"]
        if result_id in seen_result_ids:
            errors.append(f"duplicate report result id: {result_id}")
        seen_result_ids.add(result_id)
        result_ids.append(result_id)
        if entry.get("status") in failing_statuses:
            failed_result_count += 1

    expected_case_set = set(expected_case_ids)
    result_id_set = set(result_ids)
    missing_case_ids = sorted(expected_case_set.difference(result_id_set))
    if missing_case_ids:
        errors.append(f"report missing expected case ids: {missing_case_ids}")
    if require_exact_case_match:
        unexpected_case_ids = sorted(result_id_set.difference(expected_case_set))
        if unexpected_case_ids:
            errors.append(f"report returned unexpected case ids: {unexpected_case_ids}")

    if isinstance(summary, dict):
        total = summary.get("total")
        if isinstance(total, int) and total != len(results):
            errors.append("report summary.total does not match result count")
        if summary.get("status") == "PASS" and failed_result_count:
            errors.append("report summary.status is PASS but results contain failures")

        pass_criteria = profile.get("passCriteria", {}) if isinstance(profile.get("passCriteria"), dict) else {}
        skip_policy = profile.get("skipPolicy", {}) if isinstance(profile.get("skipPolicy"), dict) else {}
        evaluation = aggregate_summary if isinstance(aggregate_summary, dict) else summary
        if pass_criteria.get("policy") == "threshold" and summary.get("status") == "PASS":
            eval_total = evaluation.get("total")
            eval_passed = evaluation.get("passed")
            eval_failed = evaluation.get("failed")
            eval_skipped = evaluation.get("skipped")
            eval_pass_rate = evaluation.get("passRate")
            if isinstance(eval_total, int) and isinstance(eval_passed, int) and isinstance(eval_skipped, int) and not isinstance(eval_pass_rate, (int, float)):
                denom = eval_total - eval_skipped
                eval_pass_rate = 1.0 if denom <= 0 else eval_passed / denom
            minimum_passed = pass_criteria.get("minimumPassed")
            minimum_pass_rate = pass_criteria.get("minimumPassRate")
            if isinstance(eval_failed, int) and eval_failed > 0:
                errors.append("report summary.status is PASS but threshold aggregate contains failures")
            if isinstance(minimum_passed, int) and (not isinstance(eval_passed, int) or eval_passed < minimum_passed):
                errors.append("report summary.status is PASS but aggregate passed count is below profile minimumPassed")
            if isinstance(minimum_pass_rate, (int, float)) and (not isinstance(eval_pass_rate, (int, float)) or float(eval_pass_rate) < float(minimum_pass_rate)):
                errors.append("report summary.status is PASS but aggregate pass rate is below profile minimumPassRate")
            if not bool(skip_policy.get("allowed")) and isinstance(eval_skipped, int) and eval_skipped > 0:
                errors.append("report summary.status is PASS but profile skipPolicy does not allow skips")

    return errors


def ensure_assets_valid_for_paths(root: Path, paths: list[Path]) -> list[str]:
    validator = AssetValidator(root)
    assets, _ = validator.validate()
    errors: list[str] = []
    for path in paths:
        rel = relpath(root, path)
        asset = assets.get(rel)
        if asset is None:
            continue
        for message in asset.errors:
            errors.append(f"{rel}: {message}")
    return errors


def write_report_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def command_list_assets(root: Path) -> int:
    validator = AssetValidator(root)
    asset_map = validator.list_assets()
    for group in ("schemas", "profiles", "vectors", "datasets", "adapters"):
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
        write_report_json(report, write_report)
        print(f"wrote report: {write_report.as_posix()}")

    return 0 if summary["failed"] == 0 else 1


def command_verify_adapter(
    root: Path,
    adapter_manifest_path: Path,
    profile_path: Path,
    dataset_path: Path | None,
    case_ids: list[str],
    write_report: Path | None,
) -> int:
    manifest = load_json_file(adapter_manifest_path)
    profile = load_json_file(profile_path)
    dataset_manifest_path = detect_profile_dataset_path(profile_path, profile, dataset_path)
    dataset_manifest = load_json_file(dataset_manifest_path) if dataset_manifest_path is not None else None
    dataset_version = dataset_manifest.get("version") if dataset_manifest is not None else None

    asset_errors = ensure_assets_valid_for_paths(
        root,
        [path for path in [adapter_manifest_path, profile_path, dataset_manifest_path] if path is not None],
    )
    if asset_errors:
        print("[FAIL] asset-precheck")
        for message in asset_errors:
            print(f"  error: {message}")
        return 2

    available_case_ids = collect_required_case_ids(profile)
    requested_case_ids = case_ids[:] if case_ids else available_case_ids
    unknown_case_ids = sorted(set(requested_case_ids).difference(available_case_ids))
    if unknown_case_ids:
        print("[FAIL] case-selection")
        print(f"  error: unknown case ids for profile {profile.get('profileId')}: {unknown_case_ids}")
        return 2

    print(f"adapter: {manifest.get('adapterId')}")
    print(f"profile: {profile.get('profileId')}")
    if dataset_manifest_path is not None:
        print(f"dataset: {relpath(root, dataset_manifest_path)}")

    try:
        info_outcome = invoke_adapter_command(adapter_manifest_path, manifest, "info", [])
    except ValueError as exc:
        print("[FAIL] info")
        print(f"  error: {exc}")
        return 2

    info_errors: list[str] = []
    if info_outcome.exit_code != 0:
        info_errors.append(f"unexpected exit code: {info_outcome.exit_code}")
    if info_outcome.payload is None:
        info_errors.append("info command did not emit valid JSON")
    else:
        info_errors.extend(validate_adapter_info_payload(info_outcome.payload, manifest))
    if info_errors:
        print("[FAIL] info")
        for message in info_errors:
            print(f"  error: {message}")
        if info_outcome.stderr.strip():
            print(f"  stderr: {info_outcome.stderr.strip()}")
        return 2
    print("[PASS] info")

    capabilities_outcome = invoke_adapter_command(adapter_manifest_path, manifest, "capabilities", [])
    capabilities_errors: list[str] = []
    if capabilities_outcome.exit_code != 0:
        capabilities_errors.append(f"unexpected exit code: {capabilities_outcome.exit_code}")
    if capabilities_outcome.payload is None:
        capabilities_errors.append("capabilities command did not emit valid JSON")
    else:
        capabilities_errors.extend(validate_adapter_capabilities_payload(capabilities_outcome.payload, manifest))
    if capabilities_errors:
        print("[FAIL] capabilities")
        for message in capabilities_errors:
            print(f"  error: {message}")
        if capabilities_outcome.stderr.strip():
            print(f"  stderr: {capabilities_outcome.stderr.strip()}")
        return 2
    print("[PASS] capabilities")

    adapter_args = ["--profile", str(profile_path)]
    if dataset_manifest_path is not None:
        adapter_args.extend(["--dataset", str(dataset_manifest_path)])
    if case_ids:
        for case_id in requested_case_ids:
            adapter_args.extend(["--case", case_id])
        run_command = "run-cases"
    else:
        run_command = "run-profile"

    report_outcome = invoke_adapter_command(adapter_manifest_path, manifest, run_command, adapter_args)
    report_errors: list[str] = []
    if report_outcome.exit_code not in {0, 1}:
        report_errors.append(f"unexpected exit code: {report_outcome.exit_code}")
    if report_outcome.payload is None:
        report_errors.append(f"{run_command} command did not emit valid JSON")
    else:
        report_errors.extend(
            validate_report_payload(
                report_outcome.payload,
                manifest,
                profile,
                requested_case_ids,
                dataset_version,
                require_exact_case_match=bool(case_ids),
            )
        )
    if report_errors:
        print(f"[FAIL] {run_command}")
        for message in report_errors:
            print(f"  error: {message}")
        if report_outcome.stderr.strip():
            print(f"  stderr: {report_outcome.stderr.strip()}")
        return 2

    report = report_outcome.payload
    assert report is not None
    summary = report["summary"]
    print(f"[{summary['status']}] {run_command}")
    print(
        f"adapter summary: total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} skipped={summary['skipped']} status={summary['status']}"
    )

    if write_report is not None:
        write_report_json(report, write_report)
        print(f"wrote report: {write_report.as_posix()}")

    return 0 if summary["status"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenSynaptic conformance repository asset runner")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root path",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-assets", help="list discovered schemas, profiles, vectors, datasets, and adapters")

    validate = subparsers.add_parser("validate-assets", help="validate repository JSON assets and references")
    validate.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="optional path for a generated asset-validation report",
    )

    verify = subparsers.add_parser("verify-adapter", help="invoke an executable adapter manifest and verify the CLI/JSON contract")
    verify.add_argument("--adapter", type=Path, required=True, help="path to the adapter manifest")
    verify.add_argument("--profile", type=Path, required=True, help="path to the conformance profile")
    verify.add_argument("--dataset", type=Path, default=None, help="optional explicit dataset manifest path")
    verify.add_argument("--case", dest="cases", action="append", default=[], help="specific case id to execute; may be repeated")
    verify.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="optional path for the adapter execution report",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "list-assets":
        return command_list_assets(root)
    if args.command == "validate-assets":
        write_report = resolve_cli_path(root, args.write_report) if args.write_report is not None else None
        return command_validate_assets(root, write_report)
    if args.command == "verify-adapter":
        adapter_path = resolve_cli_path(root, args.adapter)
        profile_path = resolve_cli_path(root, args.profile)
        dataset_path = resolve_cli_path(root, args.dataset) if args.dataset is not None else None
        write_report = resolve_cli_path(root, args.write_report) if args.write_report is not None else None
        return command_verify_adapter(root, adapter_path, profile_path, dataset_path, args.cases, write_report)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())