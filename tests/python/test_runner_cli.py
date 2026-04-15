from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "runners" / "python" / "conformance_runner.py"
MOCK_MANIFEST = ROOT / "adapters" / "mock" / "manifest.v1.json"
L1_PROFILE = ROOT / "profiles" / "l1-wire-compatible" / "l1-wire-compatible.profile.v1.json"
L2_PROFILE = ROOT / "profiles" / "l2-protocol-conformant" / "l2-protocol-conformant.profile.v1.json"
L3_PROFILE = ROOT / "profiles" / "l3-fusion-certified" / "l3-fusion-certified.profile.v1.json"
L4_PROFILE = ROOT / "profiles" / "l4-security-validated" / "l4-security-validated.profile.v1.json"
L5_PROFILE = ROOT / "profiles" / "l5-full-ecosystem" / "l5-full-ecosystem.profile.v1.json"


class RunnerCliTests(unittest.TestCase):
    def run_runner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    # ------------------------------------------------------------------
    # validate-assets
    # ------------------------------------------------------------------

    def test_validate_assets_passes(self) -> None:
        result = self.run_runner("validate-assets")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("status=PASS", result.stdout)

    def test_validate_assets_total_covers_all_known_entries(self) -> None:
        result = self.run_runner("validate-assets")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        # At minimum: 5 profiles + 4 vector sets + 4 datasets + 7 schemas + 4 adapters = 24
        import re
        match = re.search(r"total=(\d+)", result.stdout)
        self.assertIsNotNone(match, "no total= in output")
        self.assertGreaterEqual(int(match.group(1)), 24)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # list-assets
    # ------------------------------------------------------------------

    def test_list_assets_runs(self) -> None:
        result = self.run_runner("list-assets")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        for section in ("profiles", "schemas", "vectors", "datasets", "adapters"):
            self.assertIn(section, result.stdout)

    def test_list_assets_contains_all_profiles(self) -> None:
        result = self.run_runner("list-assets")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        for profile_id in (
            "opensynaptic.l1-wire-compatible",
            "opensynaptic.l2-protocol-conformant",
            "opensynaptic.l3-fusion-certified",
            "opensynaptic.l4-security-validated",
            "opensynaptic.l5-full-ecosystem",
        ):
            self.assertIn(profile_id, result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — mock adapter L1 (full profile)
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_l1_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L1_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("[PASS] info", result.stdout)
        self.assertIn("[PASS] capabilities", result.stdout)
        self.assertIn("adapter summary:", result.stdout)
        self.assertIn("status=PASS", result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — mock adapter L2
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_l2_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L2_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l2-protocol-conformant", result.stdout)
        self.assertIn("[PASS] run-profile", result.stdout)
        self.assertIn("status=PASS", result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — mock adapter L3
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_l3_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L3_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l3-fusion-certified", result.stdout)
        self.assertIn("[PASS] run-profile", result.stdout)
        self.assertIn("status=PASS", result.stdout)

    def test_verify_mock_adapter_selected_l3_case_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L3_PROFILE),
            "--case", "L3-CROSS-01",
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l3-fusion-certified", result.stdout)
        self.assertIn("[PASS] run-cases", result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — mock adapter L4
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_l4_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L4_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l4-security-validated", result.stdout)
        self.assertIn("[PASS] run-profile", result.stdout)
        self.assertIn("status=PASS", result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — mock adapter L5 (threshold profile)
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_l5_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter", str(MOCK_MANIFEST),
            "--profile", str(L5_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l5-full-ecosystem", result.stdout)
        self.assertIn("[PASS] run-profile", result.stdout)
        self.assertIn("status=PASS", result.stdout)

    # ------------------------------------------------------------------
    # verify-adapter — report written to disk and is valid JSON
    # ------------------------------------------------------------------

    def test_verify_mock_adapter_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"
            result = self.run_runner(
                "verify-adapter",
                "--adapter", str(MOCK_MANIFEST),
                "--profile", str(L1_PROFILE),
                "--write-report", str(report_path),
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue(report_path.exists(), "report file was not created")
            with report_path.open("r", encoding="utf-8") as fh:
                report = json.load(fh)
            self.assertEqual(report.get("kind"), "conformance-report")
            self.assertEqual(report.get("summary", {}).get("status"), "PASS")

    def test_verify_mock_adapter_l5_report_has_aggregate_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "l5-report.json"
            result = self.run_runner(
                "verify-adapter",
                "--adapter", str(MOCK_MANIFEST),
                "--profile", str(L5_PROFILE),
                "--write-report", str(report_path),
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            with report_path.open("r", encoding="utf-8") as fh:
                report = json.load(fh)
            agg = report.get("aggregateSummary")
            self.assertIsNotNone(agg, "L5 report must include aggregateSummary")
            self.assertGreaterEqual(agg["passed"], 1253, "aggregate passed must meet minimumPassed=1253")
            self.assertEqual(agg["failed"], 0)


if __name__ == "__main__":
    unittest.main()