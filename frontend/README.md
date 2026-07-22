# Frontend note

End-user chat UI: **Open WebUI** (Docker service), gated by **platform SSO**.

Users sign in at `/login` (or `/register`). NGINX injects trusted identity
headers into Open WebUI — there is no separate chat password.

Admin Console: **FastAPI + Jinja2** templates in
[`backend/app/templates/admin/`](../backend/app/templates/admin/)
and static CSS in [`backend/app/static/admin.css`](../backend/app/static/admin.css).

**CSS source of truth:** `backend/app/static/admin.css` only.
The orphaned React app under `frontend/admin/` is **not shipped** in compose —
do not maintain `frontend/admin/src/styles.css` as a second theme.

Portal login/register templates:
[`backend/app/templates/portal/`](../backend/app/templates/portal/).

See [docs/auth-sso.md](../docs/auth-sso.md).

| URL | Who |
|-----|-----|
| `/login` · `/register` | Everyone |
| `/settings/api-keys` | Logged-in users (Cursor / Continue keys) |
| `/` | Chat (after SSO) |
| `/admin/` | Platform admins |
| `/admin/models` | Warm / pull / delete Ollama models |
