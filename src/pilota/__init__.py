"""Programmable AI agents as ordinary Python expressions."""

from pilota.api import agent
from pilota.execution import run_agent
from pilota.instructions import Instruction, InstructionFile
from pilota.models import (
    RESULT_TOOL_NAME,
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
    "RESULT_TOOL_NAME",
    "Artifact",
    "DirectoryResource",
    "DirectoryWorkspace",
    "Editor",
    "Execution",
    "ExecutionStatus",
    "FinalResult",
    "InMemoryWorkspace",
    "Instruction",
    "InstructionFile",
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
