"""Durable replay of successful workflow steps."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, local
from typing import Any, Protocol
from uuid import uuid4

from pydantic_core import to_jsonable_python

from pilota.errors import JournalError

_FORMAT_VERSION = 1
_active_lock = Lock()
_active_journal: Journal | None = None


class _JournalStore(Protocol):
    def load(self) -> list[_Record]: ...

    def append(self, record: _Record) -> None: ...

    def replace(self, records: list[_Record]) -> None: ...

    def archive(self) -> Path | None: ...


@dataclass(frozen=True)
class _Record:
    sequence: int
    parent: int | None
    kind: str
    fingerprint: str
    data: Mapping[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "version": _FORMAT_VERSION,
            "sequence": self.sequence,
            "parent": self.parent,
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "data": self.data,
        }

    @classmethod
    def from_json(cls, value: object) -> _Record:
        if not isinstance(value, Mapping):
            raise JournalError("Journal record must be a JSON object")
        if value.get("version") != _FORMAT_VERSION:
            raise JournalError(f"Unsupported journal version: {value.get('version')!r}")
        sequence = value.get("sequence")
        parent = value.get("parent")
        kind = value.get("kind")
        fingerprint = value.get("fingerprint")
        data = value.get("data")
        if not isinstance(sequence, int) or sequence < 0:
            raise JournalError("Journal record sequence must be a non-negative integer")
        if parent is not None and (not isinstance(parent, int) or parent < 0):
            raise JournalError("Journal record parent must be a non-negative integer or null")
        if not isinstance(kind, str) or not kind:
            raise JournalError("Journal record kind must be a non-empty string")
        if not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:"):
            raise JournalError("Journal record fingerprint must be a sha256 value")
        if not isinstance(data, Mapping):
            raise JournalError("Journal record data must be a JSON object")
        return cls(sequence, parent, kind, fingerprint, dict(data))


@dataclass(frozen=True)
class _JournalCall:
    """A single journal-aware operation."""

    sequence: int
    parent: int | None
    kind: str
    fingerprint: str
    generation: int
    replayed: Mapping[str, Any] | None = None
    replay_ended: bool = False


class _JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path / "journal.jsonl" if path.is_dir() else path

    def load(self) -> list[_Record]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise JournalError(f"Could not read journal {self.path}: {error}") from error

        records: list[_Record] = []
        incomplete_tail = False
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                if index == len(lines) - 1:
                    incomplete_tail = True
                    break
                raise JournalError(
                    f"Journal contains invalid JSON on line {index + 1}: {error}"
                ) from error
            records.append(_Record.from_json(value))

        records.sort(key=lambda record: record.sequence)
        sequences = [record.sequence for record in records]
        if len(sequences) != len(set(sequences)):
            raise JournalError("Journal contains duplicate sequence numbers")
        if incomplete_tail:
            self.replace(records)
        return records

    def append(self, record: _Record) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            record.to_json(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise JournalError(f"Could not append journal {self.path}: {error}") from error

    def replace(self, records: list[_Record]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                for record in sorted(records, key=lambda item: item.sequence):
                    json.dump(
                        record.to_json(),
                        stream,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise JournalError(f"Could not replace journal {self.path}: {error}") from error

    def archive(self) -> Path | None:
        if not self.path.exists():
            return None
        archive = self.path.with_name(f"{self.path.name}.archive-{uuid4().hex[:12]}")
        temporary = archive.with_name(f".{archive.name}.{uuid4().hex}.tmp")
        try:
            with self.path.open("rb") as source, temporary.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, archive)
        except OSError as error:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise JournalError(f"Could not archive journal {self.path}: {error}") from error
        return archive


class Journal:
    """Record successful operations and replay them on a later run.

    Only one journal may be active in a process. Successful agent calls and
    completed human answers are appended to a JSONL file. Failed operations
    leave no record and run again on the next invocation.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._store: _JournalStore = _JsonlStore(self.path)
        self._lock = Lock()
        self._local = local()
        self._records: list[_Record] = []
        self._cursor = 0
        self._sequence = 0
        self._generation = 0
        self._matched: list[_Record] = []
        self._completed: dict[int, _Record] = {}
        self._skipped_parents: set[int] = set()
        self._replayed_any = False
        self._reported_replay_end = False
        self._entered = False

    def __enter__(self) -> Journal:
        global _active_journal
        with _active_lock:
            if _active_journal is not None:
                raise JournalError("Only one Journal may be active in a process")
            _active_journal = self
        try:
            self._records = self._store.load()
        except Exception:
            with _active_lock:
                if _active_journal is self:
                    _active_journal = None
            raise
        self._cursor = 0
        self._sequence = 0
        self._generation = 0
        self._matched = []
        self._completed = {}
        self._skipped_parents = set()
        self._replayed_any = False
        self._reported_replay_end = False
        self._entered = True
        return self

    def __exit__(self, *args: object) -> None:
        global _active_journal
        with _active_lock:
            if _active_journal is self:
                _active_journal = None
        self._entered = False

    def begin(self, kind: str, fingerprint: str) -> _JournalCall:
        """Reserve an operation and return a saved result when it matches."""

        with self._lock:
            if not self._entered:
                raise JournalError("Journal operations require an active context")
            self._advance_skipped()
            sequence = self._sequence
            self._sequence += 1
            parent = self._parent_sequence()

            replayed: Mapping[str, Any] | None = None
            replay_ended = False
            if self._cursor < len(self._records):
                record = self._records[self._cursor]
                if record.sequence == sequence:
                    if (
                        record.parent == parent
                        and record.kind == kind
                        and record.fingerprint == fingerprint
                    ):
                        self._cursor += 1
                        self._matched.append(record)
                        self._replayed_any = True
                        replayed = record.data
                        if kind == "agent":
                            self._skipped_parents.add(sequence)
                    else:
                        self._diverge()
                        replay_ended = self._mark_replay_ended()
                elif record.sequence < sequence:
                    self._diverge()
                    replay_ended = self._mark_replay_ended()
                else:
                    replay_ended = self._mark_replay_ended()
            elif self._replayed_any:
                replay_ended = self._mark_replay_ended()

            return _JournalCall(
                sequence=sequence,
                parent=parent,
                kind=kind,
                fingerprint=fingerprint,
                generation=self._generation,
                replayed=replayed,
                replay_ended=replay_ended,
            )

    def complete(self, call: _JournalCall, data: Mapping[str, Any]) -> None:
        """Persist a fully successful operation."""

        with self._lock:
            if call.replayed is not None or call.generation != self._generation:
                return
            record = _Record(
                sequence=call.sequence,
                parent=call.parent,
                kind=call.kind,
                fingerprint=call.fingerprint,
                data=dict(to_jsonable_python(data)),
            )
            self._store.append(record)
            self._completed[record.sequence] = record

    def operation(self, call: _JournalCall) -> _Operation:
        """Track nested journal operations below a parent call."""

        return _Operation(self, call.sequence)

    def _parent_sequence(self) -> int | None:
        stack = getattr(self._local, "parents", ())
        return stack[-1] if stack else None

    def _push_parent(self, sequence: int) -> None:
        stack = getattr(self._local, "parents", ())
        self._local.parents = (*stack, sequence)

    def _pop_parent(self, sequence: int) -> None:
        stack = getattr(self._local, "parents", ())
        if not stack or stack[-1] != sequence:
            raise JournalError("Journal operation scopes exited out of order")
        self._local.parents = stack[:-1]

    def _advance_skipped(self) -> None:
        while self._cursor < len(self._records):
            record = self._records[self._cursor]
            if record.parent not in self._skipped_parents:
                return
            self._cursor += 1
            self._skipped_parents.add(record.sequence)
            self._sequence = max(self._sequence, record.sequence + 1)

    def _diverge(self) -> None:
        retained = {
            record.sequence: record for record in (*self._matched, *self._completed.values())
        }
        self._store.archive()
        self._store.replace(list(retained.values()))
        self._records = []
        self._cursor = 0
        self._matched = list(sorted(retained.values(), key=lambda record: record.sequence))
        self._completed = dict(retained)
        self._skipped_parents = set()
        self._generation += 1

    def _mark_replay_ended(self) -> bool:
        if not self._replayed_any or self._reported_replay_end:
            return False
        self._reported_replay_end = True
        return True


class _Operation:
    def __init__(self, journal: Journal, sequence: int) -> None:
        self._journal = journal
        self._sequence = sequence

    def __enter__(self) -> None:
        self._journal._push_parent(self._sequence)

    def __exit__(self, *args: object) -> None:
        self._journal._pop_parent(self._sequence)


def active_journal() -> Journal | None:
    """Return the process-wide active journal, if any."""

    return _active_journal


def fingerprint(value: Mapping[str, Any]) -> str:
    """Create a stable fingerprint from JSON-compatible call inputs."""

    try:
        normalized = to_jsonable_python(value)
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as error:
        raise JournalError(f"Journal fingerprint input is not serializable: {error}") from error
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


__all__ = ["Journal"]
