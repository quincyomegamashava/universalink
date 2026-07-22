from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DockerTool(BaseTool):
    name = "docker"
    description = (
        "Inspect Docker containers and images (read-only by default). "
        "Actions: ps, images, inspect. Requires DOCKER_HOST or unix socket."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["ps", "images", "inspect"]},
            "id": {"type": "string", "description": "Container or image id for inspect"},
        },
        "required": ["action"],
    }

    def _transport(self) -> tuple[str, httpx.AsyncBaseTransport | None]:
        settings = get_settings()
        host = settings.docker_host
        if not host:
            # Default Docker Engine unix socket
            return ("http://localhost", httpx.AsyncHTTPTransport(uds="/var/run/docker.sock"))
        parsed = urlparse(host)
        if parsed.scheme == "unix":
            path = parsed.path or "/var/run/docker.sock"
            return ("http://localhost", httpx.AsyncHTTPTransport(uds=path))
        return (host.rstrip("/"), None)

    async def _get(self, path: str) -> Any:
        base, transport = self._transport()
        kwargs: dict[str, Any] = {"base_url": base, "timeout": 15.0}
        if transport is not None:
            kwargs["transport"] = transport
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(path)
            resp.raise_for_status()
            return resp.json()

    async def run(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()
        if not settings.docker_read_only and kwargs.get("action") not in {"ps", "images", "inspect"}:
            return ToolResult(success=False, output="Only read-only Docker actions are enabled")

        action = (kwargs.get("action") or "ps").lower()
        try:
            if action == "ps":
                data = await self._get("/containers/json?all=true")
                lines = [
                    f"{c.get('Id', '')[:12]}  {c.get('Image')}  {c.get('State')}  {c.get('Names', [''])[0]}"
                    for c in data
                ]
                return ToolResult(success=True, output="\n".join(lines) or "(no containers)", data={"containers": data})

            if action == "images":
                data = await self._get("/images/json")
                lines = []
                for img in data:
                    tags = img.get("RepoTags") or ["<none>"]
                    lines.append(f"{img.get('Id', '')[:12]}  {tags[0]}  {img.get('Size')}")
                return ToolResult(success=True, output="\n".join(lines) or "(no images)", data={"images": data})

            if action == "inspect":
                cid = kwargs.get("id")
                if not cid:
                    return ToolResult(success=False, output="id is required for inspect")
                data = await self._get(f"/containers/{cid}/json")
                summary = {
                    "id": data.get("Id"),
                    "name": data.get("Name"),
                    "image": (data.get("Config") or {}).get("Image"),
                    "state": (data.get("State") or {}).get("Status"),
                }
                return ToolResult(success=True, output=str(summary), data=summary)

            return ToolResult(success=False, output=f"Unknown action: {action}")
        except httpx.ConnectError:
            return ToolResult(
                success=False,
                output="Cannot reach Docker. Mount /var/run/docker.sock or set DOCKER_HOST.",
            )
        except httpx.HTTPStatusError as exc:
            return ToolResult(success=False, output=f"Docker API error: {exc.response.status_code}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Docker tool failed: %s", exc)
            return ToolResult(success=False, output=f"Docker tool failed: {exc}")
