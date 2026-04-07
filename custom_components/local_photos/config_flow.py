"""
Config flow for local_photos.

This module provides backwards compatibility for hassfest.
The actual implementation is in the config_flow_handler package.
"""

from __future__ import annotations

from .config_flow_handler import LocalPhotosConfigFlowHandler

__all__ = ["LocalPhotosConfigFlowHandler"]
