from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "runners" / "python" / "conformance_runner.py"
MOCK_MANIFEST = ROOT / "adapters" / "mock" / "manifest.v1.json"
L1_PROFILE = ROOT / "profiles" / "l1-wire-compatible" / "l1-wire-compatible.profile.v1.json"
L3_PROFILE = ROOT / "profiles" / "l3-fusion-certified" / "l3-fusion-certified.profile.v1.json"


class RunnerCliTests(unittest.TestCase):
    def run_runner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_validate_assets_passes(self) -> None:
        result = self.run_runner("validate-assets")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("status=PASS", result.stdout)

    def test_verify_mock_adapter_l1_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter",
            str(MOCK_MANIFEST),
            "--profile",
            str(L1_PROFILE),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("[PASS] info", result.stdout)
        self.assertIn("[PASS] capabilities", result.stdout)
        self.assertIn("adapter summary:", result.stdout)

    def test_verify_mock_adapter_selected_l3_case_passes(self) -> None:
        result = self.run_runner(
            "verify-adapter",
            "--adapter",
            str(MOCK_MANIFEST),
            "--profile",
            str(L3_PROFILE),
            "--case",
            "L3-CROSS-01",
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("profile: opensynaptic.l3-fusion-certified", result.stdout)
        self.assertIn("[PASS] run-cases", result.stdout)


if __name__ == "__main__":
    unittest.main()