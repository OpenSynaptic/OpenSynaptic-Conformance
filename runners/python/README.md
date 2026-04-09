# Python Runner

This runner validates repository assets without depending on any implementation repository.

Current capabilities:

- list discovered schemas, profiles, and vector sets
- validate JSON asset parsing and required top-level fields
- validate file references between profiles, vectors, datasets, adapters, and schemas
- verify that profile-required vector and dataset case IDs exist in the referenced manifests
- verify that adapter manifests reference known profile ids and valid report schemas
- verify executable adapter manifests via `info`, `capabilities`, `run-profile`, and `run-cases`
- emit a machine-readable asset-validation report

Example usage:

```bash
python runners/python/conformance_runner.py list-assets
python runners/python/conformance_runner.py validate-assets
python runners/python/conformance_runner.py validate-assets --write-report reports/generated/assets-validation.report.json
python runners/python/conformance_runner.py verify-adapter --adapter adapters/mock/manifest.v1.json --profile profiles/l1-wire-compatible/l1-wire-compatible.profile.v1.json
python runners/python/conformance_runner.py verify-adapter --adapter adapters/mock/manifest.v1.json --profile profiles/l3-fusion-certified/l3-fusion-certified.profile.v1.json --case L3-CROSS-01
python runners/python/real_adapter_smoke.py
```

This runner is now the repository-local execution entry point for both asset validation and adapter contract verification. The included mock adapter gives CI a strict PASS baseline, while `real_adapter_smoke.py` exercises the active real adapters and fails only on contract/runtime `ERROR` conditions.
