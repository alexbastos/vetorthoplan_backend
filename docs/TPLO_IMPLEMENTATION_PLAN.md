# Plano de implementação TPLO

## Etapas

1. **Fundação do planejamento** — contrato versionado, lateralidade e entradas clínicas persistidas junto ao plano.
2. **Validação da radiografia** — qualidade, projeção, lateralidade e critérios de elegibilidade.
3. **Medições assistidas** — pontos anatômicos, ângulo do platô e parâmetros de correção.
4. **Revisão clínica** — ajustes manuais, aprovação, rejeição e auditoria das versões.
5. **Relatório cirúrgico** — imagem anotada, PDF e exportação dos parâmetros aprovados.
6. **Validação clínica e operação** — casos de referência, métricas, reprocessamento e observabilidade.

## Etapa 1 — entregue

O documento de planejamento agora aceita `tplo` com lateralidade (`LEFT` ou `RIGHT`), ângulo atual, ângulo alvo e observações. Os ângulos são opcionais nesta etapa porque ainda não são calculados automaticamente. O plano continua versionado e protegido por conflito de revisão.

Essa etapa não interpreta a radiografia nem recomenda valores clínicos; essas capacidades ficam para as etapas 2 e 3.
