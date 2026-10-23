# Contrato de identidade entre Authentication API e VetOrthoPlan

**Estado:** etapas 1 a 4 concluídas em código. A migration precisa ser aplicada no banco de destino e os ambientes precisam receber as configurações JWT antes de habilitar tráfego autenticado.

## Responsabilidades

- A `authentication_api` é a autoridade para autenticar usuários, emitir e renovar tokens e confirmar a associação do usuário à organização selecionada.
- O `vetorthoplan_backend` valida o token e aplica autorização e isolamento dos dados clínicos em todas as rotas protegidas.
- O API Gateway pode rejeitar tokens inválidos como defesa adicional, mas a autorização do backend não depende exclusivamente dele.

## Access token aceito pelo backend

O backend aceita somente um access token assinado pela `authentication_api`, com:

| Campo | Regra |
| --- | --- |
| `alg` | `RS256`, fixado na configuração do backend; nunca inferido do token |
| `kid` | Identifica uma chave publicada no JWKS configurado |
| `iss` | Igual ao issuer configurado para o ambiente |
| `aud` | Identificador dedicado `vetorthoplan-api` (ou client ID dedicado registrado para essa API) |
| `sub` | ID opaco do usuário na `authentication_api`; não assumir que seja UUID nem usar e-mail como identidade |
| `tokenUse` | `access` |
| `iat`, `exp` | Obrigatórios; validar expiração e tolerância de relógio limitada |
| `jti` | Obrigatório para rastreabilidade; não substitui a validação de assinatura |
| `sid` | Obrigatório para access tokens com sessão; a política de revogação está descrita abaixo |
| `org_id` | ID opaco da organização ativa, incluído apenas após confirmar associação ativa do usuário |

Tokens de MFA, ID tokens e tokens emitidos para outras audiências não autorizam chamadas à API clínica. O backend não aceita claims de tenant fornecidos em headers, query parameters ou corpo da requisição.

## Contexto de tenant e ator

Após validar o token, o backend resolve `sub` e `org_id` para os UUIDs internos exigidos por `TenantContext`:

- `(issuer, sub)` identifica o ator externo e é associado a um `actor_id` UUID interno;
- `(issuer, org_id)` identifica a organização externa e é associado a um `tenant_id` UUID interno;
- o vínculo ativo entre usuário e organização precisa estar confirmado pela `authentication_api` antes de emitir o token com `org_id`;
- após a validação completa do token, os mapeamentos ausentes são criados de forma idempotente; conflitos de unicidade são relidos do banco para lidar com requisições simultâneas;
- claims ausentes, vínculo inválido segundo o emissor ou inconsistência de mapeamento resultam em negação de acesso; nunca criar tenant ou ator antes da validação criptográfica.

O backend mantém UUIDs internos e cria mapeamentos explícitos, evitando conversão ou derivação de UUID a partir de CUIDs. As tabelas `auth_subject_mappings` e `auth_organization_mappings` guardam esses vínculos; elas são criadas pela migration Alembic `20261020_0013`. Não serão copiadas senhas, e-mails ou perfis de usuário para o backend.

Os mapeamentos são criados de forma idempotente somente depois que a assinatura, o issuer, a audiência, o uso do token e os claims obrigatórios forem validados. Um `org_id` só é confiável porque a `authentication_api` deve validar a organização ativa e a associação do usuário antes de emitir o token. IDs externos ficam únicos por issuer; assim, ambientes ou emissores diferentes não colidem.

O `tenant_id` do contexto vem exclusivamente do `org_id` autenticado e mapeado. Consultas e operações seguem escopadas por esse tenant. O `actor_id` vem exclusivamente do `sub` autenticado e mapeado, incluindo autoria e chaves de idempotência.

## Autorização

- Autenticação válida é necessária para todas as rotas de casos, imagens, uploads e planos.
- Health checks de liveness/readiness podem permanecer públicos, sem expor informação sensível.
- O papel global (`USER`/`ADMIN`) não concede acesso a qualquer tenant por si só.
- O papel de membro da organização pode ser usado para regras de ação (por exemplo, leitura versus alteração), mas não substitui a filtragem por tenant.
- Uma organização inativa ou associação removida não pode gerar novos tokens de tenant.

## Emissão e revogação

A `authentication_api` atualmente emite RS256 e oferece JWKS; seu access token de login usa por padrão a audiência `authentication-api`. A integração deve registrar/configurar `vetorthoplan-api` como audiência própria e incluir `org_id` somente em tokens cuja organização ativa já tenha sido selecionada e autorizada. O refresh deve preservar a audiência e revalidar a associação antes de emitir um novo token. O papel de organização pode ser emitido para futura autorização por ação, mas não é necessário para o primeiro corte: qualquer membro ativo autenticado tem o mesmo conjunto inicial de permissões do backend.

O backend valida assinatura localmente via JWKS com cache limitado e respeita `kid` durante rotação. A política escolhida para o primeiro corte é aceitar um token já emitido até `exp`; a validade atual padrão de 15 minutos limita a janela após revogação. Não será feita chamada à `authentication_api` em cada requisição. Revogação imediata poderá ser adicionada depois por introspecção de `sid` ou mecanismo de revogação com cache curto.

## Compatibilidade que precisa ser tratada

1. `authentication_api` usa IDs string/CUID para usuários e organizações. O backend usa UUID para ator e tenant; não converter `sub`/`org_id` diretamente para UUID.
2. O login padrão emite `aud=authentication-api`; a API precisa de audiência dedicada.
3. Resolvido na etapa 2: o token dedicado à organização inclui `org_id`; o emissor valida associação ativa antes de emiti-lo e durante refresh.
4. O middleware do serviço de autenticação valida estado da sessão consultando seu banco. A validação local via JWKS no backend não reproduz essa checagem.
5. Concluído na etapa 4: `identity_mode=local` é limitado a `local`, `development` e `test`; staging/produção exigem JWT, cuja configuração falha no startup se issuer, audience ou JWKS estiverem ausentes.

## Sequência de integração

1. Concluída: definir o contrato, manter os UUIDs internos e versionar a migration Alembic das tabelas de mapeamento; aceitar a janela de revogação limitada ao `exp` (15 minutos no padrão atual).
2. Concluída no `authentication_api`: `POST /authentication_api/api/v1/auth/organizations/:orgId/token` valida membro e organização ativa e emite `aud=vetorthoplan-api` com `org_id`; tokens comuns mantêm sua audiência. O refresh-token armazena e preserva audiência/organização e revalida a associação.
3. Concluída: validar RS256 via JWKS, issuer, audience única, `tokenUse=access`, claims obrigatórios e tolerância de relógio; resolver mapeamentos com `INSERT ... ON CONFLICT DO NOTHING` após validação criptográfica.
4. Concluída: todas as operações clínicas exigem `TenantContext`, os routers declaram proteção herdável, o OpenAPI anuncia Bearer e o modo local fica limitado a `local`, `development` e `test`.
5. Integrar API Gateway e deploy do backend com as mesmas regras de issuer/audience; restringir o Security Group da EC2 antes de dados reais.
