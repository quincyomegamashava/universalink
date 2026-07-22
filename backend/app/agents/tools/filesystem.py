from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = (
        "List, read, or write files inside the agent workspace sandbox. "
        "Actions: list, read, write. Paths are relative to the workspace."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "read", "write"]},
            "path": {"type": "string", "description": "Relative path within the sandbox"},
            "content": {"type": "string", "description": "Content for write action"},
        },
        "required": ["action"],
    }

    def _root(self) -> Path:
        root = Path(get_settings().agent_workspace_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _resolve(self, path: str | None) -> Path:
        root = self._root()
        rel = (path or ".").strip() or "."
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PermissionError(f"Path escapes sandbox: {path}") from exc
        return candidate

    async def run(self, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "list").lower()
        path = kwargs.get("path", ".")
        try:
            target = self._resolve(path)
        except PermissionError as exc:
            return ToolResult(success=False, output=str(exc))

        if action == "list":
            if not target.exists():
                return ToolResult(success=False, output=f"Path not found: {path}")
            if target.is_file():
                return ToolResult(success=True, output=str(target.name), data={"entries": [target.name]})
            entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
            return ToolResult(
                success=True,
                output="\n".join(entries) if entries else "(empty)",
                data={"entries": entries, "path": str(target.relative_to(self._root()))},
            )

        if action == "read":
            if not target.is_file():
                return ToolResult(success=False, output=f"Not a file: {path}")
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) > 100_000:
                text = text[:100_000] + "\n...[truncated]"
            return ToolResult(success=True, output=text, data={"path": path, "bytes": target.stat().st_size})

        if action == "write":
            content = kwargs.get("content")
            if content is None:
                return ToolResult(success=False, output="content is required for write")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            return ToolResult(success=True, output=f"Wrote {len(str(content))} bytes to {path}", data={"path": path})

        return ToolResult(success=False, output=f"Unknown action: {action}")
