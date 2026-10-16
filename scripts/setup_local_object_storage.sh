#!/usr/bin/env bash
set -Eeuo pipefail

# Provision a persistent, localhost-only S3-compatible MinIO for development.
# This script intentionally leaves Apache, firewall rules, and DNS unchanged.

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
SERVICE_USER="${SUDO_USER:-${USER}}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Uso:
  bash scripts/setup_local_object_storage.sh

Prepara MinIO local em Docker, cria o bucket e um usuário de aplicação,
configura o .env para API/worker e reinicia os serviços systemd existentes.
Execute como usuário normal com sudo. O serviço fica limitado a 127.0.0.1.
EOF
  exit 0
fi

if [[ "$EUID" -eq 0 ]]; then
  printf 'Execute como usuário normal com sudo; não use sudo antes do script.\n' >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  printf 'sudo não está instalado.\n' >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf 'Docker Compose v2 não está disponível. Execute primeiro scripts/prepare_ubuntu_24_04.sh --install.\n' >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  printf 'Arquivo docker-compose.yml não encontrado em %s.\n' "$PROJECT_DIR" >&2
  exit 1
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  printf 'Usuário do serviço não encontrado: %s\n' "$SERVICE_USER" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf 'Criado .env a partir de .env.example.\n'
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); value=$0} END {print value}' "$ENV_FILE"
}

set_env_value() {
  local key="$1" value="$2" temporary
  temporary="$(mktemp "$PROJECT_DIR/.env.XXXXXX")"
  awk -v prefix="$key=" 'index($0, prefix) != 1 {print}' "$ENV_FILE" >"$temporary"
  printf '%s=%s\n' "$key" "$value" >>"$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$ENV_FILE"
}

random_hex() {
  openssl rand -hex "$1"
}

STORAGE_BUCKET="${STORAGE_BUCKET:-$(env_value STORAGE_BUCKET)}"
STORAGE_BUCKET="${STORAGE_BUCKET:-vetorthoplan-uploads-local}"
if [[ ! "$STORAGE_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
  printf 'Nome de bucket inválido: use letras minúsculas, números, ponto ou hífen.\n' >&2
  exit 1
fi

APP_ENV="$(env_value APP_ENV)"
if [[ "$APP_ENV" == "production" || "$APP_ENV" == "staging" ]]; then
  printf 'Recusando configurar storage de desenvolvimento com APP_ENV=%s.\n' "$APP_ENV" >&2
  exit 1
fi

MINIO_ROOT_USER="${MINIO_ROOT_USER:-$(env_value MINIO_ROOT_USER)}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio$(random_hex 6)}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-$(env_value MINIO_ROOT_PASSWORD)}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-$(random_hex 24)}"
AWS_ACCESS_KEY_ID="$(env_value AWS_ACCESS_KEY_ID)"
AWS_SECRET_ACCESS_KEY="$(env_value AWS_SECRET_ACCESS_KEY)"
if [[ ! "$AWS_ACCESS_KEY_ID" =~ ^vop[0-9a-f]{16}$ || -z "$AWS_SECRET_ACCESS_KEY" ]]; then
  AWS_ACCESS_KEY_ID="vop$(random_hex 8)"
  AWS_SECRET_ACCESS_KEY="$(random_hex 24)"
fi

set_env_value STORAGE_BUCKET "$STORAGE_BUCKET"
set_env_value STORAGE_REGION "us-east-1"
set_env_value STORAGE_ENDPOINT_URL "http://127.0.0.1:9000"
set_env_value MINIO_ROOT_USER "$MINIO_ROOT_USER"
set_env_value MINIO_ROOT_PASSWORD "$MINIO_ROOT_PASSWORD"
set_env_value AWS_ACCESS_KEY_ID "$AWS_ACCESS_KEY_ID"
set_env_value AWS_SECRET_ACCESS_KEY "$AWS_SECRET_ACCESS_KEY"
chmod 600 "$ENV_FILE"

compose() {
  if docker info >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" "$@"
  else
    sudo docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

printf 'Subindo MinIO em 127.0.0.1:9000 (dados persistentes no volume Docker)...\n'
compose up -d minio

ready=0
for _ in $(seq 1 30); do
  if curl --silent --fail --max-time 2 http://127.0.0.1:9000/minio/health/live >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  printf 'MinIO não ficou pronto. Logs recentes:\n' >&2
  compose logs --tail=50 minio >&2 || true
  exit 1
fi

printf 'Criando bucket e usuário de aplicação no MinIO local...\n'
compose --profile bootstrap run --rm minio-bootstrap

restart_if_installed() {
  local service="$1"
  if sudo systemctl cat "$service" >/dev/null 2>&1; then
    sudo systemctl restart "$service"
    if sudo systemctl is-active --quiet "$service"; then
      printf '[OK] serviço %s reiniciado\n' "$service"
    else
      printf '[FALHA] serviço %s não está ativo\n' "$service" >&2
      sudo systemctl status "$service" --no-pager -l || true
      exit 1
    fi
  else
    printf '[INFO] serviço %s não instalado; ignorado\n' "$service"
  fi
}

restart_if_installed vetorthoplan-api.service
restart_if_installed vetorthoplan-worker.service

printf '\nStorage local configurado.\n'
printf 'Bucket: %s\n' "$STORAGE_BUCKET"
printf 'Endpoint interno: http://127.0.0.1:9000\n'
printf 'Console MinIO local: http://127.0.0.1:9001\n'
printf 'As credenciais foram gravadas em %s com permissão 600; não foram exibidas.\n' "$ENV_FILE"
printf 'Próximo passo: execute scripts/smoke_image_ingestion.py no próprio servidor.\n'
