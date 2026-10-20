# Contrato de autenticação clínica — integração em andamento

## Estado do backend

O backend implementa `IDENTITY_MODE=jwt` com validação RS256 via JWKS e exige `TenantContext` em todas as rotas clínicas de casos, imagens, uploads, jobs e planos. Os routers clínicos também declaram essa dependência no nível do router para proteger novos endpoints adicionados a esses grupos. `/health/live` e `/health/ready` permanecem públicos.

`IDENTITY_MODE=local` usa os UUIDs locais somente quando `APP_ENV` é `local`, `development` ou `test`. Em `staging` e `production`, o startup falha se o modo local for selecionado. O modo JWT exige `JWT_ISSUER` e `JWKS_URL`; fora de `local`/`test`, JWKS precisa usar HTTPS. Configure também `JWT_AUDIENCE=vetorthoplan-api`.

## Dados do `authentication_api`

- assinatura de access token: JWT RS256;
- emissor padrão (`iss`): `authentication-api`;
- audiência padrão (`aud`): `authentication-api`; no fluxo OAuth, a audiência pode ser o `client_id` registrado;
- JWKS: `/authentication_api/api/v1/auth/.well-known/jwks.json`;
- para VetOrthoPlan, a rota dedicada à organização emite `org_id`, `sid`, `jti`, `iat`, `exp`, `iss`, `aud=vetorthoplan-api` e `tokenUse=access` após validar a associação ativa.

Os valores efetivos de emissor/audiência dependem da configuração da instalação e do cliente OAuth; o backend não deve aceitar a audiência genérica sem um registro explícito para VetOrthoPlan.

## Regras aplicadas pelo backend

- O backend aceita apenas `RS256`, `issuer` configurado, audiência única `vetorthoplan-api`, `tokenUse=access` e claims obrigatórios, incluindo `sub`, `org_id`, `sid`, `jti`, `iat` e `exp`.
- O tenant vem apenas de `org_id` autenticado; o ator vem de `sub`. Ambos são resolvidos para UUIDs internos por mapeamentos idempotentes no PostgreSQL.
- Claims de tenant em headers, query parameters ou corpo não são usados para autorizar chamadas.
- O JWKS usa cache limitado; indisponibilidade do provedor falha fechada com `503`, e token inválido/ausente recebe `401`.
- O backend aceita tokens até `exp`; revogação imediata via introspecção ainda não está implementada.

Consulte [identity-contract.md](identity-contract.md) para o contrato completo, a migration Alembic e as pendências de implantação. Antes de ativar JWT em ambiente de destino, aplique `alembic upgrade head` no banco correspondente e configure o mesmo issuer e audience no provedor e no backend.
