# Canonical Datasets

This directory is for stable, versioned dataset snapshots that are small enough to commit directly.

Expected near-term contents:

- canonical sensor payload sets for interoperability checks
- deterministic packet samples referenced by profiles
- compact fixtures that should remain stable across multiple releases

Large exhaustive corpora should be generated from checked-in rules and stored outside this path unless the snapshot itself is intentionally part of a published baseline.

Current manifests:

- [L2 interoperability dataset](l2-interoperability.dataset.v1.json)
- [L3 fusion dataset](l3-fusion.dataset.v1.json)
- [L4 security dataset](l4-security.dataset.v1.json)
