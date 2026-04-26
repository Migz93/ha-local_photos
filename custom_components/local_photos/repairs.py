"""Repairs platform for local_photos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.repairs import RepairsFlow
from homeassistant.data_entry_flow import FlowResult

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a repair flow based on the issue_id."""
    if issue_id == "directory_not_found":
        return DirectoryNotFoundRepairFlow()
    return UnknownIssueRepairFlow()


class DirectoryNotFoundRepairFlow(RepairsFlow):
    """Repair flow for a missing photos directory."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Prompt the user to reconfigure the integration."""
        if user_input is not None:
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="init")


class UnknownIssueRepairFlow(RepairsFlow):
    """Fallback repair flow for unknown issues."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Acknowledge the issue."""
        if user_input is not None:
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="init")
