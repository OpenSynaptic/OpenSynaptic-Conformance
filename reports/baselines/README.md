# Baseline Reports

This directory contains official baseline reports published by the OpenSynaptic project.

Each baseline report references:

- repository version (git commit)
- profile version
- dataset version
- implementation version
- execution timestamp

Generated local output belongs under `reports/generated/` instead of this directory.

## Published Baselines

The following mock adapter baselines were published to freeze the contract coverage for all five conformance levels. They serve as the authoritative pass baseline for repository-owned CI.

| File | Profile | Adapter | Status |
| --- | --- | --- | --- |
| [mock-adapter.l1.baseline.v1.json](mock-adapter.l1.baseline.v1.json) | L1 Wire Compatible | opensynaptic-mock | PASS (34/34) |
| [mock-adapter.l2.baseline.v1.json](mock-adapter.l2.baseline.v1.json) | L2 Protocol Conformant | opensynaptic-mock | PASS (8/8) |
| [mock-adapter.l3.baseline.v1.json](mock-adapter.l3.baseline.v1.json) | L3 Fusion Certified | opensynaptic-mock | PASS (6/6) |
| [mock-adapter.l4.baseline.v1.json](mock-adapter.l4.baseline.v1.json) | L4 Security Validated | opensynaptic-mock | PASS (13/13) |
| [mock-adapter.l5.baseline.v1.json](mock-adapter.l5.baseline.v1.json) | L5 Full Ecosystem | opensynaptic-mock | PASS (4 suites · 1255/1257 aggregate) |

## Promotion Policy

Mock adapter baseline reports may be promoted here when:

1. All required cases for the target profile pass without adapter `ERROR`.
2. The repository tag or commit is recorded in `repositoryVersion`.
3. The corresponding profile `status` is `stable` or the report is explicitly marked as a draft baseline.

Real-adapter baseline reports should be promoted here once a real adapter achieves a clean run (zero `ERROR`, FAIL count within the certified skip budget) against the matching profile.
