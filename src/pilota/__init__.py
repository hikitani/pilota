"""Programmable AI agents as ordinary Python expressions."""

from pilota.api import agent
from pilota.execution import run_agent
from pilota.models import (
    Artifact,
    Execution,
    ExecutionStatus,
    FinalResult,
    Limits,
    ToolCall,
    Trace,
    TraceEvent,
    Usage,
)
from pilota.providers import Model, ScriptedModel
from pilota.resources import DirectoryResource, Resource, ResourceOperation
from pilota.tools import Editor, Shell
from pilota.workspaces import DirectoryWorkspace, InMemoryWorkspace

__version__ = "0.1.0"

__all__ = [
    "Artifact",
    "DirectoryResource",
    "DirectoryWorkspace",
    "Editor",
    "Execution",
    "ExecutionStatus",
    "FinalResult",
    "InMemoryWorkspace",
    "Limits",
    "Model",
    "Resource",
    "ResourceOperation",
    "ScriptedModel",
    "Shell",
    "ToolCall",
    "Trace",
    "TraceEvent",
    "Usage",
    "agent",
    "run_agent",
]
