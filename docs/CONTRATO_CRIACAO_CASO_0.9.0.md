# Contrato de criação de caso — 0.9.0

`POST /api/v1/cases` exige `sex`: `MALE`, `FEMALE` ou `UNKNOWN`. Ausência, `null` e valores fora do enum resultam em HTTP 422; `UNKNOWN` é a escolha explícita para sexo não conhecido. Leitura de casos legados continua aceitando `sex: null`.

`birth_date` e `approximate_age_months` são opcionais individualmente e podem ser informados juntos. A API usa a data UTC da criação do caso como referência. Meses completos são a diferença de meses do calendário, ajustada ao último dia do mês de referência quando o dia de aniversário não existe naquele mês. Exemplo: nascimento em 31 de janeiro e referência em 28 de fevereiro conta um mês completo.

Com nascimento, o backend calcula e persiste `approximate_age_months`, define `age_source: BIRTH_DATE` e registra `age_reference_date`. Se o cliente também mandar a idade, ela deve coincidir com esse cálculo ou a API retorna 422 com `details.field = "approximate_age_months"`. Sem nascimento, a idade enviada é declarada, recebe `age_source: DECLARED` e a data UTC de criação como referência; ela não aumenta automaticamente. Sem os dois dados, a idade e seus metadados ficam nulos. `birth_date` futuro continua inválido.

A migration `20261019_0009` preenche a origem e referência dos dados legados sem tornar sexo legado obrigatório. Caso antigo que tenha nascimento sem idade armazenada recebe idade calculada na resposta usando sua data de criação como referência; os demais valores legados não são recalculados. A alteração é incompatível para clientes que criam casos sem `sex`; a versão da API e do pacote foi elevada de 0.8.0 a 0.9.0.
