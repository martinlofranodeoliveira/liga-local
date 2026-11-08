# Formatos locais

## Participantes

CSV UTF-8 com BOM inicial opcional, vírgula, cabeçalho exato `id,name`, até 128 KiB e no máximo 32 registros de dados. Cada registro tem dois campos; linhas vazias são inválidas. Um newline final é permitido. O grupo deve ter de 2 a 32 participantes.

IDs seguem `[A-Za-z0-9][A-Za-z0-9_-]{0,39}` e distinguem maiúsculas de minúsculas. São únicos. Nomes têm de 1 a 80 caracteres Unicode; o nome da liga tem de 1 a 120. Não podem começar ou terminar com espaço, nem conter caracteres Unicode da categoria C, incluindo controles, formatos e surrogates. Nomes repetidos são permitidos: o ID define a identidade.

## Documento JSON

O documento tem exatamente estas chaves:

```json
{
  "schema_version": 1,
  "name": "Duelo da Praça",
  "participants": [
    {"id": "aurora", "name": "Aurora"},
    {"id": "brisa", "name": "Brisa"}
  ],
  "double_round": false,
  "scoring": {"win": 3, "draw": 1, "loss": 0},
  "rounds": [
    {
      "number": 1,
      "matches": [
        {"id": "r001-m001", "home": "aurora", "away": "brisa", "score": null}
      ],
      "bye": null
    }
  ]
}
```

Um placar registrado é `{"home": 2, "away": 0}`, com inteiros de 0 a 999. Pontuações são inteiros de 0 a 1000 e obedecem `win > draw >= loss`. Booleanos não substituem números inteiros. O [calendário](algoritmo.md) é reconstruído e conferido na validação.

JSON deve ser UTF-8 estrito, sem BOM, com até 2 MiB codificados e profundidade máxima 12. Campos ausentes, extras, chaves duplicadas em qualquer nível, floats, NaN, infinitos e surrogates são recusados. A ordem das chaves do objeto recebido pode variar. A serialização canônica usa Unicode literal, indentação de dois espaços e LF final. Funções que recebem texto JSON nunca interpretam esse texto como caminho de arquivo.

## Resultados CSV

```csv
match_id,home_score,away_score
r001-m001,2,0
r001-m002,,
```

O importador aceita BOM inicial, até 128 KiB e 1000 registros de dados, usando leitura CSV estrita. O cabeçalho e a quantidade de campos devem ser exatos. IDs devem existir na liga e não podem se repetir no arquivo, mesmo em linhas sem placar.

Os dois placares vazios pulam o jogo. Apenas um vazio é erro. Valores devem ter de um a três dígitos ASCII, de 0 a 999, sem espaços, sinais ou casas decimais. Ao menos um resultado deve estar preenchido. A importação é integral: conflitos ou linhas inválidas não aplicam nenhuma alteração.

Exportar um modelo inclui todos os jogos na ordem do calendário. Resultados já iguais podem ser reimportados. Alterar um resultado existente requer `replace=True` na API ou `--substituir` na CLI; limpar exige a operação explícita de remoção.

## Relatórios

CSV de tabela tem o cabeçalho:

```text
id,name,played,won,drawn,lost,goals_for,goals_against,goal_difference,points,rank
```

CSV de jogos tem:

```text
round,match_id,home_id,home_name,away_id,away_name,home_score,away_score
```

Jogos pendentes têm os dois campos de placar vazios. Folgas aparecem no texto de jogos; não viram jogos fictícios no CSV ou na lista JSON. Todos os CSVs exportados terminam com LF. Os relatórios JSON usam Unicode literal, indentação de dois espaços e LF final.

Nos CSVs de tabela e jogos, strings que começam com `=`, `+`, `-`, `@`, tab ou CR recebem um apóstrofo inicial. Números continuam numéricos, inclusive saldo negativo. Essa precaução não garante proteção universal em planilhas. O modelo de resultados preserva os IDs necessários para reimportação.
