# Python Runner

This runner validates repository assets without depending on any implementation repository.

Current capabilities:

- list discovered schemas, profiles, and vector sets
- validate JSON asset parsing and required top-level fields
- validate file references between profiles, vectors, datasets, adapters, and schemas
- verify that profile-required vector and dataset case IDs exist in the referenced manifests
- verify that adapter manifests reference known profile ids and valid report schemas
- emit a machine-readable asset-validation report

Example usage:

```bash
python runners/python/conformance_runner.py list-assets
python runners/python/conformance_runner.py validate-assets
python runners/python/conformance_runner.py validate-assets --write-report reports/generated/assets-validation.report.json
```

This runner is the first repository-local execution step. Future adapters can extend it to execute the same profiles against OpenSynaptic Core, FX, RX, TX, and third-party implementations.
