from __future__ import annotations

import logging
from typing import Any

import httpx

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GitHubTool(BaseTool):
    name = "github"
    description = (
        "Interact with GitHub. Actions: status, list_repos, list_issues, get_repo. "
        "Requires GITHUB_TOKEN."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "list_repos", "list_issues", "get_repo"],
            },
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
        },
        "required": ["action"],
    }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        settings = get_settings()
        token = settings.github_token
        if not token:
            raise RuntimeError("GITHUB_TOKEN is not configured")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-platform-agent",
        }
        async with httpx.AsyncClient(base_url="https://api.github.com", timeout=30.0, headers=headers) as client:
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    async def run(self, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "status").lower()
        try:
            if action == "status":
                user = await self._request("GET", "/user")
                return ToolResult(
                    success=True,
                    output=f"Authenticated as {user.get('login')}",
                    data={"login": user.get("login"), "id": user.get("id")},
                )

            if action == "list_repos":
                repos = await self._request("GET", "/user/repos", params={"per_page": 20, "sort": "updated"})
                lines = [f"{r.get('full_name')}  {r.get('private') and 'private' or 'public'}" for r in repos]
                return ToolResult(success=True, output="\n".join(lines) or "(none)", data={"repos": lines})

            if action == "get_repo":
                owner, repo = kwargs.get("owner"), kwargs.get("repo")
                if not owner or not repo:
                    return ToolResult(success=False, output="owner and repo are required")
                data = await self._request("GET", f"/repos/{owner}/{repo}")
                summary = {
                    "full_name": data.get("full_name"),
                    "description": data.get("description"),
                    "stars": data.get("stargazers_count"),
                    "default_branch": data.get("default_branch"),
                    "html_url": data.get("html_url"),
                }
                return ToolResult(success=True, output=str(summary), data=summary)

            if action == "list_issues":
                owner, repo = kwargs.get("owner"), kwargs.get("repo")
                if not owner or not repo:
                    return ToolResult(success=False, output="owner and repo are required")
                state = kwargs.get("state") or "open"
                issues = await self._request(
                    "GET",
                    f"/repos/{owner}/{repo}/issues",
                    params={"state": state, "per_page": 20},
                )
                lines = [f"#{i.get('number')} {i.get('title')}" for i in issues if "pull_request" not in i]
                return ToolResult(success=True, output="\n".join(lines) or "(no issues)", data={"issues": lines})

            return ToolResult(success=False, output=f"Unknown action: {action}")
        except RuntimeError as exc:
            return ToolResult(success=False, output=str(exc))
        except httpx.HTTPStatusError as exc:
            return ToolResult(success=False, output=f"GitHub API error: {exc.response.status_code} {exc.response.text[:300]}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub tool failed: %s", exc)
            return ToolResult(success=False, output=f"GitHub tool failed: {exc}")
