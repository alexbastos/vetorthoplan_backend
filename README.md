# VetOrthoPlan Backend

Backend clínico do VetOrthoPlan, com os vertical slices de casos, upload e processamento inicial de radiografias.

## Stack

- Python 3.12+
- FastAPI e Swagger/OpenAPI
- SQLAlchemy assíncrono
- PostgreSQL
- Alembic
- pytest

O projeto não usa Prisma porque a arquitetura aprovada é Python. O schema do PostgreSQL é definido por modelos SQLAlchemy e migrations Alembic, que podem ser criados e revisados sem acesso a um banco remoto.

## Desenvolvimento local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
uvicorn vetorthoplan.bootstrap:create_app --factory --reload
```

Documentação da API:

- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- ReDoc: <http://localhost:8000/redoc>

Os arquivos locais `openapi/openapi.json` e `docs/openapi.json` representam o código desta branch (`0.9.0`). O servidor `cecia.ufsj.edu.br` ainda publica `0.8.0`; as mudanças locais não foram implantadas.

Referências de produto e frontend:

- [Plano arquitetural TPLO](docs/PLANO_ARQUITETURAL_TPLO.md)
- [Guia visual do fluxo frontend TPLO](docs/GUIA_FRONTEND_FLUXO_TPLO.md)
- [Contrato frontend — criar caso](docs/FRONTEND_CRIAR_CASO_ENDPOINT.md)
- [Contrato frontend — listar e consultar casos](docs/FRONTEND_LISTAR_CONSULTAR_CASOS.md)
- [Contrato frontend — criar sessão de upload](docs/FRONTEND_CRIAR_SESSAO_UPLOAD.md)
- [Contrato frontend — confirmar upload](docs/FRONTEND_CONFIRMAR_UPLOAD.md)
- [Contrato frontend — processamento e consulta de imagens](docs/FRONTEND_PROCESSAMENTO_IMAGENS.md)
- [Prancha visual em PNG](docs/frontend/fluxo-frontend-tplo-v2.png)
- [Prancha de criação de caso](docs/frontend/criar-caso-v1.png)
- [Prancha de lista e detalhe de casos](docs/frontend/casos-listagem-detalhe-v2.png)
- [Prancha de upload de radiografia](docs/frontend/upload-radiografia-v1.png)
- [Prancha de confirmação do upload](docs/frontend/confirmacao-upload-v1.png)
- [Prancha de processamento da imagem](docs/frontend/processamento-imagem-v1.png)
- [Índice visual dos endpoints e funcionalidades](docs/REFERENCIAS_VISUAIS_ENDPOINTS.md)
- [Contrato de criação de caso 0.9.0](docs/CONTRATO_CRIACAO_CASO_0.9.0.md)
- [Contrato de autenticação clínica — pendente](docs/CONTRATO_AUTENTICACAO_CLINICA.md)

## PostgreSQL local opcional

Não é necessário ter PostgreSQL para executar os testes unitários e HTTP iniciais. Quando for necessário validar persistência e migrations:

```bash
docker compose up -d postgres
alembic upgrade head
```

## Preparar servidor Ubuntu 24.04

O script abaixo primeiro audita o servidor sem fazer alterações. Para instalar os pacotes ausentes e preparar `.venv` com as dependências do backend e de teste:

```bash
bash scripts/prepare_ubuntu_24_04.sh --check
bash scripts/prepare_ubuntu_24_04.sh --install
```

Execute `--install` como usuário normal com `sudo`. O script instala Docker/Compose quando necessário, dependências do Python e bibliotecas de build/cliente PostgreSQL, e não altera o Apache, seus virtual hosts, firewall, DNS ou certificados. Depois da instalação, configure `.env`, suba o PostgreSQL e aplique as migrations conforme as instruções exibidas pelo script.

Após atualizar uma instalação existente, execute `alembic upgrade head` antes de iniciar a nova versão da API. A mudança de contrato é incompatível para criação de caso: `sex` agora é obrigatório e não nulo; `UNKNOWN` continua aceito explicitamente. Casos já armazenados podem manter `sex = null` e continuam legíveis.

No servidor `cecia.ufsj.edu.br`, a API continua vinculada a `127.0.0.1:8000`; o Apache encaminha `/api/`, `/docs` e `/openapi.json` pelo VirtualHost HTTPS existente, sem adicionar um prompt de autenticação Basic. O `DocumentRoot` da página principal e o Alias `/wiki` permanecem inalterados.

Para diagnosticar o servidor sem alterar serviços ou configurações:

```bash
bash scripts/diagnose_ubuntu_environment.sh
```

Para testar também um endereço externo, informe a URL sem exibir credenciais:

```bash
PUBLIC_URL=http://200.19.137.16:8000 bash scripts/diagnose_ubuntu_environment.sh
```

O diagnóstico verifica o sistema, ferramentas, `.venv`, imports Python, Docker/PostgreSQL, migrations, serviço systemd, porta 8000, health check, OpenAPI e configuração do Apache. `/health/live` testa somente o processo; `/health/ready` executa `SELECT 1` no PostgreSQL e responde 503 se o banco não estiver acessível.

Para corrigir o serviço da API após uma configuração incorreta:

```bash
bash scripts/fix_ubuntu_environment.sh
```

Esse script instala uma unidade `systemd` sem `--root-path`, reinicia a API e valida health/OpenAPI. Ele não modifica VirtualHosts, certificados, firewall nem executa migrations automaticamente.

Para executar o worker de ingestão continuamente como serviço `systemd`, depois que `.env`, PostgreSQL e storage estiverem configurados:

```bash
bash scripts/install_worker_service.sh
sudo systemctl status vetorthoplan-worker --no-pager -l
sudo journalctl -u vetorthoplan-worker -f
```

### Storage local para desenvolvimento

O fluxo de upload usa a API S3. Em um servidor sem AWS, prepare um RustFS S3 local persistido em volume Docker:

```bash
FRONTEND_ORIGIN=https://frontend.example.com bash scripts/setup_local_object_storage.sh
```

O script configura bucket privado, credenciais aleatórias locais no `.env` (permissão `600`), sobe o RustFS e reinicia API/worker se as unidades systemd existirem. Com `FRONTEND_ORIGIN`, configura CORS somente para essa origem. O serviço S3 fica limitado a `127.0.0.1:9000`. Os arquivos sobrevivem a reinícios do container no volume `vetorthoplan_rustfs_data`. O script não altera Apache, firewall nem DNS e recusa `APP_ENV=staging` ou `production`.

`STORAGE_ENDPOINT_URL` é o endpoint interno usado pela API e pelo worker. `STORAGE_PUBLIC_ENDPOINT_URL` define o endpoint público incluído nas URLs pré-assinadas. No servidor atual, use `STORAGE_ENDPOINT_URL=http://127.0.0.1:9000` e `STORAGE_PUBLIC_ENDPOINT_URL=https://cecia.ufsj.edu.br`; o Apache encaminha o caminho do bucket sem alterá-lo, e o mesmo host HTTPS serve a página principal. O cliente deve usar a URL assinada sem reescrever caminho, campos ou assinatura. Como a página e o storage usam a mesma origem, o upload direto não depende de túnel SSH nem de CORS entre origens.

Para excluir sessões expiradas/canceladas e objetos enviados tardiamente, agende `.venv/bin/python scripts/cleanup_expired_uploads.py` no diretório do projeto, por exemplo a cada 15 minutos. O comando aguarda 15 minutos adicionais após `expires_at` para não remover um POST que já esteja em andamento.

O túnel SSH descrito abaixo é apenas uma opção para desenvolvimento local. No servidor, as portas 8000 e 9000 continuam restritas ao loopback; o Apache fornece HTTPS direto para a API e para o POST S3 pré-assinado.

Para validar o fluxo real de uma imagem até `READY` e conferir que a prévia pode ser baixada e decodificada:

```bash
cd /home/capcode/Documentos/projetos/vetorthoplan_backend
API_BASE_URL=http://127.0.0.1:8000 .venv/bin/python scripts/smoke_image_ingestion.py
```

Execute com a API, PostgreSQL, bucket S3 compatível e worker ativos. O script envia um PNG sintético, aguarda o job e verifica o estado `READY`, o tipo e as dimensões da prévia. Ele salva a prévia baixada em `/tmp/vetorthoplan-smoke-preview-<id>.png` para inspeção visual; `SMOKE_PREVIEW_OUTPUT` permite escolher outro caminho. O teste cria um caso e uma imagem persistentes; não usa nem grava dados clínicos reais. Configure `SMOKE_TIMEOUT_SECONDS` para alterar o limite de espera (padrão: 120 segundos).

Se `/openapi.json` responder e as rotas de casos retornarem 500, confira logs (`sudo journalctl -u vetorthoplan-api -n 200 --no-pager`), estado do banco (`sudo systemctl status postgresql --no-pager` ou `docker compose ps postgres`), `DATABASE_URL` sem publicá-la, e `alembic current`/`alembic heads` no ambiente do serviço. Aplique `alembic upgrade head` somente após confirmar que a URL aponta ao banco correto. `/health/ready` separa indisponibilidade do banco de falha do processo; os logs da exceção são necessários para identificar a causa SQL.

As pranchas de referência por funcionalidade estão indexadas em [REFERENCIAS_VISUAIS_ENDPOINTS.md](docs/REFERENCIAS_VISUAIS_ENDPOINTS.md).

## Contexto de identidade temporário

Enquanto o contrato AUTH-01 não for fechado com os demais projetos, o ambiente `local`/`test` usa IDs fixos configurados por `LOCAL_TENANT_ID` e `LOCAL_ACTOR_ID`. Esses valores não chegam pelo payload da API.

`IDENTITY_MODE=local` é rejeitado em `staging` e `production`. O adapter JWT será implementado posteriormente sem alterar o caso de uso de criação de casos.

## Endpoints de casos

- `POST /api/v1/cases` cria um caso clínico no estado `DRAFT`;
- `GET /api/v1/cases` lista casos com busca, filtro e cursor;
- `GET /api/v1/cases/{case_id}` consulta um caso do tenant ativo.

## Endpoint de upload

- `POST /api/v1/cases/{case_id}/image-uploads` cria uma sessão `PENDING_UPLOAD` e devolve um formulário `POST` pré-assinado para envio direto ao object storage.
- A criação da sessão exige `Idempotency-Key`; repetir a chave e os mesmos metadados recupera a mesma sessão após falha de rede.
- `DELETE /api/v1/image-uploads/{upload_id}` cancela uma sessão pendente e libera a cota ativa; a URL não pode ser revogada e a limpeza remove qualquer envio tardio após a expiração.
- `POST /api/v1/image-uploads/{upload_id}/complete` confere o objeto armazenado, promove a sessão para `QUARANTINED` e agenda de forma idempotente um job durável de ingestão.
- `GET /api/v1/jobs/{job_id}` consulta o andamento da ingestão;
- `GET /api/v1/images/{image_id}/job` recupera o job após recarregar a página (job nulo antes da confirmação);
- `POST /api/v1/jobs/{job_id}/retry` reenfileira uma falha operacional `FAILED`, reutilizando o mesmo upload;
- `GET /api/v1/cases/{case_id}/images` lista as imagens e seus estados;
- `GET /api/v1/images/{image_id}` consulta uma imagem.
- `DELETE /api/v1/images/{image_id}` exclui original, prévia, plano e registro do job; retorna 409 durante `QUEUED` ou `PROCESSING`;
- `GET /api/v1/images/{image_id}/preview` emite acesso temporário à prévia PNG;
- `GET/PUT /api/v1/images/{image_id}/plan` consulta e salva o documento geométrico versionado.

O contrato aceita DICOM, PNG e JPEG de até 100 MiB e exige o SHA-256 hexadecimal calculado antes do envio. O worker confere novamente o checksum, decodifica PNG/JPEG e DICOM monocromático não comprimido single-frame, mantém uma allowlist sem identificadores do paciente, expõe espaçamento/orientação DICOM disponíveis e gera uma prévia PNG privada. Transfer syntaxes comprimidas e DICOM multiframe são recusados explicitamente neste recorte. Consulte os guias de [criação](docs/FRONTEND_CRIAR_SESSAO_UPLOAD.md), [confirmação](docs/FRONTEND_CONFIRMAR_UPLOAD.md) e [processamento](docs/FRONTEND_PROCESSAMENTO_IMAGENS.md).

Executar um job e encerrar:

```bash
python -m vetorthoplan.worker --once
```

Executar continuamente:

```bash
python -m vetorthoplan.worker
```

Configuração do adapter S3:

```bash
export STORAGE_BUCKET=vetorthoplan-uploads-local
export STORAGE_REGION=us-east-1
# Opcional para storage compatível com S3:
export STORAGE_ENDPOINT_URL=http://127.0.0.1:9000
```

As credenciais seguem a cadeia padrão do SDK AWS. O bucket privado e seu CORS devem ser provisionados separadamente; a API não cria infraestrutura na inicialização.

Consulte o Swagger para os contratos completos.

## Testes e qualidade

```bash
pytest
ruff check .
```

## Migrations

As migrations versionadas estão em `migrations/versions/`, incluindo casos (`20260915_0001`), sessões (`20260917_0002`), confirmação (`20260917_0003`), fila durável (`20260917_0004`), estados de processamento (`20260918_0005`), prévias (`20260918_0006`), planos geométricos (`20260918_0007`), idempotência de casos (`20261016_0008`), origem da idade (`20261019_0009`), falha operacional da imagem (`20261019_0010`), idempotência de sessões (`20261019_0011`) e cancelamento (`20261019_0012`). Aplique-as com `alembic upgrade head` no banco configurado.
