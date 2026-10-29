"""Programmable AI agents as ordinary Python expressions."""

from pilota.api import agent
from pilota.execution import run_agent
from pilota.human import Answer, Human, NoHuman, Question, TerminalHuman
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
from pilota.progress import TerminalProgress
from pilota.providers import Model, ScriptedModel
from pilota.resources import DirectoryResource, Resource, ResourceOperation
from pilota.tools import AskHuman, Editor, Shell
from pilota.tracing import ProgressCallback
from pilota.workspaces import DirectoryWorkspace, InMemoryWorkspace

__version__ = "0.0.2"

__all__ = [
    "RESULT_TOOL_NAME",
    "Answer",
    "Artifact",
    "AskHuman",
    "DirectoryResource",
    "DirectoryWorkspace",
    "Editor",
    "Execution",
    "ExecutionStatus",
    "FinalResult",
    "Human",
    "InMemoryWorkspace",
    "Instruction",
    "InstructionFile",
    "Limits",
    "Model",
    "NoHuman",
    "ProgressCallback",
    "Question",
    "Resource",
    "ResourceOperation",
    "ScriptedModel",
    "Shell",
    "TerminalHuman",
    "TerminalProgress",
    "ToolCall",
    "Trace",
    "TraceEvent",
    "Usage",
    "agent",
    "run_agent",
]
