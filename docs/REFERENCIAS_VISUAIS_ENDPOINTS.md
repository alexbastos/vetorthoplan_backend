# Referências visuais por endpoint e funcionalidade

Este índice liga os contratos do backend às pranchas disponíveis para orientar uma implementação frontend futura. As imagens são referências conceituais; não substituem o OpenAPI nem significam que cada tela ou regra clínica esteja implementada.

| Endpoint / funcionalidade | Referência visual | Observação sobre o backend |
|---|---|---|
| `GET /health/live` | Não se aplica | Endpoint operacional, sem interface de usuário. |
| `POST /api/v1/cases` | [criar-caso-v1.png](frontend/criar-caso-v1.png) | Cria caso no estado `DRAFT`. |
| `GET /api/v1/cases` e `GET /api/v1/cases/{case_id}` | [casos-listagem-detalhe-v2.png](frontend/casos-listagem-detalhe-v2.png) | Lista, busca, filtra, pagina e consulta casos. |
| `POST /api/v1/cases/{case_id}/image-uploads` | [upload-radiografia-v1.png](frontend/upload-radiografia-v1.png) | Cria sessão e retorna formulário pré-assinado para object storage. |
| `POST /api/v1/image-uploads/{upload_id}/complete` | [confirmacao-upload-v1.png](frontend/confirmacao-upload-v1.png) | Confere o objeto e enfileira ingestão. |
| `GET /api/v1/jobs/{job_id}` | [processamento-imagem-v1.png](frontend/processamento-imagem-v1.png) | Consulta estados do worker e da ingestão. |
| `GET /api/v1/cases/{case_id}/images` e `GET /api/v1/images/{image_id}` | [processamento-imagem-v1.png](frontend/processamento-imagem-v1.png) | Lista e consulta metadados e estados das imagens. |
| `GET /api/v1/images/{image_id}/preview` | [processamento-imagem-v1.png](frontend/processamento-imagem-v1.png) | Solicita URL temporária da prévia PNG privada. |
| `GET /api/v1/images/{image_id}/plan` e `PUT /api/v1/images/{image_id}/plan` | [plano-geometrico-v1.svg](frontend/plano-geometrico-v1.svg) | A API persiste um documento geométrico versionado e detecta conflito por revisão; não implementa ainda o fluxo clínico TPLO completo. |
| Worker de ingestão de imagens | [processamento-imagem-v1.png](frontend/processamento-imagem-v1.png) | Representa estados de processamento, não a instalação operacional do serviço. |

As imagens específicas por etapa também estão listadas no [guia visual do fluxo TPLO](GUIA_FRONTEND_FLUXO_TPLO.md). O artefato `fluxo-frontend-tplo-v2.png` apresenta a jornada completa e marca explicitamente as etapas planejadas.
