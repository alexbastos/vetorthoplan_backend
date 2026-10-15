#!/usr/bin/env bash
set -Eeuo pipefail

# Corrects the local API service and performs safe follow-up checks.
# It does not edit Apache virtual hosts, issue certificates, change firewall
# rules, or run database migrations automatically.

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_NAME="vetorthoplan-api"
SERVICE_USER="${SUDO_USER:-${USER}}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Uso:
  bash scripts/fix_ubuntu_environment.sh

Variáveis opcionais:
  API_HOST=127.0.0.1   endereço local recomendado para uso atrás de SSH/Apache
  API_PORT=8000        porta da API

O script corrige o serviço systemd da API, verifica Docker e valida health/OpenAPI.
Apache, certificados, firewall e migrations não são alterados automaticamente.
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
if [[ ! -x "$VENV_DIR/bin/uvicorn" ]]; then
  printf 'Uvicorn não encontrado em %s. Execute primeiro o script de instalação.\n' "$VENV_DIR" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  printf 'Usuário do serviço não encontrado: %s\n' "$SERVICE_USER" >&2
  exit 1
fi

printf 'Projeto: %s\n' "$PROJECT_DIR"
printf 'Usuário da API: %s\n' "$SERVICE_USER"
printf 'Endereço da API: %s:%s\n' "$API_HOST" "$API_PORT"

unit_file="$(mktemp -t vetorthoplan-api.XXXXXX)"
trap 'rm -f "$unit_file"' EXIT
cat >"$unit_file" <<EOF
[Unit]
Description=VetOrthoPlan API
After=network.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn vetorthoplan.bootstrap:create_app --factory --host $API_HOST --port $API_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

printf '\nInstalando unidade systemd corrigida...\n'
sudo install -o root -g root -m 0644 "$unit_file" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null
sudo systemctl restart "$SERVICE_NAME"

printf '\nEstado da API:\n'
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
  printf '[OK] serviço %s está ativo\n' "$SERVICE_NAME"
else
  printf '[FALHA] serviço %s não iniciou\n' "$SERVICE_NAME" >&2
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
  sudo journalctl -u "$SERVICE_NAME" --no-pager -n 40 || true
  exit 1
fi

if command -v curl >/dev/null 2>&1; then
  live_status="000"
  for attempt in {1..15}; do
    live_status="$(curl --silent --show-error --connect-timeout 2 --max-time 5 \
      --output /tmp/vetorthoplan-fix-live.$$ --write-out '%{http_code}' \
      "http://127.0.0.1:$API_PORT/health/live" || true)"
    [[ "$live_status" == 200 ]] && break
    sleep 1
  done
  if [[ "$live_status" == 200 ]]; then
    printf '[OK] health check respondeu HTTP 200\n'
    cat /tmp/vetorthoplan-fix-live.$$
    printf '\n'
  else
    printf '[FALHA] health check respondeu HTTP %s\n' "${live_status:-sem resposta}" >&2
    sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 40 || true
    exit 1
  fi
  rm -f /tmp/vetorthoplan-fix-live.$$
  openapi_status="$(curl --silent --show-error --connect-timeout 5 --max-time 10 \
    --output /dev/null --write-out '%{http_code}' \
    "http://127.0.0.1:$API_PORT/openapi.json" || true)"
  [[ "$openapi_status" == 200 ]] && printf '[OK] OpenAPI respondeu HTTP 200\n' || printf '[ATENÇÃO] OpenAPI respondeu HTTP %s\n' "${openapi_status:-sem resposta}"
fi

printf '\nDocker:\n'
if command -v docker >/dev/null 2>&1; then
  sudo systemctl enable docker >/dev/null 2>&1 || true
  sudo systemctl start docker >/dev/null 2>&1 || true
  if sudo docker info >/dev/null 2>&1; then
    printf '[OK] Docker acessível via sudo\n'
  else
    printf '[ATENÇÃO] Docker instalado, mas o daemon não está acessível\n'
    printf 'Verifique: sudo systemctl status docker\n'
  fi
else
  printf '[ATENÇÃO] Docker não instalado\n'
fi

printf '\nApache:\n'
if command -v apache2ctl >/dev/null 2>&1; then
  if sudo apache2ctl configtest; then
    printf '[OK] configuração do Apache válida\n'
  else
    printf '[ATENÇÃO] Apache possui erro de configuração; nenhum arquivo foi alterado\n'
    printf 'Revise certificados e VirtualHosts antes de recarregar o Apache.\n'
  fi
fi

printf '\nCorreção concluída. Swagger local: http://127.0.0.1:%s/docs\n' "$API_PORT"
printf 'Para SSH tunnel: ssh -N -L %s:127.0.0.1:%s %s@SERVIDOR\n' "$API_PORT" "$API_PORT" "$SERVICE_USER"
printf 'Migrations continuam manuais: %s/bin/alembic upgrade head\n' "$VENV_DIR"
