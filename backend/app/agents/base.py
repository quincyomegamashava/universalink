from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    name: str
    description: str
    # OpenAI / Ollama-compatible parameter schema for agent tool calling
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
