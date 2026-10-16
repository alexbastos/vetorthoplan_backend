# Plano geométrico da imagem

Referência visual para a futura implementação frontend: [plano geométrico](frontend/plano-geometrico-v1.svg). A prancha ilustra calibração, objetos, revisão e aviso de conflito. Ela é conceitual; o contrato executável está em `/openapi.json`.

## Consultar

`GET /api/v1/images/{image_id}/plan`

A imagem precisa pertencer ao tenant atual e estar em `READY`. Se ainda não houver plano, a resposta inicial tem `revision: 0` e documento vazio:

```json
{
  "image_id": "<uuid>",
  "revision": 0,
  "document": {"schema_version": 1, "calibration": null, "objects": []},
  "updated_at": null
}
```

Imagem inexistente ou fora do tenant retorna `404 IMAGE_NOT_FOUND`. Imagem ainda não pronta retorna `409 IMAGE_NOT_READY`.

## Salvar

`PUT /api/v1/images/{image_id}/plan`

Envie a revisão lida em `base_revision` junto com o documento completo. Coordenadas `x` e `y` são normalizadas entre `0` e `1`; o documento aceita até 500 objetos (`LINE`, `ANGLE`, `CIRCLE` ou `TPLO`) e calibração opcional por linha de referência.

```json
{
  "base_revision": 0,
  "document": {
    "schema_version": 1,
    "calibration": {
      "kind": "REFERENCE_LINE",
      "start": {"x": 0.2, "y": 0.3},
      "end": {"x": 0.7, "y": 0.3},
      "known_length_mm": 25
    },
    "objects": [
      {
        "id": "<uuid>",
        "type": "LINE",
        "start": {"x": 0.2, "y": 0.3},
        "end": {"x": 0.7, "y": 0.3},
        "label": "Referência"
      }
    ]
  }
}
```

A primeira gravação usa revisão `0`; a resposta persistida passa a `1`. Cada atualização incrementa a revisão. Se outra gravação avançar a revisão antes desta requisição, a API responde `409 PLAN_REVISION_CONFLICT` com a revisão atual em `details.current_revision`; recarregue o plano antes de reaplicar alterações. Cada PUT substitui o documento geométrico inteiro.

Este endpoint armazena marcações geométricas. Cálculos clínicos e o fluxo TPLO completo ainda não fazem parte deste contrato.
