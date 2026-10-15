#!/usr/bin/env bash
set -Eeuo pipefail

# Audit or prepare the VetOrthoPlan backend host. This script does not modify
# Apache virtual hosts, firewall rules, DNS, TLS certificates, or application secrets.

MODE="${1:---check}"
case "$MODE" in
  --check|--install) ;;
  *)
    printf 'Uso: %s [--check|--install]\n' "$0" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

if [[ ! -r /etc/os-release ]]; then
  printf 'Não foi possível identificar a distribuição: /etc/os-release ausente.\n' >&2
  exit 1
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
  printf 'Sistema detectado: %s %s. Este script é destinado ao Ubuntu 24.04 LTS.\n' \
    "${NAME:-desconhecido}" "${VERSION_ID:-desconhecida}" >&2
  exit 1
fi

REQUIRED_PACKAGES=(
  ca-certificates
  curl
  git
  build-essential
  libpq-dev
  python3.12
  python3.12-dev
  python3.12-venv
)

package_installed() {
  dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null | grep -qx installed
}

missing_packages=()
printf 'Sistema: %s (%s)\n' "$PRETTY_NAME" "$(uname -m)"
printf '\nPacotes do sistema:\n'
for package in "${REQUIRED_PACKAGES[@]}"; do
  if package_installed "$package"; then
    printf '  [OK]       %s\n' "$package"
  else
    printf '  [A instalar] %s\n' "$package"
    missing_packages+=("$package")
  fi
done

# Respect an existing Docker CE installation. Install Ubuntu's packaged engine
# only when no Docker engine package or CLI is present.
if ! package_installed docker.io && ! package_installed docker-ce && ! package_installed moby-engine \
  && ! command -v docker >/dev/null 2>&1; then
  printf '  [A instalar] docker.io (engine e cliente)\n'
  missing_packages+=(docker.io)
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  if ! package_installed docker-compose-v2; then
    printf '  [A instalar] docker-compose-v2 (plugin Compose)\n'
    missing_packages+=(docker-compose-v2)
  fi
fi

printf '\nServiços e ferramentas encontrados:\n'
for service in apache2 docker; do
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$service"; then
    printf '  [ativo]    %s\n' "$service"
  elif command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet "$service" 2>/dev/null; then
    printf '  [parado]   %s (habilitado no boot)\n' "$service"
  else
    printf '  [não ativo] %s\n' "$service"
  fi
done

if command -v apache2ctl >/dev/null 2>&1; then
  modules="$(apache2ctl -M 2>/dev/null || true)"
  for module in proxy_module proxy_http_module; do
    if grep -q "$module" <<<"$modules"; then
      printf '  [Apache]   módulo %s habilitado\n' "$module"
    else
      printf '  [Apache]   módulo %s não habilitado\n' "$module"
    fi
  done
else
  printf '  [Apache]   apache2ctl não encontrado\n'
fi

if command -v python3.12 >/dev/null 2>&1; then
  printf '  [Python]   %s\n' "$(python3.12 --version 2>&1)"
else
  printf '  [Python]   Python 3.12 não encontrado\n'
fi
if command -v docker >/dev/null 2>&1; then
  printf '  [Docker]   %s\n' "$(docker --version 2>&1)"
  if docker compose version >/dev/null 2>&1; then
    printf '  [Compose]  %s\n' "$(docker compose version --short 2>&1 || true)"
  else
    printf '  [Compose]  plugin não disponível para o usuário atual\n'
  fi
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
  if "$VENV_DIR/bin/python" -c 'import alembic, asyncpg, boto3, fastapi, httpx, numpy, PIL, pydantic_settings, sqlalchemy, pytest' >/dev/null 2>&1; then
    printf '  [Venv]     dependências backend e de teste instaladas em %s\n' "$VENV_DIR"
  else
    printf '  [Venv]     existe, mas faltam dependências do backend ou de teste\n'
  fi
else
  printf '  [Venv]     ambiente virtual não encontrado em %s\n' "$VENV_DIR"
fi

if [[ -f "$PROJECT_DIR/.env" ]]; then
  printf '  [.env]     arquivo existe (conteúdo não exibido)\n'
else
  printf '  [.env]     ausente; configure DATABASE_URL e STORAGE_* antes de executar a API\n'
fi

if [[ "$MODE" == --check ]]; then
  if ((${#missing_packages[@]})); then
    printf '\nAuditoria concluída. Execute %s --install para instalar pacotes ausentes e dependências Python.\n' "$0"
  else
    printf '\nAuditoria concluída: pacotes do sistema já instalados.\n'
  fi
  printf 'O Apache e seus virtual hosts não foram alterados.\n'
  exit 0
fi

if [[ "$EUID" -eq 0 ]]; then
  printf '\nExecute como usuário normal com sudo, para que o ambiente .venv não fique pertencendo ao root.\n' >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  printf '\nO modo de instalação requer sudo para instalar pacotes do sistema.\n' >&2
  exit 1
fi

if ((${#missing_packages[@]})); then
  printf '\nInstalando pacotes ausentes com apt...\n'
  sudo apt-get update
  sudo apt-get install -y "${missing_packages[@]}"
fi

if ! systemctl is-enabled --quiet docker 2>/dev/null; then
  printf '\nHabilitando o serviço Docker no boot...\n'
  sudo systemctl enable docker
fi
if ! systemctl is-active --quiet docker; then
  printf 'Iniciando o serviço Docker...\n'
  sudo systemctl start docker
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  printf '\nCriando ambiente virtual Python em %s...\n' "$VENV_DIR"
  python3.12 -m venv "$VENV_DIR"
fi
printf 'Instalando dependências declaradas pelo projeto...\n'
"$VENV_DIR/bin/python" -m pip install --upgrade pip
(cd "$PROJECT_DIR" && "$VENV_DIR/bin/python" -m pip install -e '.[dev]')

printf '\nPreparação concluída. Próximos passos sugeridos:\n'
printf '  1. Configure o arquivo %s/.env sem expor segredos.\n' "$PROJECT_DIR"
printf '  2. Suba o PostgreSQL do projeto: cd %q && sudo docker compose up -d postgres\n' "$PROJECT_DIR"
printf '  3. Aplique o schema: cd %q && .venv/bin/alembic upgrade head\n' "$PROJECT_DIR"
printf '  4. Rode os testes: cd %q && .venv/bin/pytest\n' "$PROJECT_DIR"
printf '  5. Rode API e worker como processos separados, limitados a 127.0.0.1 até configurar o proxy.\n'
printf '\nNenhuma configuração do Apache, firewall, DNS ou certificado foi alterada.\n'
