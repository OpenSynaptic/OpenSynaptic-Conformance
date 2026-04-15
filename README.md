# OpenSynaptic-Conformance

Specification, conformance assets, datasets, and tooling for verifying implementations of the OpenSynaptic ecosystem.

This repository is the neutral source of truth for:

- protocol and behavior requirements
- conformance profiles
- golden vectors and canonical datasets
- report schemas and baseline results
- cross-implementation runners and adapters

It does not host the production implementation source code for OpenSynaptic Core, OSynaptic-FX, OSynaptic-RX, or OSynaptic-TX. Those repositories implement the protocol. This repository defines how compatibility is measured and reproduced.

## Status

**Current phase: Adapter integration** — all initial infrastructure milestones are complete.

The repository now has stable machine-readable profiles, datasets, schemas, adapter manifests, an executable mock adapter, CI-ready runner entry points, active repository-backed adapters for OpenSynaptic Core, OSynaptic-FX, OSynaptic-RX, and OSynaptic-TX, and published mock adapter baseline reports for all five conformance levels.

Current validation posture:

- L1 and L2 profiles are **stable**; L3 and L4 are **draft** pending clean real-adapter runs
- mock adapter runs L1–L5 all pass and serve as the strict PASS baseline for repository-owned contract coverage
- real adapters are wired into smoke validation against representative profiles
- real-adapter smoke treats contract/runtime `ERROR` as regressions while preserving honest `FAIL` and `SKIP` results for current implementation gaps

**Next steps:**

- resolve remaining `FAIL`/`SKIP` results in real-adapter smoke runs
- promote L3 and L4 profiles to `stable` once real-adapter runs are clean
- advance `config/sibling-refs.json` after each revalidated release
- promote real-adapter baseline reports to `reports/baselines/` once a clean run is achieved

Seeded documents already present in this repository:

- [OpenSynaptic Technical Whitepaper](docs/whitepaper/OpenSynaptic_Technical_Whitepaper.md)
- [OpenSynaptic Certification Process](docs/certification/OpenSynaptic_Certification_Process.md)

Published mock adapter baselines (see [reports/baselines/](reports/baselines/)):

| Profile | Cases | Aggregate |
| --- | --- | --- |
| L1 Wire Compatible | 34/34 | — |
| L2 Protocol Conformant | 8/8 | — |
| L3 Fusion Certified | 6/6 | — |
| L4 Security Validated | 13/13 | — |
| L5 Full Ecosystem | 4 suites | 1255/1257 (skipped=2) |

Seeded machine-readable assets already present in this repository:

- [L1 Wire Compatible profile](profiles/l1-wire-compatible/l1-wire-compatible.profile.v1.json)
- [L2 Protocol Conformant profile](profiles/l2-protocol-conformant/l2-protocol-conformant.profile.v1.json)
- [L3 Fusion Certified profile](profiles/l3-fusion-certified/l3-fusion-certified.profile.v1.json)
- [L4 Security Validated profile](profiles/l4-security-validated/l4-security-validated.profile.v1.json)
- [L5 Full Ecosystem profile](profiles/l5-full-ecosystem/l5-full-ecosystem.profile.v1.json)
- [L1 CRC reference vectors](vectors/crc/l1-crc.reference.v1.json)
- [L1 Base62 reference vectors](vectors/base62/l1-base62.reference.v1.json)
- [L2 interoperability dataset](datasets/canonical/l2-interoperability.dataset.v1.json)
- [L3 fusion dataset](datasets/canonical/l3-fusion.dataset.v1.json)
- [L4 security dataset](datasets/canonical/l4-security.dataset.v1.json)
- [L5 ecosystem dataset](datasets/exhaustive/l5-full-ecosystem.dataset.v1.json)
- [Adapter interface contract](adapters/INTERFACE.md)
- [Mock adapter manifest](adapters/mock/manifest.v1.json)
- [Profile schema](schemas/profile.schema.json)
- [Vector-set schema](schemas/vector-set.schema.json)
- [Report schema](schemas/report.schema.json)
- [Dataset-manifest schema](schemas/dataset-manifest.schema.json)
- [Adapter-manifest schema](schemas/adapter-manifest.schema.json)
- [Adapter-info schema](schemas/adapter-info.schema.json)
- [Adapter-capabilities schema](schemas/adapter-capabilities.schema.json)

## Why This Repository Exists

OpenSynaptic already spans multiple implementations and targets:

- OpenSynaptic Core for the reference server and protocol runtime
- OSynaptic-FX for full embedded encoding and fusion behavior
- OSynaptic-RX for constrained decoding on low-end MCUs
- OSynaptic-TX for minimal transmit-only encoding

As the ecosystem grows, validation assets should not live inside only one implementation repository. Keeping them here prevents drift between repositories and makes third-party verification possible.

## Scope

This repository is intended to contain:

- technical whitepaper and certification documentation
- machine-readable conformance profiles for L1 to L5 verification
- golden vectors for CRC, Base62, frame layout, commands, and behavior
- canonical and exhaustive datasets, or reproducible generators for them
- schemas for reports, profiles, and vector definitions
- shared runners and adapters that execute checks against multiple implementations
- baseline reports for official OpenSynaptic releases

## Out Of Scope

This repository should not become:

- another implementation repository
- a general application demo repository
- a dump for large transient logs or ad-hoc local test output
- the place where implementation-specific unit tests replace protocol-level conformance assets

## Repository Layout

| Path | Purpose |
| --- | --- |
| `docs/` | Whitepaper, certification, protocol notes, and operational guidance |
| `profiles/` | Versioned conformance profiles and level definitions |
| `vectors/` | Golden vectors and known-answer test inputs/outputs |
| `datasets/` | Canonical datasets, exhaustive datasets, and generators |
| `schemas/` | JSON schemas or equivalent contracts for repository artifacts |
| `config/` | Locked sibling implementation revisions and other reproducibility inputs |
| `runners/` | Shared execution entry points for verification workflows |
| `adapters/` | Per-implementation integration layers |
| `reports/` | Baseline conformance reports and compatibility summaries |
| `tests/` | Repository-local verification for runners, schemas, and adapters |

## Relationship To Certification

Conformance is the technical base layer.

If OpenSynaptic later formalizes a public certification program, that program should reference tagged versions of this repository rather than replace it. In other words, a future certification outcome should always read like:

> based on OpenSynaptic-Conformance vX.Y

This keeps policy and branding separate from the reproducible technical evidence.

## Initial Milestones

1. ✅ Move the whitepaper and certification process into versioned documentation under `docs/`.
2. ✅ Publish the first machine-readable L1 and L2 profiles.
3. ✅ Add CRC, Base62, FULL, DIFF, HEART, and control-command golden vectors.
4. ✅ Define report schemas for official baseline output.
5. ✅ Ship a reference runner that can verify OpenSynaptic Core, FX, RX, and TX against the same assets.
6. ✅ Freeze an executable adapter contract with repository-owned smoke coverage and CI enforcement.

## Data And Reproducibility Policy

Small, stable golden vectors should be committed directly.

Large exhaustive datasets should be stored as one of the following:

- compact canonical snapshots that are stable across releases
- generated artifacts with a checked-in generator and fixed seed
- release assets or Git LFS objects when repository size would otherwise become unmanageable

Every certification or compatibility claim should be traceable to:

- a repository tag or commit
- a profile version
- a dataset version
- a generated report artifact

The repository-owned validate workflow also resolves sibling implementation checkouts from [config/sibling-refs.json](config/sibling-refs.json). That lock file is the reproducible input for ecosystem smoke validation and should only be advanced intentionally after the corresponding compatibility baseline has been revalidated.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository scope, contribution rules, and expectations for deterministic verification assets.

## Current Documentation Entry Points

- Whitepaper index: [docs/whitepaper/README.md](docs/whitepaper/README.md)
- Certification index: [docs/certification/README.md](docs/certification/README.md)
- Documentation overview: [docs/README.md](docs/README.md)

## Current Machine-Readable Entry Points

- Profiles index: [profiles/README.md](profiles/README.md)
- Vectors index: [vectors/README.md](vectors/README.md)
- Schemas index: [schemas/README.md](schemas/README.md)
- Datasets index: [datasets/README.md](datasets/README.md)
- Adapters index: [adapters/README.md](adapters/README.md)
- Reports index: [reports/README.md](reports/README.md)
- Runner index: [runners/README.md](runners/README.md)
- Tests index: [tests/README.md](tests/README.md)

## Current Real-Adapter Snapshot

- OpenSynaptic Core adapter is active, passes L1 end-to-end, and now reduces L4 security failures to the remaining timestamp replay API gap.
- OSynaptic-FX, OSynaptic-RX, and OSynaptic-TX adapters are active and smoke-stable: they emit valid reports without adapter execution errors, while remaining FAIL cases reflect current runtime incompatibilities rather than harness faults.

## Related Repositories

- OpenSynaptic Core: https://github.com/OpenSynaptic/OpenSynaptic
- OSynaptic-FX: https://github.com/OpenSynaptic/OSynaptic-FX
- OSynaptic-RX: https://github.com/OpenSynaptic/OSynaptic-RX
- OSynaptic-TX: https://github.com/OpenSynaptic/OSynaptic-TX
