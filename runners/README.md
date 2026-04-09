# Runners

Runners are the shared execution entry points for repository verification workflows.

They should eventually provide:

- profile-based execution
- dataset selection
- adapter loading for each implementation
- deterministic report generation
- CI-friendly exit behavior

Current runner entry point:

- [Python runner README](python/README.md)
- [Python conformance runner](python/conformance_runner.py)

The first reference runner is implemented in Python to keep asset validation cross-platform and repository-local.
