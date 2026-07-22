from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.base import BaseTool, ToolResult
from app.services.mail import send_email_sync

logger = logging.getLogger(__name__)


class EmailTool(BaseTool):
    name = "email"
    description = "Send transactional email via configured SMTP. Requires SMTP_HOST and SMTP_FROM."
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        to = kwargs.get("to")
        subject = kwargs.get("subject")
        body = kwargs.get("body")
        if not to or not subject or body is None:
            return ToolResult(success=False, output="to, subject, and body are required")
        try:
            await asyncio.to_thread(send_email_sync, str(to), str(subject), str(body))
            return ToolResult(success=True, output=f"Email sent to {to}", data={"to": to, "subject": subject})
        except RuntimeError as exc:
            return ToolResult(success=False, output=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email tool failed: %s", exc)
            return ToolResult(success=False, output=f"Email failed: {exc}")
