# Phase 7 — Agent tools

LangGraph ReAct agent loop under `backend/app/agents/` with live, permission-gated tools.

## Tools

| Tool | Behavior | Config |
|------|----------|--------|
| `filesystem` | list/read/write in sandbox | `AGENT_WORKSPACE_DIR` |
| `terminal` | allowlisted commands only | `AGENT_TERMINAL_ALLOWLIST` |
| `docker` | ps / images / inspect (read-only) | `DOCKER_HOST` or `/var/run/docker.sock` |
| `github` | repos / issues | `GITHUB_TOKEN` |
| `aws` | sts / describe / list (read-only) | IAM role or AWS env creds |
| `email` | SMTP send | `SMTP_*` |
| `database` | SELECT-only SQL | `AGENT_DB_URL` or platform DB |
| `web_search` | DuckDuckGo Instant Answer | none |
| `calendar` | ICS events in workspace | none |

Permissions per role: admin UI → **Agent Tools**, or `tool_permissions` table.

## Invoke a single tool

```bash
curl -X POST http://localhost/api/agents/tools/invoke \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"web_search","arguments":{"query":"ollama"}}'
```

## Run the LangGraph agent

```bash
curl -X POST http://localhost/api/agents/run \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"message":"List files in the workspace and summarize what you see"}'
```

Response includes `reply`, `tool_traces`, `iterations`, and `steps`.

Default max iterations: `AGENT_MAX_ITERATIONS` (8). Override with `"max_iterations": 4`.

## Notes

- Tools that lack credentials return `success: false` with an actionable message (not fake readiness).
- Admin Models page lists **local Ollama inventory** and syncs into `model_registry`; pull is optional under “Install additional model”.
- Mount Docker socket on the backend only if you enable the Docker tool in production.
