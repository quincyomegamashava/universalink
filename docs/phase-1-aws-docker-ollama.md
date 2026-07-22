# Phase 1 — AWS + Docker + Ollama + Open WebUI + NGINX

## Goal

Stand up a private, GPU-capable AI chat server. Ollama never faces the internet; NGINX fronts Open WebUI.

## GPU verification

After starting with `compose.gpu.yml`, confirm the GPU is visible **inside** Ollama:

```bash
docker compose exec ollama nvidia-smi -L
REQUIRE_GPU=1 bash scripts/check-models.sh
bash scripts/warmup-models.sh
```

If `nvidia-smi` is missing in the container, you are on CPU — chat will feel slow. Fix drivers / NVIDIA Container Toolkit, then recreate:

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d
```

See [performance.md](performance.md) for CPU vs GPU expectations.

```
ai-platform/
  docker-compose.yml
  compose.gpu.yml
  .env.example
  nginx/
    nginx.conf
    conf.d/default.conf
  scripts/
    host-setup-ubuntu.sh
    pull-models.sh
    smoke-phase1.sh
  docs/
    phase-1-aws-docker-ollama.md
  certs/          # empty; for TLS later
```

## AWS prerequisites

1. Launch **Ubuntu 24.04** on `g4dn.xlarge` (16GB VRAM) or `g5.xlarge`.
2. Security group inbound:
   - TCP 22 from your IP only
   - TCP 80 from your IP (or 0.0.0.0/0 if intentional)
   - TCP 443 (same)
   - **Do not open 11434**
3. Attach an IAM role only if you need later AWS tools (Phase 7); not required for Phase 1.
4. Root volume ≥ 100GB (models are large).

## Host setup

```bash
sudo bash scripts/host-setup-ubuntu.sh
# reboot if drivers were just installed
nvidia-smi   # must show GPU
```

## Start the stack

```bash
cd ai-platform
cp .env.example .env
# edit WEBUI_SECRET_KEY at minimum

# GPU production
docker compose -f docker-compose.yml -f compose.gpu.yml up -d

# CPU smoke test only (slow)
# docker compose up -d
```

## Pull models

```bash
bash scripts/pull-models.sh
# or specific:
bash scripts/pull-models.sh llama3.2:3b mistral:7b
```

### VRAM guidance (approximate, quantized)

| VRAM | Comfortable models |
|------|--------------------|
| 8GB  | 3B–7B Q4 |
| 16GB (g4dn.xlarge) | 7B–14B Q4/Q5 |
| 24GB+ | 32B Q4 or multiple small models |

Suggested catalog names (Ollama library): `llama3.2`, `llama3.1`, `mistral`, `gemma2`, `qwen2.5`, `deepseek-r1` (check size before pull).

## Expected output

```bash
docker compose ps
# ollama, open-webui, nginx — healthy / running

curl http://127.0.0.1/nginx-health
# ok

# Browser: http://<public-ip>/  → Open WebUI
```

## Security check

```bash
bash scripts/smoke-phase1.sh
```

From your laptop, `curl http://<public-ip>:11434` must fail (connection refused / timed out).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `nvidia-smi` missing | Install drivers: `ubuntu-drivers install --gpgpu`, reboot |
| Ollama unhealthy / no GPU | Use `compose.gpu.yml`; confirm NVIDIA Container Toolkit |
| Open WebUI 502 | Wait for healthy ollama; `docker compose logs open-webui` |
| OOM when loading model | Pull a smaller tag (e.g. `:3b` / `:7b`) |
| Models lost after restart | Ensure `ollama_data` volume exists (`docker volume ls`) |

## Exit criteria

- [x] Chat via NGINX → Open WebUI → Ollama
- [x] ≥2 models pullable and switchable
- [x] Port 11434 not public
- [x] Volumes persist across `down` / `up`

When confirmed, proceed to Phase 2 (FastAPI auth).
