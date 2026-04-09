# Adapter Interface Contract

This document defines the repository-level contract for implementation adapters.

The goal is to let OpenSynaptic Core, OSynaptic-FX, OSynaptic-RX, OSynaptic-TX, and future third-party implementations expose a consistent entry point to the conformance runner without hard-coding implementation-specific details into profiles or datasets.

## Design Rules

1. Profiles, vectors, and datasets remain the protocol truth.
2. Adapters are thin execution bridges.
3. Adapter output must be machine-readable.
4. A future adapter may be distributed from its implementation repository, but it must still honor the contract defined here.

## Transport

The first contract version is `cli-json-v1`.

Adapters are invoked as command-line programs. Human-readable logs may go to stderr, but structured output must be emitted on stdout as JSON.

## Required Commands

Every compliant adapter must expose these logical commands:

1. `info`
Purpose: emit adapter identity, implementation metadata, and protocol version.

2. `capabilities`
Purpose: emit supported roles, profiles, packet modes, and known limits.

3. `run-profile`
Purpose: execute an entire conformance profile and emit a report compatible with the repository report schema.

4. `run-cases`
Purpose: execute one or more specific cases from a profile or dataset and emit a report compatible with the repository report schema.

## Expected CLI Shape

Concrete binary names are implementation-specific, but the contract is expected to map to a CLI shape similar to:

```text
adapter info --json
adapter capabilities --json
adapter run-profile --profile <path> --json
adapter run-profile --profile <path> --dataset <path> --json
adapter run-cases --profile <path> --case <id> --case <id> --json
```

Additional options are allowed as long as these commands remain stable.

## Output Contract

- `info` returns a JSON object compatible with [adapter-info.schema.json](../schemas/adapter-info.schema.json).
- `capabilities` returns a JSON object compatible with [adapter-capabilities.schema.json](../schemas/adapter-capabilities.schema.json).
- `run-profile` and `run-cases` return JSON compatible with [report.schema.json](../schemas/report.schema.json).

## Executable Manifests

Planned adapters may exist only as manifests.

Once an adapter becomes executable, its manifest should include an `invocation` block that tells shared runners how to launch it. The first supported invocation styles are:

- `python-script`: repository-local or adapter-local Python entry points launched with the current Python interpreter
- `command`: external binaries or wrapper commands with fixed argv

This lets the repository keep one generic runner while still supporting different implementation repositories.

## Exit Codes

The reserved meanings are:

- `0`: success, report status may still be PASS or FAIL depending on test results
- `1`: validation failure or profile failure occurred and a report was still produced
- `2`: usage error or invalid invocation
- `3`: adapter execution error, environment error, or unrecoverable runtime fault

## Profile Resolution

Adapters must not redefine the meaning of a profile.

The adapter may filter cases that are genuinely not applicable to the implementation, but it must do so transparently in its report output. It must not silently reinterpret required cases.

## Dataset Resolution

If a profile references a dataset manifest, the adapter must either:

- consume the dataset manifest directly, or
- document how that dataset is deterministically translated into implementation-specific fixtures.

## Reporting Rule

When an adapter executes `run-profile` or `run-cases`, the output must identify:

- the profile id
- the dataset version if one was used
- the implementation name and version
- the adapter id
- per-case results
- summary totals and final status

## Status Model

Adapter manifests in this repository may be marked `planned` before a concrete implementation exists. That still has value because it freezes the interface contract and supported profile surface.

Executable examples may be marked `active` when they are runnable from this repository. The repository-local mock adapter exists for exactly this purpose: it gives CI and adapter authors a deterministic contract target before Core, FX, RX, and TX publish their own production adapters.
