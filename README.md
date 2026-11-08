# Liga Local

Biblioteca e CLI em português para organizar campeonatos de pontos corridos de pequenos grupos. Recebe participantes e resultados fornecidos por você, gera o calendário e calcula a classificação. Funciona localmente, sem dependências de runtime, rede, contas ou banco de dados. Python 3.11 ou posterior.

## Comece com uma liga fictícia

Instale em um ambiente virtual:

```sh
git clone https://github.com/martinlofranodeoliveira/liga-local.git
cd liga-local
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Na pasta do projeto, estes três comandos criam a liga dos quatro times do exemplo e mostram calendário e classificação inicial:

```sh
liga-local criar --nome "Copa do Bairro" --participantes examples/participantes.csv --saida liga.json
liga-local jogos liga.json
liga-local tabela liga.json
```

O primeiro jogo é `r001-m001`, entre Aurora e Duna. Registre seu placar em um **novo** arquivo:

```sh
liga-local resultado liga.json --jogo r001-m001 --casa 2 --fora 0 --saida liga-rodada1.json
liga-local tabela liga-rodada1.json
liga-local verificar liga-rodada1.json
```

Aurora terá 3 pontos; os jogos restantes continuam pendentes. `verificar` retorna progresso em JSON e código de saída 0 para uma liga válida, mesmo incompleta. `python -m liga_local` aceita os mesmos comandos que `liga-local`.

## Calendário e classificação

O arquivo de participantes usa cabeçalho exato `id,name`; a ordem das linhas define o calendário. São aceitos de 2 a 32 participantes; IDs são únicos e nomes podem se repetir. Os exemplos são fictícios.

O calendário segue um circle method determinístico. No turno simples, cada par joga uma vez; uma quantidade ímpar de participantes gera uma folga por rodada. Esse algoritmo não promete equilíbrio perfeito de mandos: em um grupo de quatro, um participante pode jogar as três partidas fora. `--turno-returno` acrescenta um segundo turno com os mesmos confrontos e mandos invertidos, equilibrando cada par. Veja o [algoritmo completo](docs/algoritmo.md).

A pontuação padrão é vitória 3, empate 1, derrota 0. Na criação, use `--pontos-vitoria`, `--pontos-empate` e `--pontos-derrota` para alterá-la. Os valores devem ser inteiros entre 0 e 1000, com vitória > empate >= derrota.

A tabela considera apenas placares registrados. Ordena por pontos, saldo de gols, gols a favor e vitórias, todos decrescentes. Empates nessas quatro métricas têm a mesma posição competitiva, como 1, 1, 3. O ID crescente organiza a exibição de empatados; não desfaz esse empate. Não há confronto direto nem critérios disciplinares.

## Resultados em lote e relatórios

```sh
liga-local modelo-resultados liga.json --saida resultados.csv
# Preencha home_score e away_score dos jogos que já aconteceram.
liga-local importar-resultados liga.json resultados.csv --saida liga-importada.json
liga-local tabela liga-importada.json --formato csv --saida tabela.csv
liga-local jogos liga-importada.json --rodada 1 --formato json
```

O CSV de resultados usa `match_id,home_score,away_score`. Duas células de placar vazias pulam o jogo; uma só vazia é erro. Preencha ao menos um jogo. Todos os registros são validados antes da aplicação: um erro impede a importação inteira. Um resultado já igual é idempotente; mudar um resultado existente requer `--substituir`. Para remover um placar, use `limpar-resultado`.

```sh
liga-local resultado liga-importada.json --jogo r001-m001 --casa 1 --fora 1 --substituir --saida liga-corrigida.json
liga-local limpar-resultado liga-corrigida.json --jogo r001-m001 --saida liga-sem-placar.json
```

`tabela` e `jogos` aceitam `--formato texto|csv|json` e `--saida ARQUIVO`. Sem `--saida`, relatórios vão para stdout. O texto identifica o estado Parcial ou Concluída; o calendário textual também mostra folgas. CSV de jogos contém somente partidas. Os CSVs de tabela e jogos prefixam apóstrofo em strings com início típico de fórmula de planilha; isso é uma precaução, sem garantia universal de segurança em planilhas.

## Arquivos e erros

Cada saída nomeada deve ter um caminho novo: o programa recusa arquivos, diretórios e symlinks existentes, inclusive a própria entrada. Não existe `--force`. A publicação escreve e sincroniza um temporário no diretório do destino, publica por hard link sem sobrescrever e remove o temporário. Se o sistema de arquivos não oferecer essa operação, o comando falha explicitamente.

As entradas devem ser arquivos regulares UTF-8, passados explicitamente; FIFO e symlink no componente final são recusados. Diretórios pais podem ser symlinks. A CLI usa recursos de arquivos disponíveis em Linux/POSIX; em plataformas sem leitura segura ou hard links, pode recusar a operação. JSON aceita até 2 MiB; CSV, até 128 KiB. Entradas permanecem byte a byte intactas. Erros curtos vão para stderr, com um código estável e saída 2; não incluem o conteúdo recebido. Consulte [formatos e limites](docs/formato.md).

## Uso como biblioteca

```python
from liga_local import create_league, set_result, standings

liga = create_league("Duelo da Praça", [
    {"id": "aurora", "name": "Aurora"},
    {"id": "brisa", "name": "Brisa"},
])
atualizada = set_result(liga, "r001-m001", 2, 0)
assert standings(atualizada)[0]["points"] == 3
assert liga["rounds"][0]["matches"][0]["score"] is None
```

As funções são puras e retornam estruturas novas. A [referência da API](docs/api.md) descreve as operações e os códigos de erro.

O pacote não certifica regulamentos de federações, não fornece resultados reais e não envolve apostas. Adapte as regras de pontuação somente ao acordo do seu grupo.

## Desenvolvimento

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) para executar testes e o check de distribuição em sandbox. Licença [MIT](LICENSE).

Um projeto da [LOFRANO TECNOLOGIA](https://lofranotecnologia.com.br/).
