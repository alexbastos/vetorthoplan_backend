#!/usr/bin/env bash
set -Eeuo pipefail

# Atualiza uma instalação existente do VetOrthoPlan no servidor.
# Não altera Apache, VirtualHosts, certificados, DNS ou a página principal.

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${VETORTHOPLAN_BRANCH:-master}"
VENV_DIR="$PROJECT_DIR/.venv"
API_SERVICE="vetorthoplan-api"
WORKER_SERVICE="vetorthoplan-worker"

die() { printf '[ERRO] %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }

show_api_failure() {
  printf '\n[DIAGNÓSTICO] Estado da API:\n'
  sudo systemctl status "$API_SERVICE" --no-pager -l || true
  printf '\n[DIAGNÓSTICO] Logs recentes da API:\n'
  sudo journalctl -u "$API_SERVICE" -n 80 --no-pager || true
}

if [[ "$EUID" -eq 0 ]]; then
  die 'Execute como usuário normal; o script usa sudo quando necessário.'
fi
command -v git >/dev/null || die 'Git não encontrado.'
command -v sudo >/dev/null || die 'sudo não encontrado.'
[[ -d "$PROJECT_DIR/.git" ]] || die "Repositório não encontrado em $PROJECT_DIR"
[[ -f "$PROJECT_DIR/.env" ]] || die "Arquivo .env não encontrado em $PROJECT_DIR"
[[ -x "$VENV_DIR/bin/python" ]] || die "Ambiente Python não encontrado em $VENV_DIR"

cd "$PROJECT_DIR"

info 'Validando branch e alterações locais'
current_branch="$(git branch --show-current)"
[[ "$current_branch" == "$BRANCH" ]] || die "Branch atual é '$current_branch'; esperado '$BRANCH'."
if [[ -n "$(git status --porcelain)" ]]; then
  die 'Há alterações locais. Faça backup/commit ou limpe o working tree antes de atualizar.'
fi

info 'Baixando e aplicando a versão do GitHub'
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

info 'Atualizando dependências Python'
"$VENV_DIR/bin/pip" install -e .

info 'Subindo PostgreSQL e storage'
if command -v docker >/dev/null 2>&1; then
  sudo docker compose up -d postgres rustfs
else
  printf '[ATENÇÃO] Docker não encontrado; mantendo os serviços externos existentes.\n'
fi

info 'Aplicando migrations'
"$VENV_DIR/bin/alembic" upgrade head

info 'Reiniciando API'
sudo systemctl restart "$API_SERVICE"
api_started=0
for _attempt in {1..20}; do
  if sudo systemctl is-active --quiet "$API_SERVICE"; then
    api_started=1
    break
  fi
  sleep 1
done
if [[ "$api_started" -ne 1 ]]; then
  show_api_failure
  die "Serviço $API_SERVICE não iniciou."
fi

info 'Reiniciando worker'
if sudo systemctl cat "$WORKER_SERVICE" >/dev/null 2>&1; then
  sudo systemctl restart "$WORKER_SERVICE"
  sudo systemctl is-active --quiet "$WORKER_SERVICE" || {
    sudo systemctl status "$WORKER_SERVICE" --no-pager -l || true
    die "Serviço $WORKER_SERVICE não iniciou."
  }
else
  printf '[ATENÇÃO] Serviço %s não está instalado; worker não foi reiniciado.\n' "$WORKER_SERVICE"
fi

info 'Validando health checks locais'
live_status=000
ready_status=000
for _attempt in {1..20}; do
  live_status="$(curl --silent --show-error --connect-timeout 2 --max-time 5 \
    --output /dev/null --write-out '%{http_code}' \
    http://127.0.0.1:8000/health/live || true)"
  [[ "$live_status" == 200 ]] && break
  sleep 1
done
if [[ "$live_status" != 200 ]]; then
  show_api_failure
  die "health/live respondeu HTTP ${live_status:-sem resposta}."
fi
ready_status="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
  --output /dev/null --write-out '%{http_code}' \
  http://127.0.0.1:8000/health/ready || true)"
[[ "$live_status" == 200 ]] || die "health/live respondeu HTTP ${live_status:-sem resposta}."
[[ "$ready_status" == 200 ]] || die "health/ready respondeu HTTP ${ready_status:-sem resposta}."

printf '\n[OK] VetOrthoPlan atualizado com sucesso.\n'
printf 'Commit ativo: %s\n' "$(git rev-parse --short HEAD)"
printf 'Swagger local: http://127.0.0.1:8000/docs\n'
printf 'Swagger público: https://cecia.ufsj.edu.br/docs\n'
