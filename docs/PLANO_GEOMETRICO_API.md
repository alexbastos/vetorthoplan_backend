# Plano geométrico da imagem

Referência visual para a futura implementação frontend: [plano geométrico](frontend/plano-geometrico-v1.svg). A prancha ilustra calibração, objetos, revisão e aviso de conflito. Ela é conceitual; o contrato executável está em `/openapi.json`.

## Consultar

`GET /api/v1/images/{image_id}/plan`

A imagem precisa pertencer ao tenant atual e estar em `READY`. Se ainda não houver plano, a resposta inicial tem `revision: 0` e documento vazio:

```json
{
  "image_id": "<uuid>",
  "revision": 0,
  "document": {"schema_version": 1, "calibration": null, "tplo": null, "objects": []},
  "updated_at": null
}
```

Imagem inexistente ou fora do tenant retorna `404 IMAGE_NOT_FOUND`. Imagem ainda não pronta retorna `409 IMAGE_NOT_READY`.

## Salvar

`PUT /api/v1/images/{image_id}/plan`

Envie a revisão lida em `base_revision` junto com o documento completo. Coordenadas `x` e `y` são normalizadas entre `0` e `1`; `x=0` é a borda esquerda e `y=0` a borda superior. Os pontos se referem à matriz da imagem original, orientada para exibição, e não às dimensões reduzidas da prévia. O documento aceita até 500 objetos (`LINE`, `ANGLE`, `CIRCLE` ou `TPLO`) e calibração opcional por linha ou círculo de referência.

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

A calibração circular usa `kind: "REFERENCE_CIRCLE"`, `center`, `edge` e `known_diameter_mm`; `edge` marca um ponto da borda do objeto circular de diâmetro conhecido. A calibração linear usa `REFERENCE_LINE`, `start`, `end` e `known_length_mm`.

O bloco `tplo` registra `laterality` (`LEFT`/`RIGHT`) e `projection` (`MEDIOLATERAL`, `CRANIOCAUDAL` ou `UNKNOWN`) da radiografia selecionada, além do estado de elegibilidade e observações. Esses valores descrevem a imagem usada no plano; não são inferidos automaticamente de DICOM. O campo `tplo` permanece no contrato local atual junto com a validação de elegibilidade introduzida em `master`.

A primeira gravação usa revisão `0`; a resposta persistida passa a `1`. Cada atualização incrementa a revisão. Se outra gravação avançar a revisão antes desta requisição, a API responde `409 PLAN_REVISION_CONFLICT` com a revisão atual em `details.current_revision`; recarregue o plano antes de reaplicar alterações. Cada PUT substitui o documento geométrico inteiro.

Este endpoint armazena marcações geométricas. Cálculos clínicos e o fluxo TPLO completo ainda não fazem parte deste contrato.

## Coordenadas e calibração no contrato atual

`x=0` é a borda esquerda e `x=1` a direita; `y=0` é a borda superior e `y=1` a inferior. Os pontos são normalizados no quadro da imagem original já orientado para exibição. A prévia é miniatura PNG de no máximo 1600 px no maior eixo, sem recorte e preservando a proporção; converta coordenadas normalizadas pelo tamanho renderizado em vez de reutilizar pixels absolutos.

O worker conserva `PixelSpacing`, `ImagerPixelSpacing` e `ImageOrientationPatient` DICOM, quando informados, em `ImageResponse.pixel_spacing_mm`, `imager_pixel_spacing_mm` e `image_orientation_patient`. O espaçamento segue a ordem DICOM `[linhas, colunas]`. A prévia preserva a matriz de pixels e proporção da imagem original; para PNG/JPEG, a orientação EXIF é aplicada antes da prévia. O backend não usa automaticamente o espaçamento DICOM para calibrar nem transformar coordenadas: uma calibração clínica validada continua necessária para medidas em milímetros. Conflito de revisão ocorre quando `base_revision` não coincide com a revisão persistida.
