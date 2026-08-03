"""Gateway-layer LLM security controls.

Layering rule enforced by tests: `canonical` and `policy` perform no I/O.
Scanners detect and never decide; `policy` decides and never detects.
"""
