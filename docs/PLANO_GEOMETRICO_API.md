# Plano geométrico e medições da imagem

Referências visuais para a implementação frontend: [plano geométrico](frontend/plano-geometrico-v1.svg), [calibração por linha](frontend/calibracao-linha-v1.svg), [calibração por círculo](frontend/calibracao-circulo-v1.svg), [medições anatômicas](frontend/medicoes-anatomicas-v1.svg) e [simulação da osteotomia](frontend/simulacao-osteotomia-tplo-v1.svg). As pranchas são conceituais; o contrato executável está em `/openapi.json`.

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

## Resultados de medição

Ao salvar, o backend preserva pontos normalizados e recalcula os resultados derivados usando a largura e altura em pixels da imagem original `READY`. Resultados enviados pelo cliente são descartados e recalculados; o frontend deve enviar a geometria e não tentar definir a escala nem os valores medidos.

- A calibração linear usa a distância euclidiana entre os dois pontos de referência. A circular usa o diâmetro, calculado como duas vezes a distância centro–borda. A resposta inclui `calibration.result.reference_length_px`, `calibration.result.mm_per_pixel` e `calibration.result.calibration_id`.
- A escala é `comprimento real em mm / comprimento da referência em px`. Coordenadas normalizadas são convertidas com a dimensão original correspondente (`x × largura`, `y × altura`), preservando a proporção da imagem.
- `LINE` devolve `measurement.values.length` em `mm`; `CIRCLE` devolve `radius`, `diameter` e `circumference` em `mm`; `ANGLE` devolve `angle` em graus. `TPLO` apresenta raio em mm e a rotação informada em graus, sem inferir recomendação clínica.
- Medidas em mm incluem o mesmo `calibration_id` do resultado da calibração. Ele é um fingerprint da referência manual e dimensões da imagem. Alterar referência ou imagem muda o ID e recalcula as medidas.
- Se uma geometria linear, circular ou TPLO ainda não tiver calibração válida, a resposta usa `measurement.status: "CALIBRATION_REQUIRED"` sem valores em mm. Se faltarem dimensões da imagem, usa `IMAGE_DIMENSIONS_REQUIRED`. O ângulo pode ser calculado sem calibração.
- O PixelSpacing e o ImagerPixelSpacing DICOM não são usados na fórmula.
- A simulação TPLO recebe `fragment.points` como contorno fechado (mínimo 3 pontos normalizados), junto ao centro, borda do raio e rotação do objeto `TPLO`. O backend devolve `simulation.status`, `center_px`, `radius_mm`, `rotation_degrees` e uma matriz afim 2×3 em coordenadas da imagem original. A matriz aplica rotação ao redor do centro; ângulo positivo é horário na tela (eixo Y da imagem cresce para baixo).
- `simulation.status` pode ser `SIMULATED`, `FRAGMENT_REQUIRED`, `CALIBRATION_REQUIRED` ou `IMAGE_DIMENSIONS_REQUIRED`. A prévia geométrica não calcula objetivo cirúrgico, TPA alvo, deslocamento de corda nem recomendação de rotação.
- A geometria de simulação também inclui `calibration_id`; mudança na escala implica novo cálculo ao salvar o plano.

Exemplo de partes calculadas da resposta (valores ilustrativos):

```json
{
  "calibration": {
    "kind": "REFERENCE_LINE",
    "start": {"x": 0.2, "y": 0.3},
    "end": {"x": 0.7, "y": 0.3},
    "known_length_mm": 25,
    "result": {
      "calibration_id": "<sha256>",
      "reference_length_px": 1024,
      "mm_per_pixel": 0.0244140625
    }
  },
  "objects": [{
    "id": "<uuid>",
    "type": "LINE",
    "start": {"x": 0.25, "y": 0.4},
    "end": {"x": 0.55, "y": 0.4},
    "measurement": {
      "status": "CALCULATED",
      "calibration_id": "<same sha256>",
      "values": {"length": 15},
      "units": {"length": "mm"}
    }
  }]
}
```

As medidas são geométricas e servem como base técnica para o próximo estágio de planejamento. Fórmulas anatômicas, critérios de qualidade clínica e validação de uso devem ser homologados com o parceiro e imagens autorizadas.

## Coordenadas e calibração no contrato atual

`x=0` é a borda esquerda e `x=1` a direita; `y=0` é a borda superior e `y=1` a inferior. Os pontos são normalizados no quadro da imagem original já orientado para exibição. A prévia é miniatura PNG de no máximo 1600 px no maior eixo, sem recorte e preservando a proporção; converta coordenadas normalizadas pelo tamanho renderizado em vez de reutilizar pixels absolutos.

O worker conserva `PixelSpacing`, `ImagerPixelSpacing` e `ImageOrientationPatient` DICOM, quando informados, em `ImageResponse.pixel_spacing_mm`, `imager_pixel_spacing_mm` e `image_orientation_patient`. O espaçamento segue a ordem DICOM `[linhas, colunas]`. A prévia preserva a matriz de pixels e proporção da imagem original; para PNG/JPEG, a orientação EXIF é aplicada antes da prévia. O backend não usa automaticamente o espaçamento DICOM para calibrar nem transformar coordenadas: uma calibração clínica validada continua necessária para medidas em milímetros. Conflito de revisão ocorre quando `base_revision` não coincide com a revisão persistida.
