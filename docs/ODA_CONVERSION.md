# Fluxo DWG para o catálogo de próteses

O backend mantém os DWGs originais e só publica um item depois da conversão e da aprovação manual. O backend não embute nem redistribui o ODA Drawings SDK: a conversão exige um wrapper/serviço interno que use uma licença ODA válida.

## Estados

`AWAITING_SOURCE` → `WAITING_FOR_CONVERTER` (enquanto o conversor não estiver configurado) ou `QUEUED` → `PROCESSING` → `REVIEW_REQUIRED` → `APPROVED` ou `REJECTED`. Falhas de integridade ou conversão ficam em `FAILED`. Os endpoints administrativos exigem `IMPLANT_CATALOG_ADMIN_TOKEN` e contexto de tenant autenticado. O item só aparece em `GET /api/v1/implant-catalog/items` depois de aprovado.

## API de ingestão

1. `POST /api/v1/implant-catalog/imports` com `X-Catalog-Admin-Token` e JSON de metadados: fabricante, nome/código, família, versão do catálogo, unidade, referência de origem e indicação declarada.
2. `PUT /api/v1/implant-catalog/imports/{id}/source` com bytes DWG, `Content-Type: application/octet-stream` e `X-Original-Filename`. Limite 50 MiB. O backend valida assinatura `AC10`, calcula SHA-256 e armazena o original em `implant-catalog/source/`.
3. Quando `ODA_CONVERSION_SERVICE_URL` estiver configurado, o worker envia o DWG binário ao wrapper por HTTP POST com `Content-Type: application/acad` e `X-Source-SHA256`. Se configurado, também envia `Authorization: Bearer ...`.
4. O wrapper responde JSON no formato abaixo. O `converter_version` deve identificar precisamente a versão instalada do SDK e do wrapper.
5. O worker confere integridade, limites, formato SVG/PNG e atributos SVG ativos, grava os derivados sem substituir o original e passa o item para `REVIEW_REQUIRED`.
6. Um administrador revisa `GET /api/v1/implant-catalog/imports` e aprova ou rejeita. Aprovação exige SVG e prévia prontos. Cada nova revisão de desenho deve entrar como um novo registro/versionamento.

```json
{
  "converter_version": "oda-drawings-sdk-X.Y / wrapper-Z",
  "drawing_metadata": {
    "units": "MM",
    "width": 60.0,
    "height": 12.0
  },
  "svg_base64": "...",
  "preview_png_base64": "..."
}
```

O conversor recebe só o arquivo, não executa scripts nem chama URLs da origem DWG. O wrapper deve impor limites próprios de memória/tempo e rodar isolado, pois DWG é conteúdo externo. Os SVGs com script, eventos, referências externas, `foreignObject`, DTD ou entidades são rejeitados.

## Configuração

Defina `IMPLANT_CATALOG_ADMIN_TOKEN` com segredo aleatório de pelo menos 32 caracteres. Defina `ODA_CONVERSION_SERVICE_URL` apenas depois de obter e instalar uma licença ODA e publicar o wrapper interno. `ODA_CONVERSION_SERVICE_TOKEN` é opcional quando o serviço tiver autenticação de rede equivalente. Sem URL, o backend recebe e preserva os DWGs em `WAITING_FOR_CONVERTER`; ele não declara a conversão concluída.

Os metadados comerciais e a aprovação editorial não certificam compatibilidade clínica ou adequação para TPLO. Essa validação precisa ocorrer separadamente por profissional habilitado.
