# Contributing To OpenSynaptic-Conformance

This repository exists to define and execute neutral, reproducible verification for the OpenSynaptic ecosystem.

Before opening a pull request, make sure the proposed change belongs in this repository rather than in an implementation repository.

## What Belongs Here

- protocol or behavior specifications
- conformance profile definitions
- golden vectors and canonical datasets
- reproducible dataset generators
- report schemas and baseline reports
- shared verification runners and adapters
- documentation that explains how verification is performed

## What Does Not Belong Here

- implementation-only refactors for Core, FX, RX, or TX
- unrelated application examples
- temporary logs or one-off benchmark dumps
- unverifiable compatibility claims without assets to reproduce them

## Contribution Rules

1. Keep artifacts deterministic. A result must be reproducible from committed inputs.
2. Version every public contract that affects compatibility, including profiles, schemas, and datasets.
3. Prefer compact canonical datasets over large opaque blobs.
4. If a large dataset is necessary, commit the generator and seed, and store the bulk artifact outside the default Git path when appropriate.
5. Keep policy claims separate from technical evidence. Certification language should reference a specific conformance version.

## Pull Request Expectations

Each pull request should state:

- the repository area being changed
- the compatibility surface affected
- whether a schema, profile, vector, or dataset version changed
- how the change is validated

If a pull request changes normative behavior, include at least one of the following:

- updated golden vectors
- updated profile definitions
- updated baseline reports
- updated documentation that explains the behavior change

## Recommended Workflow

1. Document the change in `docs/` first.
2. Add or update vectors, datasets, and schemas as needed.
3. Run the appropriate shared verification workflow.
4. Regenerate any committed baseline report that is intentionally affected.

## Repository Principles

- Keep implementation-neutral language whenever possible.
- Favor machine-readable assets over prose-only requirements.
- Treat compatibility claims as evidence-backed outputs, not opinions.
