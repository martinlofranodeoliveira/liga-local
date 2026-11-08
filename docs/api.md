# Referência da API

Importe os nomes públicos diretamente de `liga_local`. Todas as operações são puras: não modificam entradas nem compartilham subestruturas mutáveis com elas. As entradas diretas exigem `dict`, `list`, `str`, `int` e `bool` exatos onde aplicáveis; subclasses e objetos customizados são recusados.

| Função | Retorno e comportamento |
| --- | --- |
| `create_league(name, participants, *, double_round=False, scoring=None)` | Documento novo com calendário canônico, sem resultados. `participants` é lista de `{id, name}` e `scoring` é `{win, draw, loss}`; padrão 3/1/0. |
| `validate_league(doc)` | Cópia canônica validada, incluindo conferência do calendário inteiro. |
| `set_result(doc, match_id, home_score, away_score, *, replace=False)` | Liga nova com placar. O mesmo resultado é idempotente; alteração de resultado exige `replace=True`. |
| `clear_result(doc, match_id)` | Liga nova com placar removido; limpar jogo já pendente é idempotente. |
| `standings(doc)` | Lista ordenada com as onze chaves de classificação descritas no formato. |
| `progress(doc)` | `{participants, rounds, total_matches, played_matches, pending_matches, complete}`. |
| `fixtures(doc, round_number=None)` | Lista de jogos na ordem do calendário, opcionalmente de uma rodada inteira válida. |
| `dumps_league(doc)` | Texto JSON canônico validado por roundtrip. |
| `loads_league(text)` | Documento validado a partir de texto JSON, sem leitura de arquivos. |
| `import_results_csv(doc, text, *, replace=False)` | Liga completa nova após importação atômica de texto CSV. |
| `results_csv(doc)` | Modelo CSV com todos os jogos e placares registrados. |
| `standings_csv(doc)` | CSV da classificação com precaução para fórmulas em strings. |

Cada item de `standings` tem, nesta ordem, `id, name, played, won, drawn, lost, goals_for, goals_against, goal_difference, points, rank`. Cada item de `fixtures` tem `round, match_id, home_id, home_name, away_id, away_name, home_score, away_score`; placares pendentes são `None`. Uma rodada deve ser inteiro de 1 até a última rodada, sem aceitar booleano.

`progress` conta somente jogos reais. `complete` fica verdadeiro quando todos têm placar, independentemente da ordem em que foram informados.

## Erros

`LeagueError` deriva de `ValueError` e possui `.code` estável. Mensagens são curtas e não ecoam dados de entrada. Para tratamento programático, use o código:

```python
from liga_local import LeagueError, loads_league

try:
    liga = loads_league("{}")
except LeagueError as error:
    assert error.code == "INVALID_LEAGUE"
```

| Código | Situação |
| --- | --- |
| `INVALID_LEAGUE` | Modelo, tipos, campos ou flags inválidos. |
| `INVALID_JSON` | Parsing, codificação, duplicatas ou limites de transporte JSON. |
| `INVALID_CSV` | Estrutura, placares ou limites do transporte CSV inválidos. |
| `UNKNOWN_MATCH` | Jogo inexistente em uma operação ou em CSV estruturalmente válido. |
| `RESULT_EXISTS` | Tentativa de alterar resultado sem permissão de substituição. |
| `INVALID_SCORE` | Placar inválido em uma operação de resultado. |
| `INVALID_ROUND` | Filtro de rodada inválido. |

A CLI acrescenta `OUTPUT_EXISTS` e `IO_ERROR`. Se várias falhas coexistirem, a precedência entre elas não é garantida. Erros nunca modificam a liga recebida.
