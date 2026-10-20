# Contrato de autenticação clínica — pendente de integração

## Estado do backend

O backend clínico ainda usa `IDENTITY_MODE=local`. Nesse modo, o tenant e o ator são IDs locais fixos; os endpoints clínicos não validam `Authorization: Bearer`, não retornam 401/403 por autenticação e o OpenAPI não declara `security`. O adapter `IDENTITY_MODE=jwt` ainda não está implementado. O modo local é rejeitado em `staging` e `production`.

Esta descrição é deliberada para não publicar como protegido um contrato que o serviço ainda não aplica. A ausência de Basic Auth no Apache é uma preferência do ambiente e não substitui a autenticação da aplicação.

## Dados confirmados no `authentication_api`

- assinatura de access token: JWT RS256;
- emissor padrão (`iss`): `authentication-api`;
- audiência padrão (`aud`): `authentication-api`; no fluxo OAuth, a audiência pode ser o `client_id` registrado;
- JWKS: `/authentication_api/api/v1/auth/.well-known/jwks.json`;
- claims implementadas: `sub`, `email`, `role`, `permissions` (opcional), `sid` (opcional), `jti`, `iat`, `exp`, `iss`, `aud`, `scopes` (opcional) e `tokenUse=access`.

Os valores efetivos de emissor/audiência dependem da configuração da instalação e do cliente OAuth; o backend não deve aceitar a audiência genérica sem um registro explícito para VetOrthoPlan.

## Decisões necessárias antes de declarar `security` no OpenAPI

1. Registrar o cliente/audiência do VetOrthoPlan e definir os scopes/permissões clínicos exigidos por operação.
2. Definir como o BFF seleciona o tenant ativo e como o backend valida a associação do usuário a esse tenant. O access token descrito acima não contém claim de tenant.
3. Definir como o backend alcança e atualiza o JWKS, como valida revogação/expiração e quais 401/403 padronizados serão retornados.
4. Implementar o adapter JWT, autorização tenant-scoped e testes de isolamento antes de habilitar o contrato Bearer nas operações clínicas.

Até esses pontos serem fechados, o OpenAPI informa explicitamente que a autenticação está pendente e não anuncia uma segurança que a API não executa.
