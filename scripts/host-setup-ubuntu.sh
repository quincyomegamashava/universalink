#!/usr/bin/env bash
# Host setup for Ubuntu 24.04 EC2 (Docker + NVIDIA Container Toolkit).
# Run as root or with sudo: sudo bash scripts/host-setup-ubuntu.sh
set -euo pipefail

echo "==> Updating apt"
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git jq

echo "==> Installing Docker Engine + Compose plugin"
install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

echo "==> Adding current user to docker group (if SUDO_USER set)"
if [[ -n "${SUDO_USER:-}" ]]; then
  usermod -aG docker "$SUDO_USER" || true
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "==> NVIDIA driver detected; installing NVIDIA Container Toolkit"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -y
  apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
  echo "==> GPU check:"
  nvidia-smi || true
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi || true
else
  echo "==> No nvidia-smi found. Install NVIDIA drivers for g4dn/g5 before using compose.gpu.yml"
  echo "    Example: sudo ubuntu-drivers install --gpgpu && sudo reboot"
fi

echo "==> Host setup complete"
echo "Next:"
echo "  1. cp .env.example .env && edit secrets"
echo "  2. docker compose -f docker-compose.yml -f compose.gpu.yml up -d"
echo "  3. bash scripts/pull-models.sh"
