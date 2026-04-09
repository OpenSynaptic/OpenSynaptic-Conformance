# Profiles

Profiles define machine-readable verification targets.

Each profile should specify:

- the scope of behavior under test
- the required vectors and datasets
- the allowed implementation capabilities
- the expected report structure
- the pass and skip policy

The repository is expected to grow toward versioned profiles for:

- L1 wire compatibility
- L2 protocol conformance
- L3 fusion behavior
- L4 security validation
- L5 full ecosystem equivalence

Current profiles:

- [L1 Wire Compatible v1](l1-wire-compatible/l1-wire-compatible.profile.v1.json)
- [L2 Protocol Conformant v1](l2-protocol-conformant/l2-protocol-conformant.profile.v1.json)
