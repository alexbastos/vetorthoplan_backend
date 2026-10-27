# Plano geométrico e medições da imagem

Referências visuais para a implementação frontend: [plano geométrico](frontend/plano-geometrico-v1.svg), [calibração por linha](frontend/calibracao-linha-v1.svg), [calibração por círculo](frontend/calibracao-circulo-v1.svg), [medições anatômicas](frontend/medicoes-anatomicas-v1.svg) e [simulação da osteotomia](frontend/simulacao-osteotomia-tplo-v1.svg). As pranchas são conceituais; o contrato executável está em `/openapi.json`.

## Consultar

`GET /api/v1/images/{image_id}/plan`

A imagem precisa pertencer ao tenant atual e estar em `READY`. Se ainda não houver plano, a resposta inicial tem `revision: 0` e documento vazio:

```json
{
  "image_id": "<uuid>",
  "revision": 0,
  "document": {"schema_version": 1, "calibration": null, "tplo": null, "clinical_validation": null, "objects": []},
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

## Validação clínica

O documento aceita `clinical_validation` para acompanhar o checklist do veterinário. Os estados são `DRAFT`, `READY_FOR_REVIEW`, `APPROVED` e `REJECTED`. Para `READY_FOR_REVIEW`, orientação, qualidade da imagem, calibração e referências anatômicas precisam estar confirmadas. `REJECTED` exige `rejection_reason`.

`APPROVED` só é persistido quando a imagem TPLO está `ELIGIBLE`, a calibração manual foi calculada e todas as medidas em `required_measurements` foram calculadas. Caso contrário, a API responde `422 CLINICAL_VALIDATION_INVALID`.

Medidas anatômicas adicionais são definidas pelo ambiente em `TPLO_CLINICAL_PROTOCOL_JSON` e consultadas em `GET /api/v1/tplo/clinical-protocol`. O cliente envia em `additional_measurements_input.landmarks` pontos normalizados com chaves nomeadas pelo protocolo e, em `reference_values`, valores de referência independentes. `DISTANCE` exige dois marcos e calibração manual; `ANGLE` exige três marcos. O backend recalcula as medidas e retorna erro absoluto, limite configurado e aceitação (`PASS`, `FAIL` ou `NOT_ASSESSED`). Para TPA, a referência usa a chave `TPA` e a tolerância é configurada separadamente.

Exemplo de entrada no documento do plano:

```json
{
  "additional_measurements_input": {
    "landmarks": {
      "cortex_start": {"x": 0.32, "y": 0.41},
      "cortex_end": {"x": 0.46, "y": 0.42}
    },
    "reference_values": {"CRANIAL_CORTEX_LENGTH": 18.4, "TPA": 27.5}
  }
}
```

Sem protocolo configurado, os limites ficam desativados. Essa configuração técnica não representa
validação clínica; o parceiro deve definir e homologar valores, marcos, unidades e tolerâncias.

Para calcular TPA, envie `tplo_landmarks` com `plateau_cranial`, `plateau_caudal`, `intercondylar_midpoint` e `talus_center`. O método preferido `MEDIAL_CONDYLE_CRANIAL_CRUCIATE_FULL_AXIS_V1` segue o artigo Today's Veterinary Practice: o marco cranial fica junto à inserção tibial do CrCL, caudal ao sulco do extensor digital longo; o marco caudal é o ponto mais caudoproximal do côndilo tibial medial. O eixo mecânico completo liga o ponto médio das eminências intercondilares ao centro do tálus. O TPA é o ângulo entre a linha do platô e a perpendicular ao eixo. A resposta persiste `tplo_measurement.tpa_degrees`; com calibração também inclui comprimentos do platô/eixo em mm e o `calibration_id`.

`tplo_measurement.clinically_validated` permanece `false`: o cálculo reproduz a geometria descrita, mas o parceiro clínico ainda precisa confirmar os marcos, tolerâncias e desempenho com radiografias autorizadas. A qualidade da radiografia precisa ser revisada: incidência lateral verdadeira, côndilos femorais e tibiais superpostos, tíbia alinhada, feixe centrado no joelho e toda a tíbia incluída. O marcador de calibração deve ficar próximo do joelho e no mesmo plano/altura. Osteófitos ou posicionamento ruim podem dificultar marcos e alterar a medida. Consulte [Today's Veterinary Practice: como medir o TPA](https://todaysveterinarypractice.com/orthopedics/small-animal-cruciate-disease-tibial-plateau-angle/) e estudos sobre [eixo completo versus eixos proximais](https://pubmed.ncbi.nlm.nih.gov/13677389/) e [variação do marco caudal](https://pubmed.ncbi.nlm.nih.gov/24003987/).

Para a etapa de rotação, registre o TPA pré-operatório e o diâmetro da lâmina escolhida. O artigo de [Garofallo](https://www.vetgarofallo.com/post/tabela-tplo) direciona à tabela oficial de rotação TPLO da [BioMedtrix/VOI](https://biomedtrix.com/tplo-rotation-guide-chart-1-15-18-2/), cujo objetivo de exemplo é slope pós-operatório aproximado de 5°. Não extrapole valores fora da tabela nem transforme o exemplo publicado (TPA 25°, lâmina 24 mm, rotação 8,38 mm) em fórmula universal; a seleção e conferência cabem ao cirurgião.

O endpoint `GET /api/v1/tplo/rotation-table` consulta por padrão a [tabela BioMedtrix/VOI `1-15-18`](https://biomedtrix.com/tplo-rotation-guide-chart-1-15-18-2/), carregada pela migration `20261026_0018`. A versão, a fonte, os links do gráfico, o alvo de slope de 5 graus, o SHA-256 e as 360 combinações são persistidos no banco. A migration valida a grade de TPA (10–45 graus), os dez diâmetros de lâmina (8–33 mm), valores finitos/positivos e a referência publicada TPA 25° com lâmina 24 mm = 8,38 mm. `tpa_degrees` e `blade_diameter_mm` filtram por correspondência numérica exata; ausência de correspondência retorna lista vazia. Não existe interpolação nem recomendação automática. Uma versão posterior homologada pode ser fornecida pelas variáveis `TPLO_ROTATION_TABLE_VERSION`, `TPLO_ROTATION_TABLE_SOURCE` e `TPLO_ROTATION_TABLE_JSON`, sempre em conjunto.

## Finalizar e emitir relatório

`POST /api/v1/images/{image_id}/plan/finalize` recebe `{"base_revision": <revisão>}`. A finalização requer imagem `ELIGIBLE`, cinco critérios de qualidade em `PASS`, calibração calculada, checklist clínico confirmado, estado `APPROVED` e valores calculados/aceitos para todas as medidas obrigatórias. Falhas retornam `422 CLINICAL_VALIDATION_INVALID`; divergência na revisão retorna `409 PLAN_REVISION_CONFLICT`.

O backend grava um snapshot imutável do plano e gera PNG e PDF com imagem anotada, resumo geométrico, medidas, calibração e auditoria. A resposta inclui a versão da finalização, a revisão de origem, SHA-256 do snapshot e de cada arquivo, além de links temporários para download. `GET /api/v1/images/{image_id}/plan/finalization` consulta o snapshot e emite novos links. Depois de finalizado, `PUT /api/v1/images/{image_id}/plan` retorna `409 IMAGE_PLAN_FINALIZED`.

Os relatórios identificam a versão do template `TPLO_FINAL_REPORT_V1`. A migration `20261026_0017_finalized_image_plans` cria a tabela de snapshots e gatilhos no banco que bloqueiam alterações ao snapshot e ao plano congelado. A exclusão autorizada da imagem ou do caso também remove os relatórios do armazenamento.

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
