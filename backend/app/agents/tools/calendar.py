from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    name = "calendar"
    description = (
        "Create or list simple calendar events as ICS files in the agent workspace "
        "(no external calendar OAuth in this release)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "create"]},
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO-8601 start datetime"},
            "end": {"type": "string", "description": "ISO-8601 end datetime"},
            "description": {"type": "string"},
        },
        "required": ["action"],
    }

    def _calendar_dir(self) -> Path:
        root = Path(get_settings().agent_workspace_dir).resolve() / "calendar"
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def run(self, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "list").lower()
        cal_dir = self._calendar_dir()

        if action == "list":
            files = sorted(cal_dir.glob("*.ics"))
            names = [f.name for f in files]
            return ToolResult(
                success=True,
                output="\n".join(names) if names else "(no events)",
                data={"events": names},
            )

        if action == "create":
            title = (kwargs.get("title") or "").strip()
            start = (kwargs.get("start") or "").strip()
            end = (kwargs.get("end") or "").strip()
            description = kwargs.get("description") or ""
            if not title or not start or not end:
                return ToolResult(success=False, output="title, start, and end are required")

            def _fmt(iso: str) -> str:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

            try:
                dtstart = _fmt(start)
                dtend = _fmt(end)
            except ValueError as exc:
                return ToolResult(success=False, output=f"Invalid datetime: {exc}")

            uid = str(uuid.uuid4())
            now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            ics = "\r\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:-//AI Platform//EN",
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now}",
                    f"DTSTART:{dtstart}",
                    f"DTEND:{dtend}",
                    f"SUMMARY:{title}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                    "END:VCALENDAR",
                    "",
                ]
            )
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
            path = cal_dir / f"{now}_{safe_name}.ics"
            path.write_text(ics, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Created event ICS at calendar/{path.name}",
                data={"path": str(path), "uid": uid, "title": title},
            )

        return ToolResult(success=False, output=f"Unknown action: {action}")
