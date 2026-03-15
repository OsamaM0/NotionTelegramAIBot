"""Core abstractions shared between platform (bot) and data-source (Notion) layers."""

from src.core.platform import PlatformConfig
from src.core.protocols import AgentService, DataSourceProvider

__all__ = ["AgentService", "DataSourceProvider", "PlatformConfig"]
