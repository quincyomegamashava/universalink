from __future__ import annotations

from app.agents.base import BaseTool
from app.agents.tools.aws import AWSTool
from app.agents.tools.calendar import CalendarTool
from app.agents.tools.database import DatabaseTool
from app.agents.tools.docker import DockerTool
from app.agents.tools.email import EmailTool
from app.agents.tools.filesystem import FilesystemTool
from app.agents.tools.github import GitHubTool
from app.agents.tools.terminal import TerminalTool
from app.agents.tools.web_search import WebSearchTool

TOOL_INSTANCES: list[BaseTool] = [
    GitHubTool(),
    FilesystemTool(),
    DockerTool(),
    TerminalTool(),
    AWSTool(),
    EmailTool(),
    DatabaseTool(),
    WebSearchTool(),
    CalendarTool(),
]

TOOL_REGISTRY: dict[str, BaseTool] = {t.name: t for t in TOOL_INSTANCES}

__all__ = ["TOOL_INSTANCES", "TOOL_REGISTRY"]
