"""Imports every module with checks so that their @register runs.

Catalog of checks v1: docs/tech-design/05_ci.md (22 checks).
"""

from reqgraph.checks import iso, schema, sound, template, trace  # noqa: F401 - registration
