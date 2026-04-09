# Runners

Runners are the shared execution entry points for repository verification workflows.

They should eventually provide:

- profile-based execution
- dataset selection
- adapter loading for each implementation
- deterministic report generation
- CI-friendly exit behavior

The first reference runner can be implemented in Python if it simplifies cross-platform orchestration.
