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
| Checklist de qualidade da radiografia | Pendente | Lateral verdadeira, alinhamento, sobreposição, campo e centralização precisam virar campos/regras. |
| Tolerâncias de erro e critérios de aceitação | Pendente | Dependem de protocolo do parceiro clínico. |
| Auditoria de revisão e aprovação clínica | Pendente | Registrar ator, data, método e versão do protocolo. |
| Medidas anatômicas adicionais homologadas | Pendente | Definir marcos, fórmulas e unidades com o parceiro. |
| Consulta à tabela de rotação TPLO | Pendente | Deve ser referência configurável; não gerar recomendação automática sem aprovação. |

## Planejamento cirúrgico e entrega

| Funcionalidade | Estado | Observação |
|---|---|---|
| Parâmetros clínicos de rotação e alvo de slope | Pendente | Depende do protocolo e da tabela adotados. |
| Máscara editável e transformação visual do fragmento no frontend | Parcial | Backend persiste contorno e transformação; integração visual pendente. |
| Implantes e catálogo versionado | Pendente | Assets e regras de escala ainda precisam de contrato. |
| Finalização imutável e checklist de completude | Pendente | Necessário antes de uso operacional. |
| Relatório PNG/PDF versionado | Pendente | Depende da revisão final e catálogo. |

## Próximas prioridades do backend

1. Transformar o checklist de qualidade radiográfica em campos e regras persistidas.
2. Implementar auditoria de revisão clínica.
3. Definir e validar, com o parceiro, tolerâncias e medidas anatômicas adicionais.
4. Preparar a consulta configurável à tabela de rotação TPLO.
5. Implementar finalização imutável e geração de relatório.

