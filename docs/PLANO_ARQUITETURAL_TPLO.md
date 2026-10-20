# Plano arquitetural do VetOrthoPlan — MVP TPLO

> Status: em implementação incremental; check-in atualizado em 2026-09-18
> Data: 2026-09-18
> Escopo: planejamento e acompanhamento dos vertical slices implementados
> Repositórios envolvidos: `vetorthoplan_backend`, `vetorthoplan_frontend` e `authentication_api`

## 1. Resumo executivo

O VetOrthoPlan será uma aplicação web de planejamento ortopédico veterinário inspirada nas capacidades públicas do VPOP PRO, sem copiar marca, interface, textos, algoritmos proprietários ou ativos de terceiros. O primeiro recorte clínico será o planejamento de TPLO em radiografias 2D.

O produto será iniciado como um microserviço clínico independente, chamado neste documento de `vetorthoplan_backend`, integrado ao provedor de identidade existente (`authentication_api`) e consumido exclusivamente pelo BFF do `vetorthoplan_frontend`. Internamente, o backend será um monólito modular em Python organizado segundo Clean Architecture. A separação futura em outros serviços só deverá ocorrer por necessidade comprovada de escala, disponibilidade ou ownership.

A decisão arquitetural mais importante é representar o planejamento como dados geométricos vetoriais versionados, e não como sucessivas imagens rasterizadas. A radiografia original permanece imutável; calibrações, medições, fragmentos, osteotomias, implantes e anotações formam um documento de planejamento reproduzível. PNG e PDF são derivados de exportação.

O MVP deverá entregar um fluxo TPLO completo para piloto controlado:

1. autenticar e selecionar a organização/clínica;
2. criar um caso;
3. importar DICOM, PNG ou JPEG;
4. validar e calibrar a radiografia;
5. medir eixos, linhas, círculos e ângulos;
6. simular osteotomia e rotação do fragmento;
7. posicionar implantes de um catálogo inicialmente restrito;
8. salvar revisões automaticamente;
9. finalizar o plano;
10. gerar imagem e relatório PDF rastreáveis.

## Check-ins de implementação

Este registro acompanha o que foi realmente desenvolvido neste repositório. Um item marcado como parcial não autoriza antecipar a implementação das etapas seguintes no frontend. O registro deve ser atualizado a cada novo vertical slice, mantendo a data, o estado e a evidência técnica.

| Data | Entrega | Estado | Evidência |
|---|---|---|---|
| 2026-09-15 | Scaffold Python/FastAPI com Clean Architecture | Concluído | `pyproject.toml`, `src/vetorthoplan/` |
| 2026-09-15 | Domínio e caso de uso de criação de caso | Concluído | `domain/cases`, `application/use_cases/create_case.py` |
| 2026-09-15 | `POST /api/v1/cases` no estado inicial `DRAFT` | Concluído | `api/routes/cases.py` |
| 2026-09-15 | `GET /api/v1/cases` com busca, status e cursor | Concluído | `application/use_cases/list_cases.py`, `api/routes/cases.py` |
| 2026-09-15 | `GET /api/v1/cases/{case_id}` tenant-scoped | Concluído | `application/use_cases/get_case.py`, erro padronizado `CASE_NOT_FOUND` |
| 2026-09-15 | Modelo PostgreSQL e migration Alembic inicial | Concluído; não aplicado | `infrastructure/database`, `migrations/versions/20260915_0001_create_clinical_cases.py` |
| 2026-09-15 | Swagger, ReDoc e OpenAPI `0.2.0` exportado | Concluído | `/docs`, `/redoc`, `openapi/openapi.json` |
| 2026-09-15 | Health check de processo | Parcial | `GET /health/live`; `/health/ready` ainda pendente |
| 2026-09-15 | Identidade/tenant temporários para local e testes | Restrito a `local`, `development` e `test` | `IDENTITY_MODE=local`; UUIDs configurados não vêm do cliente |
| 2026-09-15 | Testes unitários, HTTP, configuração e arquitetura | Concluído | `tests/` — 24 testes aprovados |
| 2026-10-20 | JWT/JWKS e isolamento tenant-scoped com `authentication_api` | Implementado em código; pendente aplicar migration e configurar ambientes | Branch `vet_auth_01`; contrato e migration `20261020_0013` |
| 2026-09-17 | Domínio e caso de uso de criação de sessão de upload | Concluído | `domain/imaging`, `application/use_cases/create_image_upload.py` |
| 2026-09-17 | `POST /api/v1/cases/{case_id}/image-uploads` tenant-scoped | Concluído | valida DICOM/PNG/JPEG, 100 MiB, SHA-256 e limite de sessões |
| 2026-09-17 | Formulário S3 pré-assinado e registro em quarentena | Concluído; infraestrutura não provisionada | `infrastructure/storage.py`, migration `20260917_0002` |
| 2026-09-17 | Swagger, ReDoc e OpenAPI `0.3.0` exportado | Concluído | `/docs`, `/redoc`, `openapi/openapi.json` |
| 2026-09-17 | Testes após o slice de upload | Concluído | `tests/` — 37 testes aprovados; `ruff check .` aprovado |
| 2026-09-17 | `POST /api/v1/image-uploads/{upload_id}/complete` tenant-scoped e idempotente | Concluído | confere objeto privado e promove para `QUARANTINED` |
| 2026-09-17 | Migration de confirmação e estado `QUARANTINED` | Concluído; não aplicada | `migrations/versions/20260917_0003_confirm_image_uploads.py` |
| 2026-09-17 | Swagger, ReDoc e OpenAPI `0.4.0` exportado | Concluído | `/docs`, `/redoc`, `openapi/openapi.json` |
| 2026-09-17 | Testes após confirmação de upload | Concluído | `tests/` — 52 testes aprovados; `ruff check .` aprovado |
| 2026-09-17 | Publicação idempotente do job de ingestão | Concluído | fila PostgreSQL durável, migration `20260917_0004`, OpenAPI `0.5.0` |
| 2026-09-17 | Testes após agendamento da ingestão | Concluído | `tests/` — 54 testes aprovados; `ruff check .` aprovado |
| 2026-09-18 | Worker idempotente de ingestão inicial | Concluído; infraestrutura não provisionada | claim PostgreSQL, `QUEUED → PROCESSING → SUCCEEDED/REJECTED/FAILED` |
| 2026-09-18 | Inspeção de conteúdo PNG/JPEG/DICOM Part 10 | Parcial | checksum real, magic bytes e dimensões PNG/JPEG; parsing DICOM pendente |
| 2026-09-18 | Consulta de jobs e imagens | Concluído | `GET /jobs/{id}`, `GET /cases/{id}/images`, `GET /images/{id}` |
| 2026-09-18 | Swagger, ReDoc e OpenAPI `0.6.0` exportado | Concluído | contratos IMG-02 sincronizados |
| 2026-09-18 | Testes após primeiro recorte IMG-02 | Concluído | `tests/` — 63 testes aprovados; `ruff check .` aprovado |
| 2026-09-18 | Prévias PNG/JPEG e DICOM não comprimido | Concluído no primeiro recorte | allowlist, preview PNG privado e `GET /images/{id}/preview`; migration `0006` |
| 2026-09-18 | Viewer, calibração, medições e simulação TPLO | Concluído no primeiro recorte funcional | BFF, polling, zoom/pan, geometria vetorial e planos versionados; migration `0007` |
| 2026-09-18 | OpenAPI `0.7.0` e cliente frontend sincronizados | Concluído | contratos de preview e planejamento publicados |

**Recorte atual:** casos, upload direto, worker, prévias, viewer e o primeiro documento geométrico TPLO estão implementados. O viewer oferece zoom, pan, calibração, linhas, ângulos, círculos e rotação TPLO com persistência otimista. DICOM comprimido/multiframe, fragmentos, implantes, finalização e relatório continuam pendentes.

### Checklist do slice IMG-01

- [x] validar nome, extensão, tipo, tamanho e SHA-256 declarado;
- [x] autorizar o caso no tenant ativo sem expor existência entre tenants;
- [x] persistir sessão `PENDING_UPLOAD` e chave segregada em `quarantine/`;
- [x] limitar sessões não expiradas por caso;
- [x] emitir formulário S3 POST com chave, tipo, checksum, tamanho exato e expiração;
- [x] versionar migrations, OpenAPI `0.4.0`, README e contratos frontend;
- [x] gerar pranchas PNG de criação e confirmação para desenvolvimento frontend;
- [x] cobrir domínio, caso de uso, HTTP, tenant e assinatura S3 com testes;
- [x] confirmar upload e conferir tamanho, tipo, checksum, sessão e temporalidade no storage;
- [x] promover a sessão confirmada para `QUARANTINED` de forma idempotente;
- [x] publicar job idempotente de ingestão em fila durável no PostgreSQL;
- [x] fazer content sniffing inicial e conferir novamente o SHA-256;
- [x] listar imagens e consultar o estado do job;
- [x] fazer parsing DICOM inicial, metadata allowlist e derivados;
- [x] publicar acesso temporário ao conteúdo aprovado.

### Checklist do primeiro recorte IMG-02

- [x] reservar atomicamente o job mais antigo com `FOR UPDATE SKIP LOCKED`;
- [x] registrar tentativas e estados terminais do job;
- [x] validar magic bytes de PNG, JPEG e DICOM Part 10;
- [x] extrair dimensões de PNG e JPEG;
- [x] rejeitar checksum ou formato divergente com código seguro;
- [x] expor consultas tenant-scoped de job, lista e detalhe de imagem;
- [x] versionar migration `20260918_0005` e OpenAPI `0.6.0`;
- [x] atualizar contratos e pranchas para o frontend;
- [x] extrair tags DICOM em allowlist e validar transfer syntax;
- [x] gerar thumbnail/derivados e URL temporária de leitura;
- [ ] implementar retry/backoff e recuperação de jobs interrompidos.

## 2. Fontes, premissas e leitura dos projetos atuais

### 2.1 Fontes consideradas

Este plano usa como entradas:

- o documento `GUIA_NOVOS_MICROSSERVICOS.md`, tratado como restrição arquitetural;
- o estado atual de `authentication_api`;
- o estado atual de `vetorthoplan_frontend`;
- as capacidades públicas documentadas pelo VPOP PRO;
- a intenção de validar posteriormente o produto de referência usando uma conta do solicitante e um caso sanitizado.

Referências públicas do produto de referência:

- Quick Start Guide: <https://support.vpop-pro.com/portal/en/kb/articles/quick-start-guide>
- Formatos aceitos: <https://support.vpop-pro.com/portal/en/kb/articles/what-files-can-i-add-in-vpop>
- Calibração: <https://support.vpop-pro.com/portal/en/kb/articles/how-to-calibrate-images>
- Reposicionamento de fragmentos: <https://support.vpop-pro.com/portal/en/kb/articles/how-to-use-the-reposition-tool>
- Uso de implantes: <https://support.vpop-pro.com/portal/en/kb/articles/how-to-use-implants-in-vpop-pro>
- Tutoriais clínicos: <https://support.vpop-pro.com/portal/en/kb/vpop-pro/tutorials>
- Compartilhamento e referência: <https://support.vpop-pro.com/portal/en/kb/articles/referral>
- Integração PACS: <https://support.vpop-pro.com/portal/en/kb/articles/pacs-integration>

### 2.2 Estado do `vetorthoplan_backend`

Na revisão inicial, o repositório continha apenas a estrutura Git e a pasta `docs`. Desde então, foram implementados o scaffold FastAPI, o domínio de casos, criação, listagem e consulta de casos, criação de sessão de upload direto, modelos/migrations PostgreSQL, Swagger/OpenAPI, health check de processo e testes. O estado corrente e as limitações desses slices estão registrados em [Check-ins de implementação](#check-ins-de-implementação).

### 2.3 Estado do `vetorthoplan_frontend`

O frontend já oferece uma base relevante:

- monorepo com pnpm e Turborepo;
- Next.js, React e TypeScript;
- BFF por Route Handlers;
- sessão com access e refresh tokens em cookies `HttpOnly`, cifrados no servidor;
- validação de origem nas mutações;
- renovação de sessão centralizada;
- cliente TypeScript gerado a partir de OpenAPI;
- React Query e Zod;
- área autenticada e shell da aplicação;
- testes da superfície de autenticação.

Há, entretanto, dívida de origem a resolver antes das features clínicas:

- o package raiz ainda se chama `capta`;
- o cliente é publicado internamente como `@capta/api-client`;
- variáveis como `CAPTAGOV_APP_ORIGIN` permanecem no código;
- a documentação ainda descreve CaptaGov;
- somente o contrato da `authentication_api` está integrado ao cliente gerado.

Essa limpeza não bloqueia a documentação, mas deverá fazer parte da fundação do produto. O viewer clínico deverá ser adicionado como feature do frontend existente, não como uma segunda aplicação concorrente.

### 2.4 Estado da `authentication_api`

Foram confirmadas as seguintes capacidades:

- JWT assinado com RS256;
- endpoint JWKS;
- validação de `iss`, `aud`, `exp`, `iat`, `jti` e algoritmo;
- access token curto e refresh token com rotação;
- sessões, MFA, organizações e RBAC;
- OAuth 2.0/OIDC com Authorization Code e PKCE;
- cadastro de client applications e scopes;
- webhooks, incluindo nomes de eventos organizacionais;
- Clean Architecture em TypeScript/Fastify.

Também foram encontradas lacunas que precisam ser resolvidas antes da integração clínica:

1. o access token do login comum usa, por padrão, audiência `authentication-api`;
2. tokens OAuth podem usar o `client_id` como audiência, mas o contrato precisa ser formalizado para o resource server VetOrthoPlan;
3. o token atual não possui `tenant_id`;
4. `permissions` e `scopes` são opcionais e não aparecem no login comum;
5. existem tipos de webhook `ORG_CREATED`, `ORG_MEMBER_ADDED` e `ORG_MEMBER_REMOVED`, mas a emissão efetiva por todos os casos de uso organizacionais precisa ser confirmada;
6. o `kid` observado é fixo (`auth-key-1`); o procedimento real de rotação de chaves precisa ser acordado e testado;
7. documentação e rotas observadas possuem diferenças de prefixo; o contrato publicado pelo ambiente deverá ser a fonte de verdade.

Nenhum endpoint clínico deverá ser publicado antes do fechamento do gate de autenticação descrito na seção 10.

## 3. Objetivos e não objetivos

### 3.1 Objetivos do MVP

- Disponibilizar planejamento TPLO 2D confiável e reproduzível.
- Funcionar em navegadores modernos de desktop e tablet.
- Integrar-se à autenticação e às organizações existentes.
- Isolar rigorosamente os dados por tenant.
- Preservar o DICOM original e seus derivados rastreáveis.
- Permitir calibração manual e medições em milímetros e graus.
- Permitir seleção, rotação e translação de fragmentos ósseos.
- Permitir posicionamento de implantes vetoriais licenciados.
- Manter autosave, histórico de revisões, auditoria e exportação.
- Entregar OpenAPI versionado e cliente frontend gerado.
- Ser observável, implantável e recuperável desde a primeira release de homologação.

### 3.2 Não objetivos do MVP

- Paridade total com o VPOP PRO.
- Planejamento 3D ou importação de estudos completos de CT.
- Diagnóstico automático ou recomendação clínica por IA.
- Execução autônoma de decisões cirúrgicas.
- Biblioteca de milhares de implantes.
- Aplicativos nativos para Windows, macOS, Android ou iOS.
- Operação offline.
- Chat, referrals entre organizações ou compartilhamento público.
- Cobrança e assinatura.
- PACS/DICOMweb bidirecional.
- Tela dividida com múltiplos viewports.
- TTA, CBLO, CCWO ou outras técnicas além de TPLO.

## 4. Princípios arquiteturais

1. **Dependências apontam para dentro.** Domínio não importa framework, banco, fila, HTTP ou storage.
2. **Um serviço clínico com módulos claros.** Evitar microserviços internos antes de existir necessidade operacional.
3. **Identidade não é domínio clínico.** A `authentication_api` autentica; o VetOrthoPlan aplica autorização e regras de recurso.
4. **BFF como fronteira do navegador.** O browser não recebe access ou refresh token.
5. **Tenant obrigatório.** Toda entidade clínica pertence a exatamente um tenant, salvo catálogo público explicitamente global.
6. **Originais imutáveis.** Arquivos médicos nunca são sobrescritos.
7. **Plano é dado, renderização é derivado.** O documento geométrico é a fonte de verdade.
8. **Precisão é requisito funcional.** Transformações, calibração e arredondamento são testados como regras de domínio.
9. **Contratos antes de integração.** OpenAPI e eventos são versionados.
10. **Assíncrono para trabalho pesado.** Conversão, thumbnails, sanitização e relatórios não bloqueiam requests HTTP.
11. **Idempotência por padrão.** Upload, criação, finalização e jobs devem tolerar retry.
12. **Segurança e observabilidade desde o primeiro commit.** Não serão fases de acabamento.
13. **Evolução compatível.** Documentos de plano possuem `schema_version` e migradores explícitos.

## 5. Arquitetura de contexto

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Navegador                                                            │
│ UI React/Next + Cornerstone3D + ferramentas TPLO                     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ mesma origem
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ vetorthoplan_frontend / BFF                                          │
│ sessão HttpOnly, CSRF/origin, token, cliente tipado, normalização    │
└───────────────┬───────────────────────────────────┬──────────────────┘
                │                                   │
                │ HTTPS via API Gateway             │ autenticação/sessão
                ▼                                   ▼
┌───────────────────────────────┐      ┌───────────────────────────────┐
│ vetorthoplan_backend privado  │      │ authentication_api            │
│ casos, imagens, planos, TPLO, │      │ identidade, organizações,     │
│ implantes, relatórios, audit  │      │ OAuth/OIDC, JWT/JWKS, MFA     │
└───────┬──────────┬────────────┘      └───────────────────────────────┘
        │          │
        ▼          ▼
┌─────────────┐  ┌────────────────────┐       ┌───────────────────────┐
│ PostgreSQL  │  │ Object storage     │       │ Fila + workers        │
│ serviço     │  │ privado/KMS        │◀─────▶│ ingestão/exportação   │
└─────────────┘  └────────────────────┘       └───────────────────────┘
```

### 5.1 Exceção controlada para upload binário

Passar arquivos DICOM grandes pelo processo Next.js e pelo backend simultaneamente aumenta custo, latência e risco de timeout. O fluxo recomendado é:

1. navegador solicita uma sessão de upload ao BFF;
2. BFF autentica e solicita a sessão ao backend;
3. backend cria um registro `ImageUpload` e uma URL pré-assinada de curta duração;
4. navegador envia o arquivo diretamente para um prefixo de quarentena no object storage;
5. navegador confirma a conclusão pelo BFF;
6. backend valida checksum e agenda a ingestão;
7. somente arquivos aprovados são promovidos para o storage clínico.

A URL deverá limitar chave, método, tamanho, tipo declarado, checksum e tempo de validade. O bucket permanece privado. Essa é uma exceção para transporte de binários, não uma exposição direta do microserviço.

## 6. Estilo do backend e Clean Architecture

### 6.1 Stack proposta

- Python com versão fixada e suportada pelo time.
- FastAPI como adapter HTTP e gerador do contrato OpenAPI.
- Pydantic para contratos de entrada/configuração.
- SQLAlchemy e Alembic para PostgreSQL.
- `pyproject.toml` e lockfile reproduzível.
- Ruff para lint/format.
- mypy ou pyright para type checking; escolher um e torná-lo obrigatório.
- pytest, testes assíncronos e property-based tests para geometria.
- pydicom e codecs explicitamente homologados para ingestão DICOM.
- OpenTelemetry para traces, métricas e correlação.
- SDK de object storage compatível com S3.
- fila gerenciada em produção; adapter local para desenvolvimento.

As bibliotecas concretas de fila, PDF e renderização serão escolhidas em ADR durante o spike, atrás de ports da aplicação.

### 6.2 Estrutura lógica proposta

```text
vetorthoplan_backend/
├── docs/
│   ├── adr/
│   ├── runbooks/
│   └── PLANO_ARQUITETURAL_TPLO.md
├── openapi/
│   └── openapi.yaml
├── src/
│   └── vetorthoplan/
│       ├── domain/
│       │   ├── cases/
│       │   ├── imaging/
│       │   ├── planning/
│       │   ├── implants/
│       │   ├── reports/
│       │   └── shared/
│       ├── application/
│       │   ├── commands/
│       │   ├── queries/
│       │   ├── dto/
│       │   └── ports/
│       ├── api/
│       │   ├── routes/
│       │   ├── schemas/
│       │   ├── dependencies/
│       │   └── error_handlers/
│       ├── infrastructure/
│       │   ├── auth/
│       │   ├── database/
│       │   ├── storage/
│       │   ├── messaging/
│       │   ├── imaging/
│       │   ├── reports/
│       │   └── observability/
│       ├── config/
│       └── bootstrap.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── architecture/
│   ├── security/
│   └── fixtures/
├── migrations/
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 6.3 Regras de dependência

- `domain` depende apenas da biblioteca padrão e de código do próprio domínio.
- `application` depende de `domain` e define ports para persistência, storage, relógio, IDs, fila e auditoria.
- `api` transforma HTTP em commands/queries e não contém regra clínica.
- `infrastructure` implementa os ports e nunca é importada pelo domínio.
- `config/bootstrap` monta as dependências.
- modelos ORM não são entidades de domínio.
- schemas HTTP não atravessam a camada de aplicação.
- testes automatizados devem falhar quando as regras de importação forem violadas.

## 7. Módulos e limites de responsabilidade

### 7.1 Cases

Responsável por:

- dados mínimos do caso e do animal;
- status e arquivamento;
- relação entre caso, imagens, planos e relatórios;
- validação de acesso ao recurso pelo tenant;
- listagem, busca e paginação.

Não será responsável por identidade, senha, associação à organização ou cobrança.

### 7.2 Imaging

Responsável por:

- sessão de upload;
- checksum e content sniffing;
- validação de DICOM/PNG/JPEG;
- extração controlada de metadados;
- orientação, dimensões e pixel spacing informativo;
- geração de thumbnails e derivados;
- acesso temporário a conteúdo;
- política de quarentena e rejeição.

### 7.3 Planning

Responsável por:

- documento geométrico do plano;
- calibração;
- medições e anotações;
- transformação de fragmentos;
- regras de revisão, autosave, concorrência e finalização;
- validação estrutural e migração de versões do documento.

### 7.4 TPLO

Responsável pelas regras específicas do primeiro procedimento:

- parâmetros do planejamento TPLO;
- geometria do platô tibial;
- círculo/lâmina de osteotomia;
- centro de rotação;
- rotação alvo e medidas derivadas;
- checklist clínico necessário antes da finalização.

As fórmulas, tolerâncias e obrigatoriedades serão homologadas com cirurgião veterinário. Nenhuma interpretação do comportamento do concorrente será considerada validação clínica.

### 7.5 Implants

Responsável por:

- fabricantes, famílias, variantes e vistas;
- dimensões reais em milímetros;
- arquivos vetoriais normalizados;
- versão e vigência do catálogo;
- proveniência, licença e checksum;
- instâncias posicionadas em um plano.

### 7.6 Reports

Responsável por:

- snapshot da revisão finalizada;
- renderização de imagem e PDF;
- template versionado;
- rastreabilidade entre relatório, plano, catálogo e arquivos de origem.

### 7.7 Audit

Responsável por registrar eventos relevantes sem armazenar tokens ou conteúdo clínico desnecessário em logs técnicos.

## 8. Modelo de domínio inicial

### 8.1 Agregados principais

#### Case

- `id`
- `tenant_id`
- `title`
- `animal_name`
- `species`
- `breed`
- `sex`
- `birth_date` ou idade aproximada
- `weight`
- `clinical_notes`
- `status`: `DRAFT`, `IN_PLANNING`, `READY`, `ARCHIVED`
- `created_by`
- timestamps

Dados do tutor só serão armazenados se houver requisito comprovado. Minimização de dados é preferível.

#### ImageAsset

- `id`
- `tenant_id`
- `case_id`
- `kind`: `DICOM`, `PNG`, `JPEG`
- `status`: `PENDING_UPLOAD`, `QUARANTINED`, `PROCESSING`, `READY`, `REJECTED`
- `source_object_key`
- `source_sha256`
- `media_type`
- dimensões e bit depth
- orientação/projeção declarada
- metadados DICOM permitidos
- chaves de derivados
- motivo de rejeição seguro

#### Calibration

- `id`
- `image_id`
- método: linha ou círculo
- valor real em milímetros
- pontos geométricos no espaço da imagem
- `millimeters_per_pixel`
- origem: manual ou metadata informativa
- usuário, data e versão

Uma calibração DICOM automática deve ser marcada como informativa até existir uma decisão clínica explícita sobre seu uso.

#### SurgicalPlan

- `id`
- `tenant_id`
- `case_id`
- `image_id`
- `procedure_type`: inicialmente `TPLO`
- `status`: `DRAFT`, `FINALIZED`, `SUPERSEDED`, `ARCHIVED`
- `current_revision`
- `created_by`
- `finalized_by`
- timestamps

#### PlanRevision

- `id`
- `plan_id`
- `revision_number`
- `schema_version`
- documento JSONB imutável
- hash canônico do documento
- autor e timestamp
- razão opcional da revisão
- catálogo de implantes referenciado

#### Implant catalog

- `Manufacturer`
- `ImplantFamily`
- `ImplantVariant`
- `ImplantViewAsset`
- `CatalogRelease`

Cada asset deverá registrar unidade, dimensões, orientação, lateralidade, fonte, licença, checksum e estado de aprovação.

#### Report

- `id`
- `tenant_id`
- `case_id`
- `plan_id`
- `plan_revision_id`
- `template_version`
- `status`
- object key e checksum
- timestamps

### 8.2 Identidade externa

`user_id` e `tenant_id` são identificadores externos emitidos/geridos pela `authentication_api`. Não haverá foreign key entre bancos. O backend armazena os IDs necessários à auditoria, mas não replica senha, e-mail ou perfil completo.

### 8.3 Isolamento de tenant

- todas as tabelas clínicas possuem `tenant_id` não nulo;
- todas as queries de repositório exigem `TenantContext`;
- índices e unicidades incluem tenant quando pertinente;
- IDs opacos não substituem autorização;
- considerar PostgreSQL Row Level Security como defesa adicional;
- testes negativos entre tenants são obrigatórios;
- object keys são segregadas por ambiente e tenant, mas a autorização nunca depende apenas do nome da chave.

## 9. Documento geométrico do plano

### 9.1 Fonte de verdade

O plano será salvo como um documento versionado com:

- `schema_version`;
- referência à imagem original e à calibração;
- sistema de coordenadas;
- viewport apenas quando necessário para restaurar UX, nunca para definir medidas;
- objetos vetoriais;
- fragmentos e máscaras;
- matrizes de transformação;
- instâncias de implantes;
- parâmetros TPLO;
- metadados de edição.

### 9.2 Sistemas de coordenadas

Devem existir três espaços explícitos:

1. **Image space:** pixels da matriz original, independente do tamanho da tela.
2. **Patient space:** milímetros derivados da calibração.
3. **Viewport space:** coordenadas de apresentação, zoom, pan e rotação visual.

Medições e objetos persistidos nunca devem usar coordenadas da página, CSS ou viewport como fonte clínica.

### 9.3 Tipos de objeto previstos

- `measurement.line`
- `measurement.circle`
- `measurement.angle`
- `annotation.text`
- `axis.anatomic`
- `axis.mechanical`
- `tplo.plateau_line`
- `tplo.saw_circle`
- `tplo.osteotomy`
- `fragment.mask`
- `fragment.transform`
- `implant.instance`

Cada tipo terá contrato discriminado, IDs estáveis, visibilidade, lock, estilo e dados geométricos. Estilo visual não deve alterar o valor clínico.

### 9.4 Máscaras e fragmentos

A seleção de fragmento não deve depender da cor dos pixels. A máscara será binária/alpha, derivada de um polígono fechado no espaço da imagem. A transformação será uma matriz afim explícita aplicada ao fragmento. O fundo e o fragmento continuam relacionados à mesma imagem original.

### 9.5 Revisões e concorrência

- autosave cria uma nova revisão ou snapshot consolidado segundo política de retenção;
- o cliente envia a versão base por `If-Match` ou campo equivalente;
- conflito de versão retorna `409 PLAN_VERSION_CONFLICT`;
- o frontend oferece recarregar, duplicar ou reconciliar; merge geométrico automático não faz parte do MVP;
- finalizar gera uma revisão imutável;
- editar após finalização cria uma nova revisão/versão de plano, sem alterar o relatório anterior.

## 10. Autenticação e autorização

### 10.1 Gate obrigatório AUTH-01

Antes do primeiro vertical slice, `authentication_api`, frontend e backend deverão aprovar um contrato único contendo:

- `iss` exato por ambiente;
- `aud` exclusivo aceito pelo VetOrthoPlan;
- algoritmo permitido: RS256;
- `sub` como único identificador de usuário;
- `exp`, `iat`, `jti` e `nbf` quando presente;
- `scopes` como array canônico, acompanhando o formato já emitido;
- `tenant_id` como organização ativa única;
- sem confiança em nome ou e-mail para autorização;
- endpoint JWKS/discovery canônico;
- TTL e cache das chaves;
- processo de rotação de `kid` e janela de sobreposição;
- comportamento de logout/revogação durante o TTL do access token.

### 10.2 Audiência

O backend não deverá aceitar tokens com audiência genérica `authentication-api`. A audiência proposta é `vetorthoplan-api` ou um `client_id` formalmente registrado para o BFF. A escolha final depende de como a `authentication_api` emitirá tokens first-party destinados ao resource server.

Abordagens aceitáveis para o spike de integração:

1. fluxo OAuth existente, com client application própria, audience vinculada ao cliente e aquisição server-side pelo BFF; ou
2. extensão first-party da `authentication_api` para emitir/trocar token audience-bound e tenant-bound para o BFF autenticado.

Não é aceitável permitir que o navegador escolha livremente a audiência ou encaminhar ao backend o token interno destinado apenas à própria Authentication API.

### 10.3 Tenant ativo

O token deverá representar um tenant ativo. O BFF pode permitir que o usuário selecione uma organização, mas a `authentication_api` precisa confirmar membership e emitir o contexto assinado. Um header `X-Tenant-Id` sozinho é apenas uma preferência solicitada e nunca prova autorização.

Caso a projeção de membership seja sincronizada por eventos, estes deverão ser assinados, idempotentes, ordenáveis por entidade e reconciliáveis. Os eventos organizacionais existentes na enumeração da `authentication_api` precisam ter sua emissão testada antes de serem usados.

### 10.4 Scopes iniciais propostos

- `vetorthoplan:cases:read`
- `vetorthoplan:cases:write`
- `vetorthoplan:images:read`
- `vetorthoplan:images:write`
- `vetorthoplan:plans:read`
- `vetorthoplan:plans:write`
- `vetorthoplan:plans:finalize`
- `vetorthoplan:implants:read`
- `vetorthoplan:implants:manage`
- `vetorthoplan:reports:read`
- `vetorthoplan:reports:create`
- `vetorthoplan:audit:read`

Scopes concedem capacidade máxima. O backend ainda verifica tenant, papel clínico e ownership/acesso ao caso.

### 10.5 Papéis de produto

- **Tenant Owner:** configura clínica e membros; não recebe automaticamente poderes clínicos se a política não permitir.
- **Surgeon:** cria, edita e finaliza planos.
- **Clinical Assistant:** cria casos, envia imagens e edita dados permitidos; finalização depende de política.
- **Viewer:** somente leitura de casos autorizados.
- **Catalog Manager:** administra implantes; preferencialmente papel de plataforma separado.
- **Platform Administrator:** operação técnica, com acesso clínico excepcional, justificado e auditado.

Os papéis globais `USER` e `ADMIN` da autenticação não devem ser traduzidos diretamente em permissões clínicas amplas.

### 10.6 Validação local do JWT

O backend valida localmente assinatura, algoritmo, `iss`, `aud`, tempos, `jti`, `sub`, `tenant_id` e scopes. Chaves são obtidas por JWKS e mantidas em cache com refresh seguro quando surge `kid` desconhecido. Falha de JWKS não deve permitir bypass; chaves ainda válidas podem permanecer em stale cache por uma janela definida.

Tokens, cookies e Authorization headers nunca são registrados.

## 11. Contrato HTTP do backend

### 11.1 Convenções

- prefixo `/api/v1`;
- OpenAPI 3.1 versionado em `openapi/openapi.yaml`;
- JSON em `snake_case` no backend e tipos gerados no frontend;
- IDs opacos e não sequenciais;
- timestamps ISO 8601 em UTC;
- paginação por cursor;
- filtros e ordenação por allowlist;
- `Idempotency-Key` em criações e comandos repetíveis;
- `ETag`/`If-Match` ou versão equivalente para planos;
- `202 Accepted` para jobs;
- `204 No Content` para sucesso sem corpo;
- `409 Conflict` para versão, idempotência ou estado incompatível;
- `traceparent` e `x-request-id` propagados.

Erro padrão:

```json
{
  "code": "PLAN_VERSION_CONFLICT",
  "message": "O plano foi alterado por outra sessão.",
  "details": {},
  "trace_id": "01..."
}
```

O BFF pode reduzir detalhes antes de devolver o erro ao navegador. Mensagens internas, stack traces, chaves de storage e metadados sensíveis não fazem parte do contrato público.

### 11.2 Recursos previstos para o MVP

#### Casos

- `POST /api/v1/cases`
- `GET /api/v1/cases`
- `GET /api/v1/cases/{case_id}`
- `PATCH /api/v1/cases/{case_id}`
- `POST /api/v1/cases/{case_id}/archive`

#### Upload e imagens

- `POST /api/v1/cases/{case_id}/image-uploads`
- `POST /api/v1/image-uploads/{upload_id}/complete`
- `GET /api/v1/cases/{case_id}/images`
- `GET /api/v1/images/{image_id}`
- `GET /api/v1/images/{image_id}/content-access`
- `DELETE /api/v1/images/{image_id}` enquanto permitido pelo estado do caso

#### Planos

- `POST /api/v1/cases/{case_id}/plans`
- `GET /api/v1/cases/{case_id}/plans`
- `GET /api/v1/plans/{plan_id}`
- `PUT /api/v1/plans/{plan_id}/document`
- `GET /api/v1/plans/{plan_id}/revisions`
- `GET /api/v1/plans/{plan_id}/revisions/{revision}`
- `POST /api/v1/plans/{plan_id}/finalize`
- `POST /api/v1/plans/{plan_id}/duplicate`

#### Implantes

- `GET /api/v1/implant-catalog/releases/current`
- `GET /api/v1/implant-families`
- `GET /api/v1/implant-families/{family_id}/variants`
- `GET /api/v1/implant-variants/{variant_id}`

Rotas de administração do catálogo devem ser separadas e não são necessárias para o primeiro piloto se o catálogo for carregado por pipeline controlado.

#### Relatórios e jobs

- `POST /api/v1/plans/{plan_id}/reports`
- `GET /api/v1/reports/{report_id}`
- `GET /api/v1/reports/{report_id}/content-access`
- `GET /api/v1/jobs/{job_id}`

#### Operação

- `GET /health/live`
- `GET /health/ready`
- endpoint de métricas somente na rede operacional apropriada.

### 11.3 Limites provisórios

Os valores finais serão medidos na descoberta. Para o primeiro desenho:

- até 100 MiB por arquivo;
- até 20 arquivos por caso no MVP;
- JSON comum até 1 MiB;
- documento de plano até 5 MiB;
- URL pré-assinada de upload válida por poucos minutos;
- timeouts curtos para metadata e maiores apenas em jobs assíncronos;
- rate limit por usuário, tenant e IP nas rotas sensíveis.

## 12. Integração com `vetorthoplan_frontend`

### 12.1 Responsabilidade do BFF

O navegador chama apenas rotas do mesmo domínio. O BFF:

- resolve/renova a sessão existente;
- adquire o token correto para o VetOrthoPlan;
- injeta `Authorization: Bearer` server-side;
- propaga `traceparent` e request ID;
- valida Origin/CSRF em mutações;
- aplica timeout;
- normaliza `401`, `403`, `409`, `422`, `429` e `5xx`;
- não envia token ao JavaScript;
- não registra corpo clínico ou credenciais;
- repassa apenas URLs pré-assinadas com escopo mínimo e prazo curto.

### 12.2 Cliente gerado

Adicionar um contrato separado para o backend clínico e gerar tipos automaticamente. O objetivo recomendado é evoluir `@capta/api-client` para um pacote neutro ou `@vetorthoplan/api-client`, com exports distintos para Authentication API e VetOrthoPlan API.

Arquivos gerados nunca serão editados manualmente. Mudanças incompatíveis deverão falhar no CI por diff/contract test.

### 12.3 Organização das features

```text
apps/web/src/features/
├── cases/
├── imaging/
├── planning/
├── tplo/
├── implants/
└── reports/
```

Cada feature concentra componentes, hooks, schemas, services e testes. Páginas do App Router apenas compõem a feature. O shell global não deve conhecer detalhes do viewer.

### 12.4 Viewer

Utilizar Cornerstone3D diretamente como motor de visualização médica, com ferramentas específicas do VetOrthoPlan sobre a camada de rendering. O OHIF pode ser usado como referência arquitetural, mas incorporar o viewer completo tende a impor workflows não alinhados ao planejamento ortopédico.

Referências técnicas:

- Cornerstone3D: <https://www.cornerstonejs.org/docs/getting-started/overview/>
- OHIF: <https://docs.ohif.org/>

O frontend deve manter interações de alta frequência localmente e persistir comandos/snapshots por autosave. Não se deve transmitir uma imagem raster completa ao backend a cada movimento.

### 12.5 Estado no frontend

- React Query para estado remoto e invalidação.
- Estado transitório do canvas isolado do restante da aplicação.
- Documento do plano com reducer/command model testável.
- Undo/redo local baseado em comandos.
- Autosave debounced e idempotente.
- Indicadores explícitos: salvando, salvo, conflito, offline/erro.
- Nenhuma promessa de operação offline no MVP.

### 12.6 Segurança de conteúdo

A adoção do viewer exigirá revisar CSP para `worker-src`, `connect-src`, WebAssembly e origens do object storage. A política deve ser ampliada por allowlist mínima e testada; não liberar `unsafe-eval` como solução genérica.

## 13. Ingestão e ciclo de vida de imagens

### 13.1 Pipeline

```text
PENDING_UPLOAD
      │ upload + checksum
      ▼
QUARANTINED
      │ validação/scan
      ▼
PROCESSING ───────▶ REJECTED
      │ metadata + derivados
      ▼
READY
```

### 13.2 Regras

- detectar o formato pelo conteúdo, não apenas por extensão ou header;
- recusar payloads poliglotas, formatos não permitidos e dimensões abusivas;
- calcular SHA-256 durante a ingestão;
- limitar descompressão para impedir decompression bombs;
- validar transfer syntaxes DICOM homologadas;
- armazenar original imutável com criptografia;
- gerar derivados sem substituir o original;
- extrair apenas tags em allowlist;
- tratar tags de texto livre como potencialmente identificáveis;
- remover metadados desnecessários de thumbnails e exports;
- manter pixel spacing DICOM como informação, sem substituir automaticamente a calibração clínica manual;
- nunca converter a fonte clínica apenas para JPEG com perdas.

### 13.3 Conteúdo de teste

Radiografias usadas em desenvolvimento e CI devem ser sintéticas, públicas com licença compatível ou formalmente desidentificadas. Nenhum arquivo de projeto externo deve ser copiado automaticamente para este repositório.

## 14. Fluxo clínico TPLO a validar

Este fluxo é hipótese de produto e requer validação com cirurgião:

1. selecionar caso e radiografia mediolateral apropriada;
2. confirmar orientação, lado e qualidade da incidência;
3. calibrar por marcador radiopaco usando linha ou círculo;
4. marcar referências anatômicas do platô tibial;
5. calcular/exibir o TPA inicial;
6. posicionar círculo de serra e centro de osteotomia;
7. confirmar raio/lâmina;
8. definir máscara do fragmento proximal;
9. simular rotação até o objetivo clínico informado;
10. calcular ângulo, deslocamento de corda e medidas auxiliares homologadas;
11. selecionar e posicionar placa/implantes compatíveis;
12. registrar observações e medidas operatórias;
13. executar checklist de completude;
14. finalizar revisão e gerar relatório.

### 14.1 Invariantes propostas

- plano não pode ser finalizado sem imagem `READY`;
- medições em milímetros exigem calibração válida;
- alteração da calibração invalida ou recalcula explicitamente medidas dependentes;
- instância de implante registra a versão exata do catálogo;
- exclusão de imagem é impedida quando há plano finalizado que a referencia;
- relatório sempre aponta para uma revisão imutável;
- alterações clínicas relevantes geram audit event;
- valores calculados preservam precisão interna e arredondam apenas para exibição.

## 15. Persistência e storage

### 15.1 PostgreSQL

Banco/schema exclusivo do serviço. Nenhuma consulta ao banco da `authentication_api`.

Práticas obrigatórias:

- migrations versionadas e revisáveis;
- migrações de schema separadas do start da aplicação;
- `tenant_id` indexado;
- constraints para estados e unicidades importantes;
- transações locais por agregado;
- outbox gravada na mesma transação das mudanças relevantes;
- backup, restore testado e point-in-time recovery em produção;
- pooling com limites por ambiente.

### 15.2 Object storage

Separação lógica ou física entre:

- `quarantine/`
- `originals/`
- `derived/`
- `catalog/`
- `reports/`

Requisitos:

- bucket privado;
- criptografia com chave gerenciada;
- versionamento conforme política;
- acesso apenas por role do serviço/worker;
- URLs assinadas curtas;
- lifecycle por classe de objeto;
- política explícita de retenção e exclusão;
- eventos de deleção auditados;
- inventário periódico para detectar órfãos entre banco e storage.

## 16. Processamento assíncrono e eventos

### 16.1 Jobs do MVP

- `ingest_image`
- `extract_dicom_metadata`
- `generate_image_derivatives`
- `generate_plan_preview`
- `generate_report`
- `delete_case_objects`
- `reconcile_orphan_objects`

### 16.2 Garantias

- entrega pelo menos uma vez;
- consumidor idempotente;
- retry apenas para falha transitória, com backoff e jitter;
- dead-letter queue;
- timeout por etapa;
- estado do job persistido;
- correlação por `trace_id`, `tenant_id` pseudonimizado e resource ID;
- payload de fila contém referências, não binários ou dados clínicos extensos.

### 16.3 Eventos de domínio/outbox

- `case.created`
- `image.upload.completed`
- `image.ready`
- `image.rejected`
- `plan.created`
- `plan.revision.saved`
- `plan.finalized`
- `report.requested`
- `report.ready`

Eventos internos não devem ser confundidos com contrato público. Se publicados externamente, exigem schema, versão e política de compatibilidade.

## 17. Segurança, privacidade e LGPD

### 17.1 Classificação de dados

Dados clínicos do animal não são automaticamente dados pessoais de uma pessoa natural, mas casos podem conter dados de tutores, profissionais, clínicas, contatos e texto livre identificável. O sistema será desenhado assumindo presença de dados pessoais.

Referência: Lei Geral de Proteção de Dados, especialmente arts. 5º e 46: <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm>

### 17.2 Controles mínimos

- TLS em trânsito e criptografia em repouso;
- least privilege em IAM, banco e storage;
- isolamento de rede; backend e banco sem exposição pública direta;
- validação de entrada e output encoding;
- proteção contra SSRF em importações futuras por URL;
- CORS restrito; preferencialmente backend aceita somente gateway/BFF;
- rate limit e limites de payload;
- secrets em secret manager;
- imagens de container sem root e com filesystem read-only quando possível;
- SAST, análise de dependências, SBOM e scan de imagem;
- logs estruturados com redaction;
- auditoria separada de logs de diagnóstico;
- retenção, exportação e exclusão documentadas;
- resposta a incidente e comunicação definidas;
- revisão de ameaça antes do piloto.

### 17.3 Auditoria funcional

Registrar, no mínimo:

- criação/arquivamento de caso;
- upload, rejeição e exclusão de imagem;
- criação e finalização de plano;
- mudança de calibração;
- geração/download de relatório;
- acesso administrativo excepcional;
- mudanças de catálogo.

Não registrar o conteúdo do JWT, URL pré-assinada, cookie, notas clínicas completas ou pixels da imagem.

### 17.4 Compartilhamento futuro

Links públicos não fazem parte do MVP. Quando implementados, deverão usar grants próprios, hash do token no banco, expiração, escopo de leitura/importação, revogação e auditoria. Um link não deverá expor IDs internos nem herdar permissões maiores do criador.

## 18. Observabilidade e confiabilidade

### 18.1 Instrumentação

- logs JSON com `service`, `environment`, `trace_id`, `request_id` e versão;
- traces OpenTelemetry entre BFF, gateway, backend, banco, storage e worker;
- métricas RED para HTTP: rate, errors, duration;
- métricas de fila: idade, profundidade, retries e DLQ;
- métricas de ingestão por formato e causa de rejeição;
- métricas de autosave, conflitos e geração de relatório;
- dashboards e alertas antes do piloto.

IDs de usuário e tenant, quando necessários em telemetria, devem ser pseudonimizados ou restritos ao audit log apropriado.

### 18.2 SLOs iniciais propostos

Para homologação/piloto, validar e ajustar:

- disponibilidade mensal da API: 99,9% após estabilização;
- p95 de endpoints de metadata: até 300 ms sem contar rede do cliente;
- confirmação de autosave: p95 até 1 s;
- criação de sessão de upload: p95 até 500 ms;
- ingestão de radiografia comum: 95% concluída em até 30 s;
- relatório: 95% concluído em até 60 s;
- RPO de produção: até 15 minutos;
- RTO de produção: até 4 horas.

Metas de precisão clínica serão definidas separadamente pelo responsável clínico; não devem ser inventadas pelo time de software.

### 18.3 Health checks

- `/health/live`: apenas processo/event loop ativo; não consulta dependências.
- `/health/ready`: verifica dependências necessárias para receber tráfego, com timeout curto.
- falha de storage/fila pode degradar rotas específicas sem necessariamente derrubar leituras de metadata.

## 19. Infraestrutura e deploy

### 19.1 Topologia AWS proposta

- CDN/WAF e domínio do frontend;
- frontend Next.js conforme estratégia já existente;
- API Gateway;
- `vetorthoplan_backend` em ECS Fargate ou runtime equivalente privado;
- worker separado, escalável por fila;
- RDS PostgreSQL;
- S3 com KMS;
- SQS com DLQ;
- secret manager;
- OpenTelemetry collector e destino de logs/métricas;
- backups e alarmes.

Não reutilizar banco, bucket ou credenciais da `authentication_api`.

### 19.2 IaC

Criar módulos Terraform específicos do VetOrthoPlan em repositório de infraestrutura definido pelo time. Não acoplar o novo domínio ao `captagov_terraform` apenas por conveniência histórica.

O pipeline deverá executar:

1. lint e formatação;
2. type check;
3. testes unitários, arquitetura, integração e contrato;
4. geração/validação de OpenAPI;
5. SAST e dependency scan;
6. build de imagem reproduzível;
7. SBOM e scan da imagem;
8. publicação com tag imutável;
9. Terraform plan;
10. aprovação de produção;
11. migration job;
12. deploy gradual e smoke tests;
13. rollback documentado.

### 19.3 Ambientes

- local;
- test/CI;
- homologação com dados sintéticos ou desidentificados;
- piloto controlado;
- produção.

Cada ambiente terá issuer/audience, banco, bucket, chaves e secrets próprios.

## 20. Estratégia de testes

### 20.1 Unitários de domínio

- transições de estado;
- calibração e conversão pixel/mm;
- ângulos e transformações;
- invariantes TPLO homologadas;
- política de finalização;
- idempotência lógica;
- migração de schema do documento.

### 20.2 Property-based

- transformações inversas preservam pontos dentro da tolerância numérica;
- zoom/pan do viewport não alteram medidas clínicas;
- rotação de 360 graus retorna à posição equivalente;
- serializar/desserializar documento preserva geometria;
- arredondamento de UI não contamina o valor interno.

### 20.3 Integração

- PostgreSQL real em container;
- migrations forward e rollback permitido;
- S3/MinIO ou emulador homologado;
- fila e workers;
- ingestão DICOM com corpus controlado;
- geração e acesso a relatório;
- outbox e retry.

### 20.4 Contrato e autenticação

- JWKS válido e rotação de `kid`;
- assinatura, algoritmo, issuer e audience incorretos;
- token expirado e `nbf` futuro;
- ausência de `sub`, `jti`, `tenant_id` ou scopes;
- acesso cross-tenant;
- escopo insuficiente;
- token de refresh apresentado como Bearer;
- contrato consumidor-produtor com o BFF;
- OpenAPI gerado sem diff não revisado.

### 20.5 Frontend/E2E

- sessão renovada sem expor tokens;
- criação de caso e upload;
- falha/retry de upload;
- calibração com mouse e touch;
- zoom/pan sem alterar geometria;
- autosave e conflito entre duas abas;
- undo/redo;
- reabertura do plano em navegador diferente;
- relatório ligado à revisão finalizada;
- acessibilidade de todo o fluxo fora do canvas e atalhos documentados.

### 20.6 Precisão visual e clínica

- phantom/calibration fixtures com medidas conhecidas;
- golden files para renderização;
- comparação entre browsers/GPU dentro da tolerância definida;
- dataset de casos TPLO desidentificados revisado por especialista;
- dupla medição independente durante o piloto;
- registro de divergências e causa raiz.

### 20.7 Carga e resiliência

- uploads concorrentes;
- autosaves frequentes;
- fila atrasada e DLQ;
- indisponibilidade temporária de JWKS, storage e banco;
- limite de conexões;
- restore de backup;
- rollback da versão da aplicação e compatibilidade do documento.

## 21. Roadmap de execução

As durações são estimativas para um time de 3 a 5 profissionais técnicos, designer/QA compartilhado e participação recorrente de cirurgião veterinário. Trilhas podem ocorrer em paralelo.

### Fase 0 — Descoberta e decisões bloqueantes (2–4 semanas)

Entregáveis:

- sessão guiada no VPOP com caso sanitizado;
- jornada TPLO aprovada;
- glossário clínico;
- critérios clínicos de precisão;
- matriz de formatos DICOM prioritários;
- decisão de catálogo/licenciamento;
- threat model inicial;
- AUTH-01 fechado;
- ADRs fundamentais aprovados;
- backlog priorizado.

Gate: nenhum desenvolvimento clínico começa sem contrato de tenant/audience e responsável clínico nomeado.

### Fase 1 — Fundação e vertical slice (2–3 semanas)

Estado dos entregáveis:

- [x] scaffold Python/Clean Architecture;
- [x] qualidade e testes unitários/de arquitetura do primeiro slice;
- [ ] CI e observabilidade básica;
- [x] banco e migration inicial (DDL validado offline; não aplicado);
- [x] JWT/JWKS integrado no backend; aplicação da migration e configuração de ambiente ainda pendentes;
- [ ] BFF chamando endpoint protegido;
- [ ] tenant isolation com identidade real testado;
- [x] OpenAPI gerado e Swagger publicado;
- [x] `/health/live`;
- [ ] `/health/ready` e deploy em homologação.

O endpoint de criação de caso foi antecipado como primeiro slice funcional. O modo local usa identidade fixa somente em `local`, `development` e `test`; o gate de ponta a ponta ainda exige BFF e banco configurados com JWT.

Gate: um usuário autenticado acessa um recurso sintético apenas no tenant correto, ponta a ponta.

### Fase 2 — Casos e ingestão (3–5 semanas)

Estado dos entregáveis:

- [ ] CRUD controlado completo de casos (criar, listar e consultar concluídos; editar e arquivar pendentes);
- [x] busca, filtro por status e paginação por cursor na listagem;
- [x] criação de sessão de upload direto pré-assinado;
- [x] confirmação do objeto e promoção para quarentena;
- [ ] ingestão assíncrona completa (worker inicial concluído; retry, recuperação e derivados pendentes);
- [ ] DICOM/PNG/JPEG completos (conteúdo e checksum validados; parsing clínico DICOM pendente);
- [ ] metadados em allowlist;
- [ ] thumbnail/derivados;
- [ ] listagem e visualização inicial no frontend (contratos, endpoints e referências visuais concluídos; implementação no frontend pendente).

`POST /api/v1/cases`, `GET /api/v1/cases`, `GET /api/v1/cases/{case_id}`, `POST /api/v1/cases/{case_id}/image-uploads`, `POST /api/v1/image-uploads/{upload_id}/complete`, `GET /api/v1/jobs/{job_id}`, `GET /api/v1/cases/{case_id}/images` e `GET /api/v1/images/{image_id}` estão implementados. Edição, arquivamento, derivados e visualização de pixels permanecem pendentes.

Gate: corpus homologado é importado sem corromper o original e sem vazamento de tenant.

### Fase 3 — Viewer, calibração e geometria (4–6 semanas)

Entregáveis planejados:

- Cornerstone3D integrado;
- zoom, pan, window/level;
- linha, círculo, ângulo e texto;
- calibração linha/círculo;
- documento versionado;
- autosave, undo/redo e conflitos;
- testes de precisão e golden files.

Gate: medidas permanecem invariantes entre zoom, tamanho de tela, reload e browsers homologados.

### Fase 4 — Workflow TPLO (4–6 semanas)

Entregáveis planejados:

- marcação do platô/TPA;
- ferramenta de círculo/serra;
- seleção de fragmento;
- rotação/translação e métricas derivadas;
- checklist de finalização;
- revisão clínica iterativa.

Gate: especialista completa casos de referência com resultados dentro das tolerâncias aprovadas.

### Fase 5 — Implantes, relatório e piloto (4–6 semanas)

Entregáveis planejados:

- catálogo inicial licenciado;
- filtro, tamanho, lado, vista, opacidade e transformação;
- relatório PDF e imagem;
- auditoria completa;
- runbooks, backup/restore e alarmes;
- hardening e teste de carga;
- piloto controlado.

Gate: critérios clínicos, segurança, suporte e operação aprovados para o piloto.

### Horizonte

- MVP TPLO pilotável: aproximadamente 4–6 meses com trabalho paralelo.
- SaaS multi-clínica endurecido: aproximadamente 8–12 meses.
- Paridade ampla com o produto de referência: 12–24 meses ou mais, fortemente dependente do catálogo e da validação clínica.

## 22. Backlog por épicos

| Épico | Resultado | Dependências | Estado no último check-in |
|---|---|---|---|
| ARCH-01 | Scaffold e regras de Clean Architecture | ADRs iniciais | Parcial — scaffold e testes criados |
| IAM-01 | Token audience/tenant-bound e autorização local | `authentication_api`, AUTH-01 | Pendente — identidade local provisória |
| BFF-01 | Cliente e proxy tipados sem token no browser | IAM-01, OpenAPI | Pendente |
| CASE-01 | Casos isolados por tenant | IAM-01, DB | Parcial — criar, listar e consultar implementados |
| IMG-01 | Upload seguro | CASE-01, storage | Concluído em código — sessão, assinatura, confirmação e quarentena; infraestrutura não aplicada |
| IMG-02 | Ingestão e consulta de imagens | IMG-01, fila | Parcial — worker inicial, estados e consultas implementados; parsing DICOM, retry e derivados pendentes |
| VIEW-01 | Visualização DICOM e imagens | IMG-01 | Pendente |
| GEO-01 | Documento geométrico e calibração | VIEW-01 | Pendente |
| PLAN-01 | Revisões, autosave e concorrência | GEO-01 | Pendente |
| TPLO-01 | Workflow clínico TPLO | PLAN-01, validação clínica | Pendente |
| IMP-01 | Catálogo e posicionamento de implantes | licença, GEO-01 | Pendente |
| REP-01 | Exportação e relatórios | TPLO-01, IMP-01 | Pendente |
| AUD-01 | Auditoria funcional | IAM-01, todos os módulos | Pendente |
| OBS-01 | Logs, métricas, tracing e alertas | infraestrutura | Pendente |
| SEC-01 | Threat model, scans e testes de isolamento | todas as fases | Pendente |
| OPS-01 | Deploy, backup, restore e runbooks | infraestrutura | Pendente |
| QA-01 | Corpus, precisão, E2E e aceite clínico | responsável clínico | Pendente |

## 23. ADRs que devem preceder implementação

1. ADR-001 — Monólito modular clínico versus múltiplos microserviços.
2. ADR-002 — Python/FastAPI e regras de Clean Architecture.
3. ADR-003 — Contrato de token audience-bound e tenant-bound.
4. ADR-004 — BFF como único cliente da API de metadata.
5. ADR-005 — Upload direto com URL pré-assinada.
6. ADR-006 — PostgreSQL + JSONB para revisões do plano.
7. ADR-007 — Original imutável e derivados no object storage.
8. ADR-008 — Cornerstone3D como motor do viewer.
9. ADR-009 — Modelo de coordenadas e precisão numérica.
10. ADR-010 — Outbox e processamento assíncrono.
11. ADR-011 — Estratégia de catálogo/licenciamento de implantes.
12. ADR-012 — Política de retenção, exclusão e auditoria.
13. ADR-013 — Stack de fila/worker e geração de PDF.

## 24. Riscos principais

| Risco | Probabilidade | Impacto | Mitigação |
|---|---:|---:|---|
| Token atual sem tenant/audience adequados | Alta | Crítico | Fechar AUTH-01 antes do vertical slice |
| Erro de precisão geométrica | Média | Crítico | Phantom, property tests, golden files e aceite clínico |
| Catálogo sem direito de uso | Alta | Alto | Acordos/licença e catálogo pequeno no MVP |
| Variabilidade DICOM | Alta | Alto | Corpus representativo, codecs homologados e ingestão assíncrona |
| Vazamento cross-tenant | Média | Crítico | Contexto obrigatório, RLS, testes negativos e auditoria |
| Dados identificáveis em fixtures | Alta | Alto | Inventário, desidentificação e política de datasets |
| Frontend ainda acoplado ao nome CaptaGov | Alta | Médio | Trilha de fundação e nomenclatura antes das features |
| Autosave sobrescrever outra sessão | Média | Alto | Versionamento otimista e `409` explícito |
| Upload grande saturar BFF/API | Média | Alto | URL pré-assinada, quotas e quarentena |
| Escopo crescer para paridade total | Alta | Alto | TPLO-first, gates e não objetivos explícitos |
| Copiar ativos/workflows proprietários | Média | Alto | Design próprio, proveniência e revisão jurídica |
| Falta de especialista disponível | Média | Crítico | Responsável clínico formal e agenda de aceite |

## 25. Definition of Done do MVP

- [ ] jornada TPLO e tolerâncias aprovadas por responsável clínico;
- [ ] OpenAPI 3.1 versionado e cliente frontend gerado;
- [ ] JWT valida assinatura, algoritmo, issuer, audience, tempos, `jti`, scopes e tenant;
- [ ] nenhum access/refresh token disponível ao JavaScript do navegador;
- [ ] banco e storage exclusivos do serviço;
- [ ] migrations automatizadas e testadas;
- [ ] originais imutáveis com checksum;
- [ ] DICOM, PNG e JPEG homologados no corpus do MVP;
- [ ] calibração e medidas independentes do viewport;
- [ ] documento do plano versionado e migrável;
- [ ] autosave idempotente e conflitos tratados;
- [ ] plano finalizado e relatório são rastreáveis à revisão;
- [ ] catálogo inicial possui licença/proveniência e dimensões verificadas;
- [ ] testes cross-tenant e de scopes passam;
- [ ] testes unitários, property-based, integração, contrato e E2E passam;
- [ ] precisão validada com casos-padrão;
- [ ] `/health/live`, `/health/ready`, métricas, logs e traces publicados;
- [ ] alertas, backup, restore e rollback testados;
- [ ] SAST, dependências, SBOM e container scan aprovados;
- [ ] documentação LGPD, retenção, incidente e suporte publicada;
- [ ] piloto usa apenas dados autorizados e ambiente aprovado.

## 26. Validação futura com acesso ao VPOP

Não é necessário compartilhar senha. O titular da conta deve realizar o login e usar um caso sem dados pessoais desnecessários. A sessão de descoberta deverá observar comportamento, não copiar ativos.

Roteiro:

1. criação e organização de caso;
2. upload DICOM e imagem comum;
3. metadata e orientação;
4. calibração por linha e círculo;
5. zoom, pan e window/level;
6. linhas, círculos, ângulos, eixos e anotações;
7. seleção/reposicionamento de fragmento;
8. TPLO e ferramenta de serra;
9. filtros, vistas e transformação de implantes;
10. autosave, reload, undo/redo e histórico;
11. finalização e relatório;
12. comportamento em tablet/touch;
13. erros, limites e recuperação de falhas.

Saídas esperadas:

- mapa da jornada real;
- inventário de estados e comandos;
- critérios de aceite por ferramenta;
- diferenças entre documentação pública e aplicação atual;
- lista priorizada de funcionalidades do MVP, sem replicar trade dress.

## 27. Decisões em aberto

Estas decisões precisam de owner e prazo na Fase 0:

1. Qual é a audiência canônica do backend?
2. Como a `authentication_api` emitirá token com tenant ativo?
3. Scopes e permissões serão ambos claims ou haverá um contrato único?
4. Como será feita a rotação real de JWKS/`kid`?
5. Qual papel clínico pode finalizar um plano?
6. Quais incidências radiográficas são obrigatórias no primeiro workflow?
7. Qual tolerância clínica será aceita para milímetros e graus?
8. Quais fabricantes/implantes podem ser usados legalmente no piloto?
9. Qual formato vetorial canônico será usado para os implantes?
10. Qual política de retenção e exclusão se aplica a caso, imagem e relatório?
11. Quais modalidades/transfer syntaxes DICOM entram no corpus inicial?
12. Qual infraestrutura Terraform hospedará o produto?
13. Qual stack de fila e PDF será adotada?
14. Haverá Row Level Security já no MVP?
15. Quais navegadores, tablets e GPUs serão homologados?

## 28. Próximo passo recomendado

Executar a Fase 0 antes de criar o scaffold. A primeira reunião técnica deve reunir responsável de arquitetura, responsável da `authentication_api`, responsável do frontend e responsável clínico para fechar AUTH-01, tenant, tolerâncias e catálogo.

Após essas decisões, o primeiro incremento não deve ser “CRUD de casos” isolado. Deve ser um vertical slice mínimo e seguro:

```text
login existente
  → tenant ativo assinado
  → BFF com token audience-bound
  → GET protegido no vetorthoplan_backend
  → registro isolado no PostgreSQL
  → resposta tipada pelo OpenAPI
  → trace ponta a ponta
```

Esse slice valida a integração mais arriscada antes que regras clínicas e dados reais sejam adicionados.
