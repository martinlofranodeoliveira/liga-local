# Calendário e tabela

## Circle method prescrito

1. Copiar os IDs na ordem dos participantes. Se a quantidade for ímpar, acrescentar `null` no fim. Chamar o tamanho resultante de `m`.
2. Para cada rodada de índice `r`, começando em zero, emparelhar as posições `i` e `m - 1 - i`, para `i` de zero a `m / 2 - 1`.
3. Se um membro do par for `null`, o outro tem folga. Caso contrário, o primeiro é mandante quando `(r + i) % 2 == 0`; quando ímpar, inverter casa e fora.
4. Numerar apenas os jogos reais, a partir de 1, na ordem desses pares. O ID é `r{rodada:03d}-m{posição:03d}`. Rodadas também começam em 1.
5. Rotacionar para `[ids[0], ids[-1], *ids[1:-1]]` e repetir até completar `m - 1` rodadas.

No returno, copiar o primeiro turno com casa e fora invertidos, mantendo as folgas e atribuindo números de rodada e IDs novos. O calendário é determinístico para a mesma ordem de IDs. Cada par se encontra uma vez por turno. Uma folga não gera partida, pontos ou estatísticas.

Para os quatro participantes de `examples/participantes.csv`, o turno simples é:

| Rodada | Jogo 1 | Jogo 2 |
| --- | --- | --- |
| 1 | Aurora × Duna | Cedro × Brisa |
| 2 | Cedro × Aurora | Duna × Brisa |
| 3 | Aurora × Brisa | Duna × Cedro |

Brisa joga as três partidas fora nesse exemplo. Isso decorre da regra de orientação prescrita; o turno simples não busca equilíbrio perfeito de mandos. O returno espelha todos os jogos e equilibra cada confronto.

## Classificação

Somente partidas com placar contam como disputadas. O empate 0 a 0 é um resultado; um placar `null` é pendente. Resultados podem ser informados em qualquer ordem de rodada.

Para cada participante, calcular jogos, vitórias, empates, derrotas, gols a favor, gols contra, saldo e pontos. Ordenar por `(pontos, saldo, gols a favor, vitórias)` decrescente. IDs crescentes ordenam apenas a exibição quando essas métricas são iguais.

A posição é competitiva: se dois participantes empatam no primeiro lugar, ambos recebem 1 e o seguinte recebe 3. O ID não modifica essa posição. Não são usados confronto direto, sorteio, disciplina ou critérios inferidos.

## Integridade

Uma liga carregada é validada contra uma reconstrução completa desse calendário. Alterações de IDs, ordem dos participantes, rodadas, folgas ou confrontos são recusadas. Os placares são a parte variável. Para começar com outro grupo ou outra ordem de participantes, crie uma liga nova.
