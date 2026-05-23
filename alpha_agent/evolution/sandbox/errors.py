"""Structured sandbox errors. The 5 kinds cover every way an LLM-authored
operator can fail; callers (validator in 3c, runtime dispatch in 3d) pattern
match on .kind, never parse strings."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SandboxErrorKind(str, Enum):
    TIMEOUT = "timeout"
    SYSCALL_BLOCKED = "syscall_blocked"
    EXCEPTION = "exception"
    SHAPE_MISMATCH = "shape_mismatch"
    SIGNATURE_MISMATCH = "signature_mismatch"


@dataclass(frozen=True)
class SandboxError:
    kind: SandboxErrorKind
    detail: str
    op_name: str
