# Adapters

Adapters connect a concrete implementation to the shared conformance workflows.

Typical adapter responsibilities include:

- invoking encode or decode entry points
- normalizing implementation output into repository schemas
- declaring capability limits such as RX-only or TX-only support
- exposing stable commands for automated runners

Adapters should be thin and implementation-specific. The protocol truth belongs in profiles, vectors, datasets, and schemas.
