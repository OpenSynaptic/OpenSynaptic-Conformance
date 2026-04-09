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

Bootstrap phase.

The initial repository goal is to establish a stable structure for documentation, vectors, datasets, schemas, runners, and reports so that future protocol verification work is versioned independently from implementation repositories.

Seeded documents already present in this repository:

- [OpenSynaptic Technical Whitepaper](docs/whitepaper/OpenSynaptic_Technical_Whitepaper.md)
- [OpenSynaptic Certification Process](docs/certification/OpenSynaptic_Certification_Process.md)

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
| `runners/` | Shared execution entry points for verification workflows |
| `adapters/` | Per-implementation integration layers |
| `reports/` | Baseline conformance reports and compatibility summaries |

## Relationship To Certification

Conformance is the technical base layer.

If OpenSynaptic later formalizes a public certification program, that program should reference tagged versions of this repository rather than replace it. In other words, a future certification outcome should always read like:

> based on OpenSynaptic-Conformance vX.Y

This keeps policy and branding separate from the reproducible technical evidence.

## Initial Milestones

1. Move the whitepaper and certification process into versioned documentation under `docs/`.
2. Publish the first machine-readable L1 and L2 profiles.
3. Add CRC, Base62, FULL, DIFF, HEART, and control-command golden vectors.
4. Define report schemas for official baseline output.
5. Ship a reference runner that can verify OpenSynaptic Core, FX, RX, and TX against the same assets.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for repository scope, contribution rules, and expectations for deterministic verification assets.

## Current Documentation Entry Points

- Whitepaper index: [docs/whitepaper/README.md](docs/whitepaper/README.md)
- Certification index: [docs/certification/README.md](docs/certification/README.md)
- Documentation overview: [docs/README.md](docs/README.md)

## Related Repositories

- OpenSynaptic Core: https://github.com/OpenSynaptic/OpenSynaptic
- OSynaptic-FX: https://github.com/OpenSynaptic/OSynaptic-FX
- OSynaptic-RX: https://github.com/OpenSynaptic/OSynaptic-RX
- OSynaptic-TX: https://github.com/OpenSynaptic/OSynaptic-TX
