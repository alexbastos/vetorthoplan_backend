# Plano de adequação da infraestrutura AWS para testes do VetOrthoPlan

> Status: proposta; nenhuma alteração de infraestrutura foi executada
> Data da avaliação: 2026-09-15
> Escopo analisado: `PLANO_ARQUITETURAL_TPLO.md` e estado local do repositório `vetorthoplan_terraform`
> Ambiente-alvo: teste/homologação técnica com dados sintéticos ou formalmente desidentificados
> Objetivo financeiro: minimizar custo e permanecer dentro das franquias gratuitas ou dos créditos disponíveis, sem afirmar custo zero

## 1. Decisão recomendada

A estratégia principal é **replicar, em outra conta AWS, a mesma arquitetura que já está em execução no projeto de origem**. A topologia existente passa a ser a baseline validada: uma EC2 com Docker Compose, API Gateway HTTP API, S3, SES, VPC e controles de custo. As mudanças posteriores substituem nomes, repositórios, configurações e aplicações pelo contexto do VetOrthoPlan, sem redesenhar inicialmente a infraestrutura.

A arquitetura mais completa descrita no plano TPLO — Fargate, RDS, integração privada, WAF, Secrets Manager e chaves KMS gerenciadas pelo cliente — continua sendo o destino de piloto/produção, não um requisito para a réplica inicial. A baseline será replicada em etapas, sem mudar sua topologia:

- inicialmente, a mesma EC2 com frontend/BFF CaptaGov, `authentication_api`, PostgreSQL e Redis em contêineres, para comprovar a réplica na nova conta;
- posteriormente, substituição/adaptação do frontend e inclusão do `vetorthoplan_backend` e do worker na mesma EC2;
- manutenção do bucket S3 de avatares na réplica e criação posterior de bucket clínico próprio para quarentena, originais, derivados, catálogo e relatórios;
- adição de SQS e DLQ somente quando começar o processamento assíncrono clínico, preservando a arquitetura de compute existente;
- API Gateway HTTP API como endpoint HTTPS, preservado apenas se o teste do gateway fizer parte do gate de integração;
- Parameter Store Standard para configuração e segredos estáticos de teste;
- métricas básicas e logs de baixa retenção no CloudWatch;
- AWS Budgets e alarmes de uso antes de provisionar o restante;
- nenhuma porta de banco, Redis, Docker ou SSH exposta à Internet;
- somente dados sintéticos/desidentificados; a topologia compacta não é aprovada para piloto ou produção.

Essa abordagem reduz risco operacional porque reaproveita uma arquitetura já exercitada. Ela preserva os contratos mais importantes do plano — JWT/JWKS, tenant, BFF, PostgreSQL, upload pré-assinado, S3, fila, worker e observabilidade — aceitando conscientemente disponibilidade de uma única zona e menor isolamento físico.

O uso gratuito é **condicional**. Trocar de conta isola o novo ambiente e reinicia o consumo medido naquela conta, mas não prova, sozinho, elegibilidade ao Free Tier. Antes de implementar, é obrigatório confirmar a data da conta, seu tipo de plano, créditos restantes e ofertas ativas no console Billing/Free Tier. Para contas criadas em ou após 15 de julho de 2025, a AWS passou a usar créditos e um plano gratuito de até seis meses; pelas regras publicadas, quem já possuiu conta AWS pode não ser elegível ao novo plano/créditos. Contas anteriores mantêm as regras legadas, e uma conta antiga fora dos primeiros 12 meses pode pagar EC2, EBS, IPv4, S3 e API Gateway desde o primeiro uso.

### 1.1 O que significa “mudar apenas a conta”

A topologia e os tipos de recursos podem permanecer iguais, mas uma réplica entre contas exige algumas diferenças de identidade/configuração:

- credenciais/provider devem apontar inequivocamente para a conta de destino;
- o state deve ser novo e não pode ser copiado da conta de origem;
- nomes de buckets S3 são globais e, portanto, o nome fixo `authentication-api-avatars` não poderá ser reutilizado por outra conta enquanto pertencer à origem; o sufixo do account ID resolve a colisão sem alterar a arquitetura;
- key pairs, IAM roles e instance profiles são recriados na conta de destino; a chave privada do projeto de origem não deve ser copiada;
- identidades SES/DKIM precisam ser verificadas na nova conta/região;
- URLs do API Gateway mudam, exigindo atualização automática de issuer JWT, CORS, callback OAuth e origem pública;
- budgets, alertas e destinatários precisam existir e ser verificados na nova conta;
- limites, créditos e consumo do Free Tier são avaliados na conta de destino.

Para evitar apply acidental na conta errada, a futura configuração deve receber `target_account_id`, usar `data.aws_caller_identity.current.account_id` e restringir o provider com `allowed_account_ids` ou controle equivalente.

### 1.2 Sequência de implantação

1. criar state e provider exclusivos da conta de destino;
2. replicar a infraestrutura e as aplicações atuais sem alterar a conta/projeto de origem;
3. validar paridade funcional, consumo e alertas financeiros;
4. corrigir configurações críticas sem mudar a topologia;
5. adaptar nomes, frontend e artefatos para VetOrthoPlan;
6. adicionar backend clínico, storage clínico e processamento assíncrono quando essas funcionalidades existirem.

## 2. Limites desta avaliação

**Premissa de reutilização:** as referências atuais a Capta/CaptaGov e à `authentication_api` são intencionais. O Terraform e o frontend dessa aplicação serão replicados em uma conta AWS diferente e adaptados posteriormente ao contexto do VetOrthoPlan. Portanto, nomes de repositórios, variáveis, paths, imagens e recursos legados não são classificados isoladamente como defeitos. O risco existe somente se a cópia for promovida para o ambiente VetOrthoPlan antes da parametrização, separação de recursos e revisão de segurança previstas neste plano.

Foram feitas leitura estática dos arquivos Terraform e comparação com o plano arquitetural. Não foram executados `terraform init`, `terraform plan`, `terraform apply`, consultas à conta AWS nem alterações em recursos.

`terraform fmt -check` não apontou diferenças. `terraform validate` não pôde ser concluído porque os providers `hashicorp/aws` e `hashicorp/null` não estão instalados localmente; não foi executado `terraform init` para respeitar a restrição de não modificar o repositório. Portanto, esta avaliação não confirma o plano real contra o estado remoto nem a disponibilidade regional dos recursos.

O repositório Terraform inteiro aparece como não rastreado no Git local na data desta análise. Também existem no diretório um estado local, backup de estado, log de apply e uma chave privada. O conteúdo desses arquivos sensíveis não foi reproduzido neste documento.

## 3. Arquitetura de produção proposta versus réplica de teste

O `PLANO_ARQUITETURAL_TPLO.md`, seção 19, propõe corretamente para produção:

- CDN/WAF e domínio;
- API Gateway;
- backend privado em ECS Fargate ou runtime equivalente;
- worker separado;
- RDS PostgreSQL;
- S3 com KMS;
- SQS com DLQ;
- gerenciador de segredos;
- observabilidade, backups e alarmes.

Para testes iniciais, o valor principal está em validar contratos e comportamento, não alta disponibilidade. A réplica mantém o desenho operacional já utilizado no projeto de origem e posterga os componentes gerenciados de produção:

| Capacidade | Produção proposta | Teste econômico recomendado | Limitação aceita no teste |
|---|---|---|---|
| API clínica | ECS Fargate privado | contêiner na EC2 | indisponibilidade junto com a EC2 |
| Worker | serviço separado escalável | contêiner separado na mesma EC2 | disputa CPU/RAM com a API |
| PostgreSQL | RDS exclusivo | instância/role/database clínicos no PostgreSQL em contêiner | sem Multi-AZ/PITR gerenciado |
| Redis | serviço gerenciado ou equivalente | contêiner local, somente se necessário | sem HA |
| Imagens/relatórios | S3 privado com KMS | S3 privado com criptografia padrão do serviço | sem chave do cliente no teste |
| Jobs | SQS + DLQ | SQS + DLQ reais | mesma semântica; baixa escala |
| Segredos | Secrets Manager | Parameter Store Standard `SecureString` | sem rotação automática |
| Entrada HTTPS | API Gateway + integração privada | HTTP API para origem pública endurecida, ou proxy HTTPS direto durante testes locais | não comprova isolamento privado |
| Rede | subnets privadas, VPC Link e saída controlada | uma subnet pública e uma EC2 com portas mínimas | não representa rede de produção |
| Observabilidade | stack completa/OpenTelemetry | logs, métricas e alarmes essenciais | retenção curta e sem tracing gerenciado completo |
| Disponibilidade | múltiplas AZs | uma AZ | ambiente descartável |

RDS Single-AZ pode ser introduzido em uma segunda etapa somente se a conta mostrar oferta/crédito aplicável e se o objetivo do teste for validar operação gerenciada, conexão TLS, migrations e restore. Fargate deve ficar fora do ambiente econômico inicial: ele é cobrado por vCPU, memória e armazenamento enquanto a tarefa roda, e não há franquia mensal permanente apresentada na página de preços.

## 4. Topologia de teste recomendada

O diagrama representa o estado da réplica depois da adaptação clínica. No primeiro apply da nova conta, os blocos `vetorthoplan_backend`, worker, S3 clínico e SQS ainda podem estar ausentes; eles entram incrementalmente sem trocar a topologia-base.

```text
                         Internet
                            │
                  API Gateway HTTP API
                  endpoint HTTPS da AWS
                            │
             origem de teste pública endurecida
                            │
┌───────────────────────────▼────────────────────────────────────┐
│ EC2 em subnet pública, uma AZ                                 │
│                                                               │
│ reverse proxy ─┬─ frontend Next.js / BFF                      │
│                ├─ authentication_api                           │
│                └─ vetorthoplan_backend                         │
│                                                               │
│ worker VetOrthoPlan ─ PostgreSQL ─ Redis opcional             │
│ containers sem portas públicas; limites de CPU/RAM definidos  │
└───────────────┬─────────────────────┬─────────────────────────┘
                │                     │
                ▼                     ▼
       S3 clínico privado       SQS standard + DLQ
       upload pré-assinado      referências, sem binários

       Parameter Store Standard / CloudWatch / AWS Budgets
```

### 4.1 Fronteiras obrigatórias mesmo com co-localização

- O banco da `authentication_api` e o banco clínico devem ter databases, usuários e senhas distintos.
- O bucket de avatares não pode armazenar DICOM, radiografias, relatórios ou implantes.
- API e worker devem usar roles/permissões mínimas para os prefixos e filas necessários.
- O worker recebe object keys e IDs pela fila; nunca recebe a imagem no corpo da mensagem.
- PostgreSQL e Redis escutam somente na rede Docker/loopback.
- O browser continua sem receber access ou refresh token; chama o BFF.
- O backend clínico valida JWT, `iss`, `aud`, tempos, `sub`, `tenant_id` e scopes. O API Gateway não substitui a autorização de recurso.
- Toda fixture cloud deve ser sintética, pública com licença compatível ou formalmente desidentificada.

### 4.2 Entrada HTTP e compromisso de segurança

O Terraform atual integra o API Gateway diretamente ao IP público e às portas 3000/3001 da EC2. Isso fornece HTTPS ao cliente, mas não torna a origem privada. A configuração atual ainda permite alcançar a EC2 sem passar pelo gateway.

Para o ambiente econômico, escolher explicitamente uma destas opções:

1. **Preferida para integração AWS:** manter o HTTP API, publicar somente um reverse proxy em 443 com certificado válido, fazer os serviços escutarem apenas internamente e exigir no proxy uma credencial de origem adicionada pelo gateway. O valor deve ser gerado/injetado pelo pipeline e tratado como secret; se a configuração do gateway o levar ao state, esse state passa a exigir a mesma proteção do secret. Como a origem ainda é pública, esse controle é apenas defesa adicional e o ambiente deve usar exclusivamente dados não sensíveis.
2. **Preferida para desenvolvimento restrito:** dispensar temporariamente o API Gateway, permitir 443 apenas aos IPs dos testadores e usar um domínio de teste/certificado TLS no reverse proxy. Executar a validação do API Gateway em um gate separado.
3. **Necessária para piloto/produção:** mover compute para subnet privada e usar uma integração privada suportada, aceitando o custo de load balancer/VPC Link ou escolhendo outra topologia gerenciada aprovada por ADR.

Não se deve tratar uma allowlist genérica de faixas publicadas do serviço API Gateway como prova suficiente de que somente a integração concreta alcança a origem sem antes testar e documentar essa premissa.

## 5. Avaliação do Terraform atual

### 5.1 O que pode ser reaproveitado

- provider AWS e região parametrizada;
- HTTP API e stage `$default`;
- uma EC2 com Docker Compose, adequada como base de laboratório;
- fluxo de deploy do CaptaGov como referência funcional para a replicação, sujeito aos ajustes de segurança e reprodutibilidade deste plano;
- disco `gp3` de 20 GB, dentro do limite legado de EBS quando a conta ainda for elegível;
- bucket de avatares privado com Public Access Block;
- instance profile como base para acesso sem access keys estáticas;
- SES já modelado para autenticação;
- orçamento mensal com múltiplos limiares;
- health checks locais após deploy;
- VPC, Internet Gateway e subnets que podem ser corrigidos e simplificados para o teste.

### 5.2 Lacunas críticas — corrigir antes de qualquer novo deploy

| ID | Evidência atual | Risco | Alteração planejada |
|---|---|---|---|
| P0-01 | `main.tf:32-35` deixa `test_environment_open_access = true`; `ec2.tf:31-40` abre todos os protocolos/portas para `0.0.0.0/0` | comprometimento da máquina e acesso direto a bancos | remover o modo aberto; regras explícitas e padrão seguro |
| P0-02 | `api_ec2_deploy.tf:64-81` publica PostgreSQL 5432 e Redis 6379 | exposição de dados e brute force; senha não é controle de perímetro | remover port mappings públicos; acesso administrativo via SSM/port forwarding |
| P0-03 | `ec2.tf:24-54` não associa o security group à VPC criada e `ec2.tf:99-105` não define `subnet_id` | EC2/SG tendem a usar a default VPC; a VPC de `vpc.tf` fica sem workload | associar SG à `aws_vpc.main` e EC2 à subnet escolhida |
| P0-04 | state, backup, log de apply e chave privada estão na árvore de trabalho; não há `.gitignore` | vazamento de credenciais, chaves e dados sensíveis | bloquear arquivos, configurar state remoto criptografado e rotacionar segredos potencialmente expostos |
| P0-05 | `locals.tf:6-50` interpola senhas/segredos no Terraform e `api_ec2_deploy.tf:43-49` grava `.env` por provisioner | segredos persistem no state, plano, processo e host | provisionar somente nomes/ARNs; injetar valores fora do state e buscá-los em runtime via role |
| P0-06 | `api_gateway.tf:29-39` deixa authorizer comentado; rotas chamadas de “protegidas” em `:69-78` e `:104-112` não têm autorização do gateway | falsa sensação de proteção | ativar authorizer após AUTH-01 ou renomear/documentar que a proteção é exclusivamente da aplicação; manter validação no backend |
| P0-07 | integrações em `api_gateway.tf:44-179` usam HTTP e IP público da EC2 | bypass do gateway, tráfego de origem sem TLS e quebra após mudança de IP | introduzir reverse proxy/TLS, origem estável e estratégia explícita de restrição; integração privada no piloto |
| P0-08 | `main.tf` declara apenas o provider AWS, mas dois arquivos usam `null_resource` | resolução não reprodutível de provider | declarar e fixar `hashicorp/null`, ou eliminar provisioners do Terraform |

### 5.3 Lacunas altas

| ID | Evidência atual | Consequência | Alteração planejada |
|---|---|---|---|
| P1-01 | `variables.tf:13-40` ainda aponta intencionalmente para `authentication_api` e `captagov_frontend`, pois esses projetos serão a base da replicação; ainda não existe target/deploy clínico | uma cópia aplicada antes da adaptação implantaria os componentes legados, não o VetOrthoPlan | replicar primeiro; depois parametrizar identidade, nomes, paths e artefatos, adicionando backend clínico e worker por revisão imutável |
| P1-02 | `api_ec2_deploy.tf:5-8` e `frontend_ec2_deploy.tf:5-8` forçam deploy em todo apply | apply não determinístico e acoplamento entre IaC/deploy | substituir `timestamp()` por versão imutável e pipeline/SSM; separar provisionamento de release |
| P1-03 | deploy clona branch mutável e compila na EC2 | baixa rastreabilidade, alto uso de RAM e rollback frágil | publicar imagens versionadas por digest e promover digest aprovado |
| P1-04 | `ec2.tf:101` fixa `t3.micro` e o frontend já cria 2 GB de swap | 1 GB de RAM tende a ser insuficiente para frontend, duas APIs, worker, PostgreSQL e Redis | parametrizar tipo, impor limites por contêiner e executar teste de memória; usar `t3.small` apenas com crédito/orçamento aprovado |
| P1-05 | bucket S3 existente é apenas de avatares | não atende quarentena, imutabilidade, derivados, relatórios e lifecycle | criar bucket clínico separado, prefixos/policies, versionamento e lifecycle |
| P1-06 | não há SQS/DLQ | ingestão e relatório continuam síncronos | criar fila standard, DLQ, redrive, visibility timeout, retenção e alarmes |
| P1-07 | role da EC2 combina responsabilidades e SES usa `Resource = "*"` | blast radius excessivo | separar políticas por serviço/prefixo/ação e restringir SES quando suportado |
| P1-08 | não há logs do stage, retenção, alarmes da EC2/fila nem dashboard mínimo | falhas e custos ficam invisíveis | logs com redaction e retenção curta; alarmes de CPU, status, disco, DLQ e idade da fila |
| P1-09 | o budget de USD 5 só alerta; não interrompe recursos | alerta não é teto de gasto | incluir Free Tier alerts, Anomaly Detection e runbook de desligamento; opcionalmente ação segura aprovada |

Os itens P0/P1 acima são ajustes de configuração e hardening da arquitetura replicada. Eles não exigem trocar o padrão EC2 + Docker Compose + API Gateway, nem invalidam o fato de essa topologia já estar operacional no projeto de origem.

### 5.4 Lacunas médias e de manutenção

- nomes globais/fixos, como `authentication-api-avatars`, não incluem conta, região e ambiente;
- tags não são uniformes e não existem `Project`, `Environment`, `Owner`, `ManagedBy` e `CostCenter` obrigatórias;
- duas subnets são criadas, mas a topologia de teste usa uma única instância; a segunda não oferece HA real sem workloads redundantes;
- a AMI x86_64 e o tipo da instância não permitem trocar diretamente para Graviton sem imagens multi-arquitetura;
- o `user_data` baixa pacotes e Docker de fontes externas a cada criação, sem versão de imagem base ou validação de artefato;
- Swagger é público por padrão;
- CORS inclui origens locais no ambiente implantado e deve ser uma allowlist por ambiente;
- não há política explícita de EBS criptografado, IMDSv2 obrigatório, término protegido, limites de créditos T3 ou atualização de SO;
- não há backup/restore testado nem política de descarte do ambiente;
- não há lockfile do provider visível nem pipeline de `fmt`, `validate`, lint de segurança e `plan` revisado.

## 6. Free Tier e custo: o que pode e não pode ser assumido

### 6.1 Gate obrigatório de elegibilidade

Antes do primeiro `plan`, registrar em evidência de revisão:

1. data de criação da conta;
2. Free Plan ou Paid Plan;
3. créditos disponíveis e validade;
4. franquias ativas por serviço e região;
5. uso já consumido por outros projetos na conta de destino;
6. se a conta pertence ou ingressará em AWS Organizations — no modelo novo isso altera a elegibilidade;
7. região escolhida e preços fora de franquia;
8. limite financeiro mensal explicitamente aprovado.

Sem essa evidência, o plano deve mostrar o custo on-demand integral. O histórico de custo da arquitetura na conta de origem serve como referência de consumo, mas não substitui a verificação da conta de destino. “Free Tier eligible” não significa “sempre gratuito”, e créditos não eliminam o custo: apenas pagam a fatura temporariamente.

### 6.2 Classificação dos serviços propostos

| Serviço | Situação para teste | Regra de decisão |
|---|---|---|
| EC2 | condicional à conta/crédito | usar um único tipo marcado como elegível no console/API; `t3.micro` para legado elegível, ou tipo coberto pelo modelo de créditos; medir RAM |
| EBS gp3 | condicional | manter até 20–30 GB; snapshots mínimos; EBS continua existindo e pode cobrar com EC2 parada |
| IPv4 público | condicional | uma única alocação; liberar quando o ambiente for destruído; não manter EIP ocioso |
| S3 | condicional/crédito para novas contas | limitar corpus, versionamento e lifecycle; monitorar storage, requests e transferência |
| API Gateway HTTP API | baixo custo, franquia limitada por programa | usar HTTP API, sem cache pago; limitar chamadas de testes automáticos |
| SQS + DLQ | 1 milhão de requests/mês anunciado para todos os clientes | usar batching e long polling; medir receives vazios |
| CloudWatch | franquia mensal limitada | retenção de 7–14 dias, nível `info`, sem pixels/tokens/notas clínicas |
| Parameter Store Standard | sem custo adicional no tier Standard | não habilitar advanced tier/high throughput; usar `SecureString` e role |
| AWS Budgets sem ações | gratuito | manter; criar alertas menores e por forecast |
| Lambda | franquia mensal existe, mas não é escolha inicial | útil para automação curta; não migrar FastAPI/worker pesado apenas para perseguir gratuidade |
| RDS Single-AZ micro | condicional | adiar; habilitar apenas para teste específico e após confirmar oferta/crédito |
| Fargate | pago por vCPU/memória/tempo | adiar até teste de runtime/produção; desligar tarefas quando não usadas |
| NAT Gateway | custo fixo e por GB | não usar no laboratório econômico |
| ALB/NLB | custo por hora/capacidade | não usar na fase econômica; aceitar somente quando necessário à integração privada |
| Secrets Manager | cobrado por secret e chamadas, coberto apenas por créditos quando aplicável | preferir Parameter Store Standard no teste; Secrets Manager na arquitetura endurecida |
| KMS customer-managed key | custo mensal e de requests | usar criptografia padrão/AWS-owned no teste; CMK no piloto conforme threat model |
| WAF/Route 53 | custos próprios | adiar; aproveitar DNS existente quando permitido e seguro |

### 6.3 Ordem de grandeza fora de franquias

Estimativa indicativa para `us-east-1`, antes de impostos, tráfego, requests e variações futuras:

- `t3.micro` Linux contínua: aproximadamente USD 7,59/mês (`0,0104 × 730 h`);
- EBS gp3 de 20 GB: aproximadamente USD 1,60/mês;
- um IPv4 público por 730 h: aproximadamente USD 3,65/mês quando não coberto;
- subtotal fixo aproximado: **USD 12,84/mês**, antes de S3, API Gateway, logs e transferência;
- `t3.small` contínua eleva esse subtotal para aproximadamente **USD 20,43/mês**.

Rodar a `t3.micro` por 160 h/mês reduz compute e IPv4 variável, mas EBS e qualquer endereço reservado continuam sujeitos a cobrança. O resultado não é custo zero garantido. O orçamento atual de USD 5 alertará cedo em uma conta sem benefício ativo, o que é desejável.

## 7. Plano de alterações

Nenhum item abaixo foi executado. Cada fase termina em `terraform plan` revisado, sem destruição ou substituição inesperada.

### Fase 0 — Billing gate e inventário

Entregáveis:

- registrar elegibilidade e créditos conforme a seção 6.1;
- usar a conta/projeto de origem apenas como referência de arquitetura e consumo, sem alterar seus recursos;
- obter inventário da nova conta e confirmar que não existem colisões com nomes globais, quotas ou recursos anteriores;
- criar state próprio da conta de destino; não reutilizar o state da aplicação de origem;
- registrar quais componentes do Terraform e do frontend CaptaGov serão copiados sem mudança inicial e quais serão adaptados para o VetOrthoPlan;
- identificar secrets/chaves que possam ter aparecido em state ou log e planejar rotação;
- gerar estimativa no AWS Pricing Calculator para cenário contínuo e cenário 160 h/mês;
- aprovar teto mensal e owner dos alertas.

Gate de saída:

- custo sem créditos conhecido;
- nenhum recurso órfão desconhecido na conta de destino;
- stack `test` nova e isolada da aplicação de origem.

### Fase 1 — Higiene e state

Alterações planejadas:

- adicionar `.gitignore` para `.terraform/`, `*.tfstate*`, `*.tfplan`, logs, `.env`, chaves privadas e artefatos locais; versionar `.terraform.lock.hcl` para reproduzir as versões dos providers;
- remover state/log/chave do versionamento, caso já tenham sido publicados, sem apagar a única cópia antes de backup seguro;
- rotacionar credenciais e chaves potencialmente expostas;
- criar backend remoto S3 criptografado, com versionamento e lock nativo do backend S3 suportado pela versão adotada; bootstrap separado;
- adicionar `target_account_id` e proteção no provider para recusar execução fora da conta de destino;
- fixar providers AWS e Null no `required_providers` e versionar o lockfile;
- adicionar `default_tags` e convenção `${project}-${environment}-${account_id}-${region}`;
- separar configuração de `test` de futuros ambientes.

Gate de saída:

- `terraform init -backend=false`, `fmt -check`, `validate` e lint passam em CI;
- state não contém secrets novos inseridos como valores Terraform;
- backend remoto tem recuperação documentada.

### Fase 2 — Rede e acesso seguro

Alterações planejadas:

- associar explicitamente EC2 e security groups à VPC/subnet correta;
- reduzir o ambiente econômico para uma subnet pública em uma AZ, mantendo CIDRs reservados para expansão;
- remover ingress total e a variável `test_environment_open_access`;
- não criar regras para 5432, 6379, 2375/2376 ou portas internas das aplicações;
- habilitar IMDSv2 obrigatório, EBS criptografado e limites seguros de metadata hops;
- instalar/configurar SSM Agent e permissões mínimas de Session Manager; remover SSH e o key pair depois de validar o acesso SSM;
- publicar somente 443 no reverse proxy, conforme a opção de entrada aprovada;
- documentar que NAT Gateway, ALB/NLB e subnets privadas ficam adiados para piloto/produção.

Gate de saída:

- scan externo encontra somente a porta deliberadamente publicada;
- administração funciona por SSM sem chave privada;
- EC2 aparece na VPC criada pelo Terraform;
- acesso direto a PostgreSQL/Redis falha a partir da Internet.

### Fase 3 — Compute e deploy reproduzível

Alterações planejadas:

- parametrizar `instance_type`, arquitetura e tamanho do EBS com validações/allowlist;
- começar com `t3.micro` apenas se elegível e se o teste de memória passar;
- definir limites e reservations de CPU/memória por contêiner;
- criar Compose de ambiente contendo reverse proxy, frontend/BFF, auth API, backend clínico, worker, PostgreSQL e Redis opcional;
- databases e usuários separados para autenticação e clínica;
- retirar `timestamp()` e deploy por `remote-exec` do fluxo normal;
- buildar imagens em CI, publicar tags imutáveis e implantar por digest usando SSM ou mecanismo equivalente;
- manter migrations como job explícito e único antes da aplicação;
- implementar health checks `/health/live` e `/health/ready` por serviço;
- criar rollback para o digest anterior.

Gate de saída:

- reboot da EC2 restaura todos os contêineres;
- deploy repetido do mesmo digest é idempotente;
- rollback e migrations são testados;
- sem swap excessivo/OOM em upload, ingestão e geração de relatório concorrentes;
- caso `t3.micro` falhe, escalar conscientemente e atualizar a estimativa/orçamento.

### Fase 4 — Storage clínico

Alterações planejadas:

- criar bucket separado com nome global derivado de conta/região/ambiente;
- habilitar Block Public Access, BucketOwnerEnforced e criptografia padrão do serviço;
- modelar prefixos `quarantine/`, `originals/`, `derived/`, `catalog/` e `reports/`;
- aplicar least privilege por prefixo e negar transporte sem TLS;
- habilitar versionamento onde necessário;
- definir lifecycle curto para quarentena, uploads incompletos, derivados e versões antigas de teste;
- impedir deleção acidental de originais pela API comum; separar permissão de limpeza;
- implementar URLs pré-assinadas curtas com tamanho, content type e checksum validados pela aplicação;
- criar métricas/alarme de tamanho e requests.

Gate de saída:

- bucket de avatares não é usado pelo domínio clínico;
- upload direto, promoção da quarentena e download autorizado funcionam;
- teste cross-tenant e tentativa de acesso público falham;
- nenhuma URL pré-assinada, imagem ou metadata clínica aparece em logs.

### Fase 5 — Fila e worker

Alterações planejadas:

- criar SQS Standard e DLQ com SSE gerenciada pelo serviço;
- configurar visibility timeout maior que o timeout máximo do job, long polling, retenção e redrive;
- restringir `SendMessage`, `ReceiveMessage`, `DeleteMessage` e redrive às roles necessárias;
- usar payload pequeno com `job_id`, `tenant_id` pseudonimizado quando necessário e object key;
- tornar consumidores idempotentes e persistir estado do job;
- alarmar `ApproximateAgeOfOldestMessage`, profundidade e mensagens na DLQ;
- limitar concorrência do worker para não derrubar a EC2.

Gate de saída:

- retry não duplica revisão, derivado ou relatório;
- mensagem venenosa chega à DLQ;
- restart do worker não perde jobs;
- volume de requests SQS aparece no controle de custo.

### Fase 6 — Identidade, rotas e secrets

Alterações planejadas:

- fechar AUTH-01 antes de publicar rota clínica;
- configurar audience exclusiva `vetorthoplan-api`, tenant ativo e scopes;
- ativar JWT authorizer no gateway quando compatível, mantendo validação local no backend;
- separar rotas públicas de login/JWKS/health das rotas autenticadas;
- restringir ou desabilitar Swagger público;
- tornar CORS específico por ambiente e incluir headers realmente necessários (`If-Match`, `Idempotency-Key`, checksum e tracing);
- armazenar segredos em Parameter Store Standard `SecureString`, com IAM por path;
- buscar segredos em bootstrap/runtime e não renderizá-los no Terraform, user data, logs ou outputs;
- definir rotação manual documentada para o ambiente de teste.

Gate de saída:

- matriz de tokens inválidos e acesso cross-tenant passa;
- nenhuma rota chamada de protegida funciona sem token válido;
- state/plan não revela valores secretos;
- navegador não recebe tokens de backend.

### Fase 7 — Observabilidade e controle financeiro

Alterações planejadas:

- enviar logs estruturados ao CloudWatch com retenção de 7–14 dias;
- redigir Authorization, cookies, URLs assinadas, notas clínicas e pixels;
- manter métricas básicas gratuitas da EC2 e evitar detailed monitoring sem decisão de custo;
- instalar agente somente para memória/disco e limitar custom metrics;
- criar alarmes de status EC2, CPU sustentada, disco, 5xx, DLQ e idade da fila;
- adicionar alertas de Free Tier e Cost Anomaly Detection;
- manter budget sem ações, com limites absolutos baixos e forecast;
- preparar runbook para parar EC2 e destruir recursos descartáveis, lembrando que EBS/S3/EIP podem continuar cobrando;
- usar tags de custo em todos os recursos.

Gate de saída:

- uma falha simulada produz log correlacionado e alarme;
- orçamento e alertas têm destinatário confirmado;
- dashboard mostra compute, storage, requests e fila;
- runbook de desligamento foi testado sem perda de state.

### Fase 8 — Testes, promoção e decisão sobre RDS/Fargate

Executar na topologia econômica:

- vertical slice `login → tenant → BFF → API clínica → PostgreSQL → resposta tipada`;
- upload pré-assinado e ingestão `S3 → SQS → worker → derived`;
- autosave com conflito otimista;
- geração de relatório;
- isolamento entre tenants;
- restart, retry, DLQ, restore e rollback;
- carga representativa com corpus sintético.

Depois dos resultados, decidir por ADR:

- manter EC2 no restante da homologação;
- mover apenas PostgreSQL para RDS Single-AZ para testar operação gerenciada;
- mover API/worker para ECS Fargate para validar o runtime de produção;
- introduzir rede privada, load balancer/VPC Link, NAT/endpoints e KMS CMK somente no piloto endurecido.

Gate de saída:

- diferenças entre teste e produção registradas;
- estimativa pós-Free Tier aprovada;
- nenhum dado real entra enquanto os controles de piloto não forem implantados.

## 8. Estrutura Terraform alvo

Uma organização possível, a confirmar em ADR:

```text
vetorthoplan_terraform/
├── bootstrap/
│   └── state-backend/
├── environments/
│   └── test/
│       ├── backend.tf
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── terraform.tfvars.example
├── modules/
│   ├── network-test/
│   ├── compute-compose/
│   ├── api-gateway/
│   ├── clinical-storage/
│   ├── clinical-queue/
│   ├── identity-email/
│   ├── observability/
│   └── cost-controls/
├── policies/
├── scripts/
└── docs/
```

Como a implantação será feita em outra conta, a stack VetOrthoPlan deve nascer com state próprio e não deve importar nem mover recursos da conta de origem. `moved` blocks ou `terraform state mv` serão necessários apenas se a estrutura do código for reorganizada depois que recursos já existirem na nova conta. Nesse caso, antes de cada migração interna:

1. backup seguro do state;
2. `plan` sem refresh destrutivo inesperado;
3. lista de recursos que serão importados/movidos;
4. aprovação do plano;
5. aplicação em lotes pequenos;
6. smoke test e plano seguinte vazio.

## 9. Critérios de aceite do ambiente econômico

- [ ] elegibilidade/créditos e custo sem desconto documentados;
- [ ] nenhuma regra ingress `0.0.0.0/0` além da porta pública explicitamente aprovada;
- [ ] PostgreSQL, Redis, Docker e SSH não são públicos;
- [ ] acesso administrativo somente por SSM ou método aprovado equivalente;
- [ ] state remoto, criptografado, versionado e bloqueado;
- [ ] providers e imagens fixados; deploy por digest;
- [ ] secrets ausentes de state, plan, user data e logs;
- [ ] banco, usuário, bucket e filas do domínio clínico separados da autenticação;
- [ ] bucket privado, upload pré-assinado, checksum, quarentena e lifecycle testados;
- [ ] SQS/DLQ e idempotência testadas;
- [ ] audience, tenant e scopes validados ponta a ponta;
- [ ] logs redigidos, com retenção curta, alarmes e correlação;
- [ ] budget, Free Tier alerts e runbook de desligamento ativos;
- [ ] teste de memória/carga define se `t3.micro` é suficiente;
- [ ] somente dados sintéticos/desidentificados;
- [ ] limitações em relação à produção aceitas por escrito.

## 10. Riscos residuais da opção econômica

| Risco | Tratamento no teste | Condição para sair do teste |
|---|---|---|
| falha única derruba todos os serviços | aceitar e testar restart | múltiplas tarefas/AZs no piloto |
| contenção de CPU/RAM/I/O | limites por contêiner e carga controlada | separar worker/API e aumentar capacidade |
| banco no mesmo host | backups sintéticos e restore testado | RDS privado antes de dados reais |
| origem do API Gateway é pública | proxy/TLS/credencial de origem, dados não sensíveis | integração privada no piloto |
| sem CMK própria | criptografia padrão do serviço | CMK/policies aprovadas pelo threat model |
| secrets sem rotação automática | rotação manual e curta vida do ambiente | Secrets Manager/rotação no piloto |
| sem WAF/CDN | rate limit e acesso controlado | edge security antes de exposição pública ampla |
| custo muda com fim dos créditos | alertas, tags e shutdown | orçamento operacional recorrente aprovado |

## 11. Itens fora de escopo para o primeiro ambiente

- alta disponibilidade e SLA de 99,9%;
- Multi-AZ, autoscaling e disaster recovery regional;
- uso de radiografias ou dados pessoais reais;
- CloudFront/WAF completo;
- PACS/DICOMweb;
- ECS/EKS/Fargate contínuo;
- NAT Gateway;
- banco compartilhado entre serviços;
- performance de produção;
- conformidade de piloto apenas por equivalência com este laboratório.

## 12. Decisões registradas e validações pendentes

Decisões registradas:

1. será usada a mesma arquitetura já executada pelo projeto de origem;
2. a implantação será feita em outra conta AWS, com state e recursos independentes;
3. Terraform e frontend CaptaGov serão replicados antes da adaptação progressiva ao VetOrthoPlan;
4. o objetivo financeiro do ambiente inicial é permanecer dentro das franquias/créditos gratuitos disponíveis.

Validações ainda necessárias:

1. a conta de destino é efetivamente elegível, quais créditos/franquias estão ativos e quando expiram?
2. o API Gateway precisa fazer parte de todos os testes ou somente de um gate de integração?
3. existe domínio de teste sob controle do time para TLS na origem?
4. as imagens Docker do frontend, auth e backend clínico suportarão ARM64, permitindo avaliar Graviton?
5. qual limite mensal real será aceito quando o Free Tier/crédito acabar?
6. em que fase será obrigatório validar RDS e Fargate antes do piloto?

## 13. Referências oficiais de custo e elegibilidade

Consultadas em 2026-09-15:

- AWS Free Tier FAQ — créditos, prazo do Free Plan, contas existentes e Organizations: <https://aws.amazon.com/free/free-tier-faqs/>
- EC2 Free Tier antes/depois de 15 de julho de 2025: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html>
- preços e franquia do EBS: <https://aws.amazon.com/ebs/pricing/>
- preços do S3: <https://aws.amazon.com/s3/pricing/>
- preços do API Gateway: <https://aws.amazon.com/api-gateway/pricing/>
- preços e franquia do SQS: <https://aws.amazon.com/sqs/pricing/>
- preços e franquia do CloudWatch: <https://aws.amazon.com/cloudwatch/pricing/>
- Parameter Store Standard sem cobrança adicional: <https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html>
- preços do Fargate: <https://aws.amazon.com/fargate/pricing/>
- Free Tier do RDS e limitações: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html#Welcome.FreeTier>
- preços de IPv4/NAT/VPC: <https://aws.amazon.com/vpc/pricing/>
- preços do Secrets Manager: <https://aws.amazon.com/secrets-manager/pricing/>
- tipos e custos de chaves KMS: <https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html>
- AWS Budgets: <https://aws.amazon.com/aws-cost-management/aws-budgets/faqs/>
- preços e franquia do Lambda: <https://aws.amazon.com/lambda/pricing/>

## 14. Parecer final

O `vetorthoplan_terraform` é uma base intencionalmente derivada do CaptaGov, cuja arquitetura já está operacional em outro projeto. **A recomendação é replicar essa mesma topologia em uma conta AWS independente**, com state próprio, e adaptar gradualmente aplicações, nomes e recursos clínicos. As referências legadas são esperadas nesta etapa. Antes de expor a réplica, continuam necessários hardening de rede e secrets, vínculo explícito à VPC, separação dos dados clínicos e correção do deploy mutável.

Para testes, a arquitetura existente — uma EC2 única com isolamento lógico, API Gateway e S3 — oferece a melhor relação entre fidelidade, risco de mudança e custo. SQS/DLQ podem ser acrescentados quando começar o processamento assíncrono clínico, sem substituir a topologia. A expectativa de gratuidade é plausível apenas se a conta de destino for elegível e o consumo permanecer dentro dos limites verificados. Essa solução não substitui a topologia privada e gerenciada prevista para piloto/produção.
