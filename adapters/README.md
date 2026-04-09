# Adapters

Adapters connect a concrete implementation to the shared conformance workflows.

Typical adapter responsibilities include:

- invoking encode or decode entry points
- normalizing implementation output into repository schemas
- declaring capability limits such as RX-only or TX-only support
- exposing stable commands for automated runners

Adapters should be thin and implementation-specific. The protocol truth belongs in profiles, vectors, datasets, and schemas.

Current adapter contract assets:

- [Adapter interface contract](INTERFACE.md)
- [OpenSynaptic Core manifest](core/manifest.v1.json)
- [OSynaptic-FX manifest](fx/manifest.v1.json)
- [OSynaptic-RX manifest](rx/manifest.v1.json)
- [OSynaptic-TX manifest](tx/manifest.v1.json)
