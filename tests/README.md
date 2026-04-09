# Tests

This directory stores repository-owned verification for the conformance infrastructure itself.

Current coverage focuses on the Python runner and the executable mock adapter contract. These tests are intentionally repository-local and do not require cloning implementation repositories.

Real-adapter smoke coverage now lives alongside the runner entry points in [runners/python/real_adapter_smoke.py](../runners/python/real_adapter_smoke.py). It requires sibling checkouts of OpenSynaptic, OSynaptic-FX, OSynaptic-RX, and OSynaptic-TX, so it is kept out of the repository-local unittest suite.