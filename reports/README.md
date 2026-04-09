# Reports

This directory stores versioned baseline reports and compatibility summaries.

Recommended usage:

- commit official baseline reports that correspond to tagged releases
- keep generated local reports under `reports/generated/`, which is ignored by Git
- ensure every published report references a repository version, profile version, and dataset version

Future additions can include compatibility matrices, badge inputs, and release-level summary pages.

Repository-generated mock adapter reports are expected to live under `reports/generated/` in CI and local development. Only stable, versioned baselines should be promoted into `reports/baselines/`.

Current report directories:

- [Baseline reports](baselines/README.md)
