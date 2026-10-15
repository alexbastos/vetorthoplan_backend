#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only diagnostic. It does not restart services or change Apache/firewall.
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
API_URL="${API_URL:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-}"
SERVICE_NAME="${SERVICE_NAME:-vetorthoplan-api}"
OK=0; WARN=0; FAIL=0

pass() { printf '[OK]      %s\n' "$*"; OK=$((OK + 1)); }
warn_msg() { printf '[ATENÇÃO] %s\n' "$*"; WARN=$((WARN + 1)); }
fail_msg() { printf '[FALHA]   %s\n' "$*"; FAIL=$((FAIL + 1)); }
section() { printf '\n== %s ==\n' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }

TMP_DIR="$(mktemp -d -t vetorthoplan-diagnostic.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

http_status() {
  local url="$1"
  curl --silent --show-error --connect-timeout 5 --max-time 10 \
    --output "$TMP_DIR/body" --write-out '%{http_code}' "$url" 2>"$TMP_DIR/curl-error"
}

section 'Sistema operacional'
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  printf 'Sistema: %s\nHost: %s\nArquitetura: %s\n' "$PRETTY_NAME" "$(hostname)" "$(uname -m)"
  if [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]]; then
    pass 'Ubuntu 24.04 detectado'
  else
    warn_msg "Sistema diferente do Ubuntu 24.04: ${PRETTY_NAME:-desconhecido}"
  fi
else
  fail_msg '/etc/os-release não existe'
fi

section 'Ferramentas'
for tool in python3.12 curl systemctl ss docker apache2ctl; do
  if has "$tool"; then pass "$tool disponível"; else warn_msg "$tool não encontrado"; fi
done
has python3.12 && python3.12 --version

section 'Projeto e Python'
[[ -f "$PROJECT_DIR/pyproject.toml" ]] && pass 'pyproject.toml encontrado' || fail_msg 'pyproject.toml ausente'
if [[ -x "$VENV_DIR/bin/python" ]]; then
  pass "venv encontrado em $VENV_DIR"
  if "$VENV_DIR/bin/python" -c 'import alembic, asyncpg, boto3, fastapi, httpx, numpy, PIL, pydantic_settings, sqlalchemy, greenlet, pytest' >/dev/null 2>&1; then
    pass 'dependências Python importam corretamente'
  else
    fail_msg 'há dependências Python ausentes ou inválidas'
    "$VENV_DIR/bin/python" - <<'PY' || true
modules = ('alembic', 'asyncpg', 'boto3', 'fastapi', 'httpx', 'numpy', 'PIL', 'pydantic_settings', 'sqlalchemy', 'greenlet', 'pytest')
for module in modules:
    try:
        __import__(module)
        print(f'  [OK] {module}')
    except Exception as exc:
        print(f'  [FALHA] {module}: {exc}')
PY
  fi
else
  fail_msg "venv ausente em $VENV_DIR"
fi
[[ -f "$PROJECT_DIR/.env" ]] && pass '.env encontrado (valores ocultos)' || warn_msg '.env ausente'

section 'Docker e banco'
if has docker; then
  if docker info >/dev/null 2>&1; then
    pass 'Docker acessível pelo usuário atual'
    COMPOSE=(docker compose)
  elif sudo -n docker info >/dev/null 2>&1; then
    pass 'Docker acessível via sudo'
    COMPOSE=(sudo -n docker compose)
  else
    warn_msg 'daemon Docker não está acessível'
    COMPOSE=(docker compose)
  fi
  "${COMPOSE[@]}" version >/dev/null 2>&1 && pass 'Docker Compose disponível' || warn_msg 'Docker Compose indisponível'
  if "${COMPOSE[@]}" -f "$PROJECT_DIR/docker-compose.yml" ps --status running postgres 2>/dev/null | grep -q postgres; then
    pass 'PostgreSQL do compose está em execução'
  else
    warn_msg 'PostgreSQL do compose não está em execução ou não pôde ser consultado'
  fi
else
  warn_msg 'Docker não encontrado'
fi
if [[ -x "$VENV_DIR/bin/alembic" ]]; then
  if (cd "$PROJECT_DIR" && "$VENV_DIR/bin/alembic" current >"$TMP_DIR/alembic" 2>&1); then
    pass 'Alembic consultou o banco configurado'
  else
    warn_msg 'Alembic não conseguiu consultar o banco; revise DATABASE_URL e PostgreSQL'
    sed -n '1,8p' "$TMP_DIR/alembic" || true
  fi
fi

section 'Serviço e porta da API'
if has systemctl; then
  systemctl is-active --quiet "$SERVICE_NAME" && pass "$SERVICE_NAME está ativo" || { fail_msg "$SERVICE_NAME não está ativo"; systemctl status "$SERVICE_NAME" --no-pager -l 2>/dev/null | sed -n '1,12p' || true; }
  systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null && pass "$SERVICE_NAME inicia com o sistema" || warn_msg "$SERVICE_NAME não está habilitado no boot"
fi
if has ss; then
  if ss -ltn '( sport = :8000 )' | tail -n +2 | grep -q .; then
    pass 'há processo escutando na porta TCP 8000'
    ss -ltnp '( sport = :8000 )' 2>/dev/null || true
  else
    fail_msg 'nenhum processo escuta na porta TCP 8000'
  fi
fi

section 'API local'
if has curl; then
  status="$(http_status "$API_URL/health/live" || true)"
  if [[ "$status" == 200 ]]; then
    pass "health check HTTP 200 em $API_URL/health/live"
    printf 'Resposta: '; cat "$TMP_DIR/body"; printf '\n'
  else
    fail_msg "health check falhou em $API_URL/health/live (HTTP ${status:-sem resposta})"
    sed -n '1,3p' "$TMP_DIR/curl-error" || true
  fi
  status="$(http_status "$API_URL/openapi.json" || true)"
  [[ "$status" == 200 ]] && pass "OpenAPI HTTP 200 em $API_URL/openapi.json" || fail_msg "OpenAPI falhou em $API_URL/openapi.json (HTTP ${status:-sem resposta})"
else
  fail_msg 'curl não disponível'
fi

section 'Apache e acesso externo'
if has apache2ctl; then
  if apache2ctl configtest >"$TMP_DIR/apache" 2>&1; then pass 'configuração Apache válida'; else fail_msg 'configuração Apache inválida'; sed -n '1,12p' "$TMP_DIR/apache"; fi
  systemctl is-active --quiet apache2 2>/dev/null && pass 'Apache está ativo' || warn_msg 'Apache não está ativo'
fi
if [[ -n "$PUBLIC_URL" ]]; then
  status="$(http_status "$PUBLIC_URL/health/live" || true)"
  [[ "$status" == 200 ]] && pass "acesso externo HTTP 200 em $PUBLIC_URL/health/live" || warn_msg "acesso externo falhou em $PUBLIC_URL/health/live (HTTP ${status:-sem resposta}); teste a partir de outra rede"
else
  printf 'Acesso externo não testado. Use: PUBLIC_URL=https://seu-endereco bash %s\n' "$0"
fi

section 'Resumo'
printf 'OK: %d | Atenção: %d | Falhas: %d\n' "$OK" "$WARN" "$FAIL"
if ((FAIL > 0)); then printf 'Resultado: há falhas bloqueantes.\n'; exit 1; fi
if ((WARN > 0)); then printf 'Resultado: ambiente responde, mas há pontos para revisar.\n'; else printf 'Resultado: verificações concluídas sem problemas detectados.\n'; fi
