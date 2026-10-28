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
| Medidas de linha, círculo e ângulo | Concluído | Valores derivados da imagem original; linha também representa eixos anatômicos nomeados. |
| Pré-validação técnica do plano TPLO | Implementado | `POST /api/v1/images/{image_id}/plan/validate` verifica revisão, imagem, calibração, qualidade, marcos/TPA, osteotomia, fragmento simulado, correção tabelada e referências de implantes sem gravar alterações. Retorna `READY_FOR_CLINICAL_REVIEW` com aviso de homologação pendente ou `INCOMPLETE` com bloqueios. |
| Simulação geométrica de osteotomia TPLO | Parcial | Centro, raio, contorno e matriz afim implementados; falta validação clínica. |
| OpenAPI e documentação do plano | Concluído | Contratos exportados em `docs/openapi.json` e `openapi/openapi.json`. |

### Pré-validação técnica TPLO

`POST /api/v1/images/{image_id}/plan/validate` avalia a revisão já persistida e não grava alterações. O corpo pode trazer `base_revision`; se informada e diferente da versão atual, a resposta inclui `PLAN_REVISION_CONFLICT`. O estado `READY_FOR_CLINICAL_REVIEW` significa que as verificações técnicas passaram e o plano pode ser apresentado ao veterinário. A resposta sempre carrega o aviso `CLINICAL_VALIDATION_PENDING` enquanto os critérios não forem homologados.

Os bloqueios incluem radiografia não pronta, dimensões ou calibração ausentes, qualidade/elegibilidade incompletas, marcos ou TPA não calculados, falta de geometria/contorno simulado da osteotomia, correção tabelada indisponível quando há diâmetro de lâmina e referência de implante inválida. A ausência de seleção de lâmina gera aviso e deixa a verificação da tabela como `NOT_APPLICABLE`.

## Validação clínica TPLO

| Funcionalidade | Estado | Observação |
|---|---|---|
| Checklist de validação clínica e estados de revisão | Concluído no backend | `PUT` preserva o plano completo e `POST /images/{image_id}/plan/review` executa as transições `READY_FOR_REVIEW`/`APPROVED`/`REJECTED` sem aceitar alteração de geometria na decisão. Homologação clínica permanece pendente. |
| Registro de marcos anatômicos do TPA | Concluído | Método explícito e versionado. |
| Cálculo geométrico do TPA | Parcial | Método `MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1`; comparação por tolerância configurada e retorno na API. Homologação clínica com casos de referência continua pendente. |
| Checklist de qualidade da radiografia | Parcial | Campos persistidos no plano e regra de elegibilidade implementados; critérios devem ser confirmados com o parceiro clínico. |
| Tolerâncias de erro e critérios de aceitação | Parcial | Comparação versionada por erro absoluto implementada; limites e referência precisam de protocolo homologado pelo parceiro. |
| Auditoria de revisão e aprovação clínica | Parcial | Registra ator, data, decisão, método de medida, calibração e versão técnica; versão clínica precisa de homologação. |
| Medidas anatômicas adicionais homologadas | Parcial | Distâncias e ângulos entre marcos configuráveis implementados; marcos, fórmulas e unidades precisam de definição clínica homologada. |
| Consulta à tabela de rotação TPLO | Concluído | Migration `20261026_0018` persiste a [tabela BioMedtrix/VOI 1-15-18](https://biomedtrix.com/tplo-rotation-guide-chart-1-15-18-2/), fonte, versão, hash e 360 combinações; valida grade e ponto publicado antes de ativar. |

## Planejamento cirúrgico e entrega

| Funcionalidade | Estado | Observação |
|---|---|---|
| Parâmetros clínicos de rotação e alvo de slope | Parcial | O backend aplica correspondência exata da tabela versionada no `PUT`/`GET` do plano e devolve rotação, alvo, versão e hash. Não interpola. Alvos/regras e uso clínico ainda precisam de homologação. |
| Máscara editável e transformação visual do fragmento no frontend | Parcial | Backend persiste contorno e transformação; integração visual pendente. |
| Importação DWG e catálogo versionado de desenhos | Parcial | Backend preserva original, calcula SHA-256, controla versão/revisão e aceita derivados SVG/PNG de wrapper ODA. Conversor licenciado ainda não configurado; arquivos aguardam conversão. Não representa molde 3D nem certifica compatibilidade clínica. |
| Catálogo versionado e revisão de ativos de implantes | Concluído no backend | Importação preserva originais opacos, admite conversor plugável e publica apenas ativos aprovados. Variantes e vistas são metadados versionados do item. Ver [IMPLANT_CATALOG.md](IMPLANT_CATALOG.md). |
| Posicionamento de implantes no plano | Concluído no backend | Objeto `IMPLANT` vincula item aprovado do mesmo tenant a posição normalizada, rotação, escala, opacidade, variante e vista; matriz afim é recalculada pelo backend e incluída no snapshot/relatório. |
| Renderização interativa do ativo no viewer | Pendente no frontend | O contrato e a transformação server-side estão prontos; integração visual pertence ao frontend. |
| Finalização imutável e checklist de completude | Concluído no backend | `POST /images/{image_id}/plan/finalize` cria o snapshot imutável, bloqueia edições posteriores e exige TPA aceito e correção tabelada quando uma lâmina é selecionada. |
| Relatório PNG/PDF versionado | Concluído no backend | Gera PNG/PDF `TPLO_FINAL_REPORT_V2`, registra hashes, snapshot, correção, tabela/hash, auditoria e emite links temporários; o frontend apenas consome o contrato. |

## Próximas funcionalidades a implementar

1. Finalizar o frontend do editor TPLO: canvas com zoom/pan, pontos anatômicos arrastáveis, linhas/ângulos, calibração e estado de qualidade radiográfica.
2. Integrar no frontend a revisão clínica: `DRAFT` -> `READY_FOR_REVIEW` -> `APPROVED`/`REJECTED`, com bloqueios e auditoria visível.
3. Integrar a simulação da osteotomia e os parâmetros de correção, exibindo a geometria calculada pelo backend e permitindo revisão manual antes da finalização.
4. Integrar a finalização imutável e o download dos relatórios PNG/PDF.
5. Integrar frontend/BFF ao contrato autenticado do backend; cobertura backend inicial para `401/403`, conflitos `409`, imagem inelegível, plano finalizado, referências de implantes e escopo de idempotência está em `tests/api/test_authenticated_contract.py`, `tests/api/test_image_plans.py` e `tests/unit/application/test_create_image_upload.py`.
6. Homologar com o parceiro veterinário: posicionamento radiográfico, marcos anatômicos, método do TPA, tolerâncias, slope-alvo e tabela de rotação.
7. Obter licença ODA, instalar o wrapper de conversão e integrar a interface administrativa ao fluxo DWG → revisão manual.
8. Definir o formato canônico editável e contrato separado para moldes 3D antes de habilitar posicionamento/simulação clínica.

## Quando os moldes serão necessários

Os moldes não são pré-requisito para o fluxo atual de planejamento geométrico TPLO. O backend calcula e persiste calibração, marcos, TPA, medidas adicionais, parâmetros de correção, tabela de rotação, simulação geométrica, posicionamento referenciado de implantes e snapshot final.

Os DWGs New Vet podem alimentar o catálogo de desenhos 2D após conversão ODA e revisão, mas não fornecem por si só molde 3D para sobrepor à osteotomia. A simulação com geometria 3D requer contrato separado que defina formato (`STL`, `OBJ` ou outro), unidade, sistema de coordenadas, lateridade, versão, compatibilidade, origem/licença, checksum e regras de visualização.

Ordem recomendada: homologar medidas e correção; integrar a simulação sem molde; instalar o conversor ODA licenciado e revisar desenhos 2D; definir catálogo/contrato 3D; receber um conjunto pequeno de moldes oficiais; validar escala e orientação com o parceiro; ampliar o catálogo.

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

Ao salvar o plano, `tplo.blade_diameter_mm` seleciona a linha da tabela usando o TPA geométrico calculado. O backend grava em `tplo_correction` o alvo de slope, rotação em mm, versão, fonte e hash da tabela. A busca exige correspondência numérica exata de TPA e diâmetro; ausência de linha, falta de alvo ou conflito entre o alvo informado e o alvo da tabela deixa a correção sem aceitação. Para tabelas configuradas por ambiente, `TPLO_ROTATION_TABLE_TARGET_SLOPE_DEGREES` declara o alvo associado à tabela; também pode ser informado em `tplo.target_slope_degrees`. `TPLO_CORRECTION` pode ser marcada como medida obrigatória para aprovação quando houver lâmina selecionada.

O alvo/rotação retornados são referência tabelada para revisão manual. `clinically_validated` permanece falso; a existência da tabela e a comparação computacional não substituem homologação clínica.

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

