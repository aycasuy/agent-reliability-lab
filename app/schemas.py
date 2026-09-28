from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentRun:
    answer: dict[str, Any]
    tools_used: list[str]
    raw_text: str

