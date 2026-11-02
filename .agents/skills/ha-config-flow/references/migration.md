# When a config entry migration fails

This repository supports **Home Assistant 2026.8.0**. On that release, `async_migrate_entry()` returns a boolean.
Log an actionable explanation and return `False` when migration cannot safely complete. Home Assistant marks the
entry as a migration error; raising `ConfigEntryNotReady` does not automatically retry it.

Keep stored data intact until every migration prerequisite is satisfied. A repair can explain how to correct the
problem; create it with `is_fixable=True`, severity `ERROR`, the entry ID in `data`, and a matching repair flow.
Once corrected, have the user restart Home Assistant to retry migration. Remove the issue after migration succeeds.
Do not finish a repair with `async_create_entry(data={})` before its underlying problem is fixed.

`hass.config_entries.async_retry_migration()` and exception-based migration retry handling are newer APIs, absent
from 2026.8.0. Do not call them on this baseline or raise the minimum version as incidental cleanup.
