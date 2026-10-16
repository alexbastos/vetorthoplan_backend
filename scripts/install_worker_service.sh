#!/usr/bin/env bash
set -Eeuo pipefail

# Install and start the image-ingestion worker as a systemd service.
# Requires the project's venv, .env, and a reachable PostgreSQL database.

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_NAME="vetorthoplan-worker"
SERVICE_USER="${SUDO_USER:-${USER}}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf 'Uso: bash scripts/install_worker_service.sh\n'
  printf 'Instala e inicia o worker systemd para ingestão de imagens.\n'
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
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  printf 'Python do projeto não encontrado em %s.\n' "$VENV_DIR" >&2
  exit 1
fi
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  printf 'Arquivo .env não encontrado em %s. Configure o banco e o storage primeiro.\n' "$PROJECT_DIR" >&2
  exit 1
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  printf 'Usuário do serviço não encontrado: %s\n' "$SERVICE_USER" >&2
  exit 1
fi

printf 'Validando acesso ao banco com Alembic...\n'
if ! (cd "$PROJECT_DIR" && "$VENV_DIR/bin/alembic" current); then
  printf 'Não foi possível consultar o banco. Worker não foi instalado/iniciado.\n' >&2
  exit 1
fi

unit_file="$(mktemp -t vetorthoplan-worker.XXXXXX)"
trap 'rm -f "$unit_file"' EXIT
cat >"$unit_file" <<EOF
[Unit]
Description=VetOrthoPlan image ingestion worker
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/python -m vetorthoplan.worker
Restart=always
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

printf '\nInstalando unidade %s...\n' "$SERVICE_NAME"
sudo install -o root -g root -m 0644 "$unit_file" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  printf '[OK] %s está ativo e habilitado no boot.\n' "$SERVICE_NAME"
  printf 'Logs: sudo journalctl -u %s -f\n' "$SERVICE_NAME"
else
  printf '[FALHA] %s não iniciou. Logs recentes:\n' "$SERVICE_NAME" >&2
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
  sudo journalctl -u "$SERVICE_NAME" --no-pager -n 50 || true
  exit 1
fi

printf 'Referência visual do fluxo: docs/frontend/processamento-imagem-v1.png\n'
