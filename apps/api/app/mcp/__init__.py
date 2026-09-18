"""MCP client integration for VibesFactory."""

from .contracts import (
    MCPConnectionSnapshot,
    MCPInvocationResult,
    MCPToolDescriptor,
)
from .manager import MCPManager

__all__ = [
    "MCPConnectionSnapshot",
    "MCPInvocationResult",
    "MCPManager",
    "MCPToolDescriptor",
]
