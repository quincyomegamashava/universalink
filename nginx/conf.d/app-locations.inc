# Shared location blocks — included by HTTP and HTTPS server blocks.

location /nginx-health {
    access_log off;
    return 200 'ok';
    add_header Content-Type text/plain;
}

# NGINX auth_request subrequest (not client-accessible)
location = /auth/verify {
    internal;
    proxy_pass http://backend_api/auth/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Shared portal (login / register / logout / password reset / home) — no auth_request
location ~ ^/(login|register|logout|forgot-password|reset-password|home)$ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Cookie $http_cookie;
}

# User settings (API keys, password) — platform session cookie
location /settings {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Cookie $http_cookie;
}

# --- FastAPI platform routes ---

location /api/auth/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/api-keys {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/admin/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/chats/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/rag/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/agents/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
}

location /api/docs {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /api/redoc {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /api/openapi.json {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /v1/ {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
}

location /health {
    proxy_pass http://backend_api/health;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}

location /metrics {
    proxy_pass http://backend_api/metrics;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}

# Jinja Admin Console (served by FastAPI; uses platform session cookie)
location /admin {
    proxy_pass http://backend_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Cookie $http_cookie;
}

# Open WebUI — only after platform SSO (never trust client X-User-* headers)
location / {
    auth_request /auth/verify;
    auth_request_set $user_email $upstream_http_x_user_email;
    auth_request_set $user_name $upstream_http_x_user_name;
    auth_request_set $user_role $upstream_http_x_user_role;

    error_page 401 = @portal_login;

    proxy_pass http://open_webui;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-User-Email $user_email;
    proxy_set_header X-User-Name $user_name;
    proxy_set_header X-User-Role $user_role;
    # Strip any client-supplied identity headers (defense in depth)
    proxy_set_header X-Forwarded-User "";
    proxy_buffering off;
    proxy_cache off;
}

location @portal_login {
    return 302 /login?next=$request_uri;
}
