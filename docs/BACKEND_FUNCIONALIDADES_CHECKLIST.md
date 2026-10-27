# Checklist de funcionalidades do backend

Documento de acompanhamento do recorte inicial do VetOrthoPlan. Estados:

- **Concluído**: implementado, documentado e incluído em commit.
- **Parcial**: existe contrato ou base técnica, mas falta integração, validação ou homologação.
- **Pendente**: ainda precisa ser implementado.

## Upload e imagens

| Funcionalidade | Estado | Observação |
|---|---|---|
| Sessão de upload pré-assinada para DICOM, PNG e JPEG | Concluído | Fluxo direto para object storage. |
| Confirmação, checksum SHA-256 e ingestão assíncrona | Concluído | Conteúdo é conferido nos bytes recebidos. |
| CORS do bucket para frontend local e produção | Concluído | Configuração de infraestrutura aplicada conforme ambiente. |
| Idempotência por tenant, usuário e `Idempotency-Key` | Concluído | Replay do mesmo payload recupera a sessão original. |
| Proteção contra duplicata por SHA-256 no mesmo caso | Concluído | `409 IMAGE_UPLOAD_DUPLICATE`; nomes diferentes não liberam duplicata. |
| Reserva atômica do conteúdo em concorrência | Concluído | Criação serializada pelo lock transacional do caso e busca indexada. Migration `20261024_0016`. |
| Liberação da reserva após cancelamento, expiração sem confirmação ou exclusão | Concluído | Imagem confirmada mantém a proteção até exclusão efetiva. |
| Listagem e consulta de estados de imagens | Concluído | Inclui estado de processamento e prévia quando disponível. |

## Plano geométrico e calibração

| Funcionalidade | Estado | Observação |
|---|---|---|
| Plano versionado com controle de revisão | Concluído | Conflito retorna `409 PLAN_REVISION_CONFLICT`. |
| Calibração manual por linha ou círculo | Concluído | Retorna `mm_per_pixel` e `calibration_id`. |
| Medidas de linha, círculo e ângulo | Concluído | Valores derivados da imagem original. |
| Simulação geométrica de osteotomia TPLO | Parcial | Centro, raio, contorno e matriz afim implementados; falta validação clínica. |
| OpenAPI e documentação do plano | Concluído | Contratos exportados em `docs/openapi.json` e `openapi/openapi.json`. |

## Validação clínica TPLO

| Funcionalidade | Estado | Observação |
|---|---|---|
| Checklist de validação clínica e estados de revisão | Parcial | Estados e pré-condições de aprovação implementados. |
| Registro de marcos anatômicos do TPA | Concluído | Método explícito e versionado. |
| Cálculo geométrico do TPA | Parcial | Método `MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1`; resultado ainda não homologado. |
| Checklist de qualidade da radiografia | Parcial | Campos persistidos no plano e regra de elegibilidade implementados; critérios devem ser confirmados com o parceiro clínico. |
| Tolerâncias de erro e critérios de aceitação | Parcial | Comparação versionada por erro absoluto implementada; limites e referência precisam de protocolo homologado pelo parceiro. |
| Auditoria de revisão e aprovação clínica | Parcial | Registra ator, data, decisão, método de medida, calibração e versão técnica; versão clínica precisa de homologação. |
| Medidas anatômicas adicionais homologadas | Parcial | Distâncias e ângulos entre marcos configuráveis implementados; marcos, fórmulas e unidades precisam de definição clínica homologada. |
| Consulta à tabela de rotação TPLO | Concluído | Migration `20261026_0018` persiste a [tabela BioMedtrix/VOI 1-15-18](https://biomedtrix.com/tplo-rotation-guide-chart-1-15-18-2/), fonte, versão, hash e 360 combinações; valida grade e ponto publicado antes de ativar. |

## Planejamento cirúrgico e entrega

| Funcionalidade | Estado | Observação |
|---|---|---|
| Parâmetros clínicos de rotação e alvo de slope | Pendente | Depende do protocolo e da tabela adotados. |
| Máscara editável e transformação visual do fragmento no frontend | Parcial | Backend persiste contorno e transformação; integração visual pendente. |
| Implantes e catálogo versionado | Pendente | Assets e regras de escala ainda precisam de contrato. |
| Finalização imutável e checklist de completude | Parcial | Backend cria snapshot imutável e bloqueia edições; falta integrar a ação no frontend. |
| Relatório PNG/PDF versionado | Parcial | PNG e PDF gerados e armazenados por versão; fluxo de download no frontend pendente. |

## Próximas prioridades do backend

1. Homologar com o parceiro o protocolo de tolerâncias e medidas anatômicas configuráveis.
2. Homologar os parâmetros clínicos de rotação e alvo de slope além da tabela de referência.
3. Definir o contrato do catálogo de implantes versionado, incluindo assets e escala.

### Checklist de qualidade radiográfica implementado

O documento do plano aceita `radiographic_quality` com os campos `true_lateral`,
`femoral_condyles_superimposed`, `stifle_and_tarsus_included`, `tibial_axis_centered` e
`tibial_plateau_visible`. Cada critério usa `PASS`, `FAIL` ou `NOT_ASSESSED`; `notes` é opcional.
Uma imagem só pode ser marcada `ELIGIBLE` quando todos os cinco critérios estiverem em `PASS`.
Os nomes e a regra são uma base técnica e precisam de confirmação do parceiro clínico antes de
serem tratados como protocolo clínico homologado.

### Auditoria de revisão clínica implementada

Ao entrar em `APPROVED` ou `REJECTED`, o backend acrescenta ao plano um evento com ator autenticado,
data/hora UTC, decisão, método anatômico, identificador da calibração e versão técnica
`TPLO_CLINICAL_REVIEW_V1`. Eventos anteriores vêm da versão persistida do plano; entradas de auditoria
enviadas pelo cliente são substituídas. Essa versão identifica o formato técnico do registro, não um
protocolo clínico homologado.

### Medidas anatômicas e tolerâncias configuráveis

O ambiente pode definir `TPLO_CLINICAL_PROTOCOL_JSON` com versão, fonte, tolerância absoluta de TPA e
medidas extras. Cada medida extra é `DISTANCE` (dois marcos, em mm) ou `ANGLE` (três marcos, em graus),
com erro absoluto máximo em relação ao valor de referência enviado na revisão. O backend persiste os
marcos e valores de referência, recalcula os resultados em cada gravação e exige aceitação `PASS` para
cada medida listada em `required_measurements` antes de `APPROVED`.

O protocolo é consultável em `GET /api/v1/tplo/clinical-protocol`. Sem configuração, medidas extras
não são calculadas e a tolerância de TPA fica `NOT_CONFIGURED`. Versão, fonte, marcos, unidades e
limites devem ser fornecidos e homologados pelo parceiro clínico antes de uso.

### Consulta configurável à tabela de rotação TPLO

`GET /api/v1/tplo/rotation-table` retorna a versão BioMedtrix/VOI 1-15-18 instalada e validada pela
migration `20261026_0018`, com fonte, URL do gráfico, slope-alvo de 5 graus, SHA-256 e 360
combinações exatas (TPA de 10 a 45 graus; lâminas de 8 a 33 mm). `tpa_degrees` e
`blade_diameter_mm` são filtros opcionais por correspondência numérica exata. Não há interpolação nem
recomendação automática. Uma tabela homologada posterior pode substituir a ativa pelas variáveis
`TPLO_ROTATION_TABLE_VERSION`, `TPLO_ROTATION_TABLE_SOURCE` e `TPLO_ROTATION_TABLE_JSON`, preenchidas
em conjunto e validadas na inicialização.

### Finalização imutável e relatórios

`POST /api/v1/images/{image_id}/plan/finalize` recebe `base_revision` e exige imagem elegível,
qualidade radiográfica aprovada, calibração calculada, checklist clínico completo e revisão `APPROVED`
com as medidas obrigatórias aceitas. O backend grava o snapshot com SHA-256, usuário, horário, versão
e versão do template. Gatilhos no banco bloqueiam atualizações posteriores ao plano e ao snapshot.
Repetir a finalização com a mesma revisão retorna a versão já criada.

O relatório PNG/PDF inclui imagem com marcações, resumo das medidas e auditoria clínica. O endpoint
`GET /api/v1/images/{image_id}/plan/finalization` retorna o snapshot e links temporários para os
arquivos, com seus hashes. A migration `20261026_0017_finalized_image_plans` cria o armazenamento
persistente dos snapshots e metadados dos relatórios.

