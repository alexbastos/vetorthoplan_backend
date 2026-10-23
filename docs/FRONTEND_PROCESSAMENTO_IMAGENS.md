# Frontend — processamento e consulta de imagens

> Escopo: primeiro recorte do IMG-02.  
> Contrato local: OpenAPI `0.9.0`; `cecia.ufsj.edu.br` ainda publica `0.8.0`.

## Recuperação de estado e erros (0.9.0)

Após restaurar as imagens de um caso, consulte `GET /api/v1/images/{image_id}/job`. A resposta é `{ "job": null }` até a confirmação criar o job e, depois, contém o mesmo `job_id` e estado (`QUEUED`, `PROCESSING`, `SUCCEEDED`, `REJECTED` ou `FAILED`). `REJECTED` significa que o arquivo não passou validação de conteúdo; envie um novo arquivo corrigido. `FAILED` significa falha operacional e mantém o original confirmado.

Para falha operacional, `POST /api/v1/jobs/{job_id}/retry` retorna o mesmo job para `QUEUED`, preserva o número de tentativas e reutiliza o objeto original. Somente `FAILED` é reenfileirável; job `REJECTED` deve ser substituído por novo upload. A consulta do job não reinicia o processamento.

Códigos de rejeição estáveis do inspetor e mensagens seguras:

| Código | Mensagem |
| --- | --- |
| `empty_content` | O arquivo está vazio. |
| `checksum_mismatch` | O conteúdo não corresponde ao checksum confirmado. |
| `format_mismatch` | O formato real não corresponde ao formato declarado. |
| `malformed_image` | A imagem não pôde ser decodificada ou tem dimensões inválidas. |
| `dimensions_exceeded` | As dimensões excedem o limite permitido. |
| `unsupported_transfer_syntax` | A sintaxe de transferência DICOM não é suportada. |
| `unsupported_dicom_pixels` | Os pixels DICOM não são suportados neste recorte. |
| `malformed_dicom` | O DICOM está incompleto ou malformado. |
| `unsupported_dicom_structure` | A estrutura DICOM não é suportada. |

`processing_failed` e `upload_not_found` são códigos operacionais do job. Para `processing_failed`, confira os logs e reenfileire apenas se o original ainda existir; `upload_not_found` requer restaurar ou reenviar o original, não repetir o job sem o objeto. Os erros de retry são `INGESTION_JOB_NOT_FOUND` (404) e `INGESTION_JOB_RETRY_NOT_ALLOWED` (409). O retry aceita somente `FAILED`, mantém o mesmo job e original e responde `202` com o estado `QUEUED`; uma segunda tentativa depois do primeiro aceite retorna 409 porque o job já não está `FAILED`. `IMAGE_UPLOAD_OBJECT_INVALID` retorna `details.reason`: `object_not_found`, `uploaded_before_session`, `size_mismatch`, `media_type_mismatch`, `checksum_mismatch` ou `upload_id_mismatch`. Confira objeto, sessão e checksum antes de repetir a confirmação, que é idempotente para a mesma sessão.

Na criação da sessão, envie `Idempotency-Key` (obrigatório, de 1 a 128 caracteres) e mantenha a mesma chave para repetir a requisição após falha de rede. Mesma chave, mesmo caso e mesmos metadados devolvem a mesma sessão e renovam uma URL assinada somente até o `expires_at` original. Mesma chave com caso ou metadados diferentes retorna 409 `IMAGE_UPLOAD_IDEMPOTENCY_KEY_REUSED`. A chave fica vinculada ao registro e pode ser reutilizada depois que a rotina de limpeza remove a sessão expirada. Se a sessão já expirou, use uma chave nova para começar outro upload. Sessão já confirmada não recebe outra URL (`IMAGE_UPLOAD_SESSION_NOT_PENDING`); consulte o estado pela imagem/job.

`DELETE /api/v1/image-uploads/{upload_id}` cancela uma sessão `PENDING_UPLOAD` e libera imediatamente a cota de sessões ativas. A URL pré-assinada emitida não pode ser revogada: um envio que já estava em andamento ainda pode chegar ao storage. A confirmação de uma sessão cancelada retorna 409 `IMAGE_UPLOAD_CANCELLED`; a limpeza após `expires_at` remove o objeto tardio e o registro. Sessões expiradas não contam para a cota, mesmo antes da limpeza física.

Execute `cd /caminho/vetorthoplan_backend && .venv/bin/python scripts/cleanup_expired_uploads.py` periodicamente (por exemplo, a cada 15 minutos em cron). A rotina aguarda 15 minutos além de `expires_at` para permitir que um POST já iniciado termine e então remove objetos e registros de sessões pendentes expiradas ou canceladas. Uma falha faz o comando sair com código 1 e mantém registros para nova tentativa.

`DELETE /api/v1/images/{image_id}` exclui a imagem persistida, objeto original, prévia, plano e job associado. A API responde 204; em `QUEUED` ou `PROCESSING`, ou enquanto a URL assinada de upload ainda for válida, responde 409 `IMAGE_DELETION_CONFLICT` e mantém os dados. Em caso de erro de storage, a operação falha e a interface deve manter a imagem listada; a chamada pode ser repetida porque a remoção do objeto é idempotente.

`PATCH /api/v1/images/{image_id}` altera somente `display_name`. Envie `{"display_name":"Membro anterior direito - lateral.png"}`. O nome é aparado, limitado a 255 caracteres, não aceita barras nem caracteres de controle e deve preservar a extensão original. Campos extras retornam 422. A resposta mantém os campos atuais de `ImageResponse`, incluindo `original_filename` e `display_name`. Para imagens sem renomeação, `display_name` é `null`; o frontend pode então apresentar `original_filename`.

`DELETE /api/v1/cases/{case_id}` remove o caso e seus registros dependentes, imagens, prévias, planos e jobs, respondendo 204. A API retorna 409 `CASE_DELETE_NOT_ALLOWED` com `details.reason` igual a `ACTIVE_UPLOAD` ou `ACTIVE_INGESTION` enquanto houver upload válido ou job `QUEUED`/`PROCESSING`. A operação mantém os registros se a remoção do storage falhar e pode ser repetida com segurança. Objetos originais também ficam registrados numa fila de limpeza tardia; execute a rotina `cleanup_expired_uploads.py` periodicamente para cobrir um envio que já estava em andamento quando a URL assinada expirou.
> Identidade: adapter local temporário; JWT/RBAC permanecem fora deste incremento.

![Referência visual para processamento de imagem](frontend/processamento-imagem-v1.png)

## Fluxo disponível

```text
POST /api/v1/image-uploads/{upload_id}/complete
        ↓ 202 + job_id
GET /api/v1/jobs/{job_id}
        ↓
QUEUED → PROCESSING → SUCCEEDED | REJECTED | FAILED
        ↓
GET /api/v1/cases/{case_id}/images
```

O worker lê o objeto em quarentena, recalcula o SHA-256, detecta o formato pelos bytes, extrai dimensões e cria uma prévia PNG privada. Para DICOM Part 10, o recorte atual decodifica imagens monocromáticas single-frame em Explicit/Implicit VR Little Endian e mantém uma allowlist de metadados sem identificadores do paciente, incluindo espaçamento e orientação quando disponíveis.

## Consultar o job

```http
GET /api/v1/jobs/{job_id}
```

Resposta:

```json
{
  "id": "00000000-0000-4000-8000-000000000126",
  "case_id": "00000000-0000-4000-8000-000000000064",
  "image_id": "00000000-0000-4000-8000-000000000125",
  "upload_id": "00000000-0000-4000-8000-000000000124",
  "status": "SUCCEEDED",
  "attempts": 1,
  "error_code": null,
  "created_at": "2026-09-18T12:00:00Z",
  "updated_at": "2026-09-18T12:00:02Z",
  "started_at": "2026-09-18T12:00:01Z",
  "finished_at": "2026-09-18T12:00:02Z"
}
```

O frontend deve fazer polling somente enquanto o estado do job for `QUEUED` ou `PROCESSING`, com intervalo inicial de dois segundos. `SUCCEEDED`, `REJECTED` e `FAILED` são terminais para o job. `FAILED` é um estado operacional da imagem e do job; o original confirmado é mantido para retry. `REJECTED` indica conteúdo inválido e requer novo upload. Após reload, `GET /api/v1/cases/{case_id}/images` e `GET /api/v1/images/{image_id}` devolvem `job_id` nulo até existir job e o identificador para retomar a consulta. `SUCCEEDED` acompanha imagem `READY`, mas a disponibilidade da prévia continua sendo governada separadamente por `preview_available`.

## Listar imagens do caso

```http
GET /api/v1/cases/{case_id}/images
```

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000125",
      "upload_id": "00000000-0000-4000-8000-000000000124",
      "job_id": "00000000-0000-4000-8000-000000000126",
      "case_id": "00000000-0000-4000-8000-000000000064",
      "original_filename": "joelho-direito.png",
      "kind": "PNG",
      "media_type": "image/png",
      "detected_media_type": "image/png",
      "size_bytes": 8388608,
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "status": "READY",
      "width_px": 2048,
      "height_px": 1536,
      "pixel_spacing_mm": [0.14, 0.14],
      "imager_pixel_spacing_mm": null,
      "image_orientation_patient": [1, 0, 0, 0, 1, 0],
      "rejection_code": null,
      "created_at": "2026-09-18T12:00:00Z",
      "completed_at": "2026-09-18T12:00:01Z",
      "processed_at": "2026-09-18T12:00:02Z"
    }
  ]
}
```

Uma imagem individual pode ser consultada em `GET /api/v1/images/{image_id}` com o mesmo objeto de resposta.

## Estados de interface

| Estado da imagem | Apresentação |
|---|---|
| `PENDING_UPLOAD` | Envio ainda não confirmado |
| `QUARANTINED` | Arquivo recebido; aguardando worker |
| `PROCESSING` | Validando conteúdo |
| `READY` | Conteúdo aprovado; metadados disponíveis |
| `REJECTED` | Arquivo recusado; mostrar ação de reenviar |

Para `REJECTED`, o frontend pode traduzir `rejection_code`, mas deve manter uma mensagem genérica para códigos desconhecidos. Para `FAILED`, oferecer retry manual via `POST /api/v1/jobs/{job_id}/retry`.

## Limites atuais

- a prévia PNG e a URL temporária estão disponíveis em `GET /api/v1/images/{image_id}/preview`;
- DICOM suporta inicialmente Explicit/Implicit VR Little Endian, monocromático e single-frame;
- transfer syntaxes comprimidas, RGB e multiframe ainda não são convertidas;
- não há antivírus;
- não há retry/backoff automático para falhas operacionais;
- migrations ainda precisam ser aplicadas no ambiente local/homologação.
