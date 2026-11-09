---
name: "API and Coordinator"
description: "Compatibility entry point for the current API client and coordinator instructions"
applyTo: "custom_components/**/api/**/*.py, custom_components/**/coordinator/**/*.py"
paths:
  - "custom_components/**/api/**/*.py"
  - "custom_components/**/coordinator/**/*.py"
---

# API and Coordinator Instructions

Read the [current API client and coordinator instructions](blueprint.coordinator.instructions.md) for API client
layering, exception mapping, rate limiting, session ownership, and coordinator lifecycle.

That shared guide is the authoritative source for these rules. This entry point preserves existing project links.
