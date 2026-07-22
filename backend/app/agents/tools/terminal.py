from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_META_CHARS = set("&|;`$><\n")


class TerminalTool(BaseTool):
    name = "terminal"
    description = (
        "Run an allowlisted command in the agent workspace (no shell metacharacters). "
        "Provide argv as a string; first token must be on AGENT_TERMINAL_ALLOWLIST."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command line (allowlisted binary + args)"},
        },
        "required": ["command"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()
        raw = (kwargs.get("command") or "").strip()
        if not raw:
            return ToolResult(success=False, output="command is required")
        if any(c in _META_CHARS for c in raw):
            return ToolResult(success=False, output="Shell metacharacters are not allowed")

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            return ToolResult(success=False, output=f"Invalid command: {exc}")
        if not parts:
            return ToolResult(success=False, output="Empty command")

        binary = parts[0]
        allow = settings.terminal_allowlist
        if binary not in allow:
            return ToolResult(
                success=False,
                output=f"Command '{binary}' is not allowlisted. Allowed: {', '.join(sorted(allow))}",
            )

        cwd = settings.agent_workspace_dir
        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=settings.agent_terminal_timeout_sec
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(success=False, output=f"Command timed out after {settings.agent_terminal_timeout_sec}s")
        except FileNotFoundError:
            return ToolResult(success=False, output=f"Binary not found: {binary}")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run command: {exc}")

        out = (stdout or b"").decode("utf-8", errors="replace")
        err = (stderr or b"").decode("utf-8", errors="replace")
        combined = out
        if err:
            combined = (combined + "\n" + err).strip()
        if len(combined) > 50_000:
            combined = combined[:50_000] + "\n...[truncated]"
        ok = proc.returncode == 0
        return ToolResult(
            success=ok,
            output=combined or f"(exit {proc.returncode})",
            data={"exit_code": proc.returncode, "command": parts},
        )
