"""Repairs platform for local_photos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.repairs import RepairsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

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


def async_update_no_usable_photos_issue(hass: HomeAssistant, entry_id: str, has_usable_photos: bool) -> None:
    """Create or clear the concise repair for an empty usable catalog."""
    issue_id = f"no_usable_photos_{entry_id}"
    if has_usable_photos:
        ir.async_delete_issue(hass=hass, domain=DOMAIN, issue_id=issue_id)
        return
    ir.async_create_issue(
        hass=hass,
        domain=DOMAIN,
        issue_id=issue_id,
        data={"entry_id": entry_id},
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="no_usable_photos",
    )


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
