# Datasets

Datasets capture larger compatibility inputs than single vectors.

Recommended categories:

- canonical datasets for stable baseline checks
- exhaustive datasets for large-scale validation
- generated datasets produced from checked-in scripts and fixed seeds

Repository policy:

- keep small stable datasets in Git
- keep generation rules in Git for larger datasets
- avoid committing large transient output unless it is part of a versioned baseline

Current dataset directories:

- [Canonical datasets](canonical/README.md)
- [Exhaustive datasets](exhaustive/README.md)

Current seeded manifests:

- [L2 interoperability dataset](canonical/l2-interoperability.dataset.v1.json)
- [L3 fusion dataset](canonical/l3-fusion.dataset.v1.json)
- [L4 security dataset](canonical/l4-security.dataset.v1.json)
- [L5 ecosystem dataset](exhaustive/l5-full-ecosystem.dataset.v1.json)
