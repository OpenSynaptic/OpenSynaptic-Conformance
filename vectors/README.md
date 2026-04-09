# Vectors

This directory stores golden vectors and known-answer test cases.

Typical vector groups include:

- CRC-8 and CRC-16 reference cases
- Base62 encode and decode cases
- FULL frame construction cases
- DIFF and HEART behavior cases
- control command payload and byte-order cases

Vectors should stay compact, deterministic, and easy to inspect.

Current vector sets:

- [L1 CRC reference vectors](crc/l1-crc.reference.v1.json)
- [L1 Base62 reference vectors](base62/l1-base62.reference.v1.json)
- [L1 frame reference vectors](frame/l1-frame.reference.v1.json)
- [Protocol command reference](commands/protocol-commands.reference.v1.json)
