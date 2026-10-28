# Catálogo de implantes

O catálogo separa o arquivo recebido do recurso editável usado pelo viewer. O backend preserva o original sem interpretar sua extensão ou assinatura; o conversor plugável transforma a origem em um recurso editável e em uma prévia PNG. Assim, a decisão do formato de origem e do formato de trabalho pode evoluir sem alterar o fluxo de importação, revisão e publicação.

## Fluxo

`AWAITING_SOURCE` → `WAITING_FOR_CONVERTER` ou `QUEUED` → `PROCESSING` → `REVIEW_REQUIRED` → `APPROVED` ou `REJECTED`. Uma falha de integridade ou conversão fica em `FAILED`.

1. Criar uma importação com metadados do fabricante, produto, família, versão, unidades e listas opcionais de `variants` e `views` aceitas para aquele desenho.
2. Enviar o arquivo em `PUT /api/v1/implant-catalog/imports/{id}/source`. `X-Original-Filename` é opcional; `X-Source-Media-Type` também é opcional e, quando omitido, usa o `Content-Type` da requisição. O backend aceita bytes opacos até 50 MiB, calcula SHA-256 e preserva o objeto original.
3. Quando `IMPLANT_CATALOG_CONVERSION_SERVICE_URL` estiver configurada, o worker envia bytes, media type, nome original e SHA-256 ao adaptador de conversão. A ausência do adaptador mantém a importação em `WAITING_FOR_CONVERTER` sem perder o original.
4. O adaptador responde com o recurso editável escolhido pelo produto, seu media type, uma prévia PNG e metadados da conversão. A resposta legada `svg_base64` continua aceita durante a transição.
5. O worker valida integridade, limites e segurança de SVG quando esse for o formato retornado; grava os derivados e marca a importação `REVIEW_REQUIRED`.
6. Um administrador aprova ou rejeita a revisão. Apenas itens aprovados são publicados em `GET /api/v1/implant-catalog/items`.

## Contrato do conversor

O adaptador recebe o arquivo binário no corpo HTTP. Os headers incluem `Content-Type`, `X-Original-Filename`, `X-Source-SHA256` e, se configurado, `Authorization: Bearer ...`.

```json
{
  "converter_version": "adapter-1.0 / engine-1.0",
  "drawing_metadata": {"units": "MM", "width": 60.0, "height": 12.0},
  "editable_asset_base64": "...",
  "editable_asset_media_type": "image/svg+xml",
  "preview_png_base64": "..."
}
```

`editable_asset_media_type` descreve o formato de trabalho aprovado pelo produto. A API retorna `editable_asset_url` e `editable_asset_media_type` sem impor ao frontend um formato de origem. SVG é validado contra scripts, eventos, referências externas, DTD e entidades. Limites do adaptador e isolamento do processo são responsabilidade do serviço conversor, que trata arquivos externos.

## Referência e posicionamento no plano

Um objeto `IMPLANT` em `PUT /api/v1/images/{image_id}/plan` referencia `catalog_item_id` e registra posição normalizada, `rotation_degrees`, escala uniforme, opacidade, variante e vista. O servidor valida que o item está aprovado e pertence ao tenant autenticado; variante e vista, quando informadas, precisam constar nos metadados da importação. A matriz afim é recalculada no sistema de coordenadas da imagem original e qualquer matriz recebida do cliente é descartada. Sem as dimensões da imagem, a resposta informa `IMAGE_DIMENSIONS_REQUIRED`.

O relatório final registra a referência e os parâmetros de posicionamento e desenha um marcador de posição na radiografia. A renderização do arquivo editável sobre o viewer é responsabilidade do frontend e respeita o `editable_asset_media_type` publicado pelo catálogo.

Os endpoints administrativos exigem contexto autenticado de tenant e `X-Catalog-Admin-Token` com segredo de pelo menos 32 caracteres. A aprovação editorial registra autor, data e nota; não certifica indicação clínica, licenciamento do desenho ou compatibilidade com um paciente. Cada revisão de desenho deve gerar uma nova importação versionada.

## Configuração

Defina `IMPLANT_CATALOG_ADMIN_TOKEN` e, quando houver um conversor disponível, `IMPLANT_CATALOG_CONVERSION_SERVICE_URL`, `IMPLANT_CATALOG_CONVERSION_SERVICE_TOKEN` e `IMPLANT_CATALOG_CONVERSION_TIMEOUT_SECONDS`. Em ambientes fora de local/test, a URL deve usar HTTPS. As variáveis `ODA_CONVERSION_*` continuam aceitas como aliases temporários.
