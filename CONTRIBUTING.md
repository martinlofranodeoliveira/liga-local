# Contribuir

Use Python 3.11 ou posterior. O runtime usa somente a biblioteca padrão; ferramentas de build são separadas. Mantenha mensagens e documentação em português e todos os dados de exemplo fictícios.

## Executar os testes

Para uma execução rápida no ambiente virtual:

```sh
python -m pip install .
python -m unittest discover -s tests -v
```

Para verificar o artefato instalado em um ambiente isolado Linux, instale `bubblewrap` e `util-linux`, além de `setuptools` e `wheel` no Python de desenvolvimento, e execute:

```sh
python -B scripts/check.py
```

O script constrói um wheel de uma cópia do projeto, instala-o sem rede em um venv e roda os testes contra esse pacote instalado. A sandbox mantém fontes e ferramentas somente para leitura, sem rede, credenciais ou home do usuário, com capacidades removidas e `NoNewPrivs`. Dependendo da política de user namespaces da máquina, o administrador pode precisar preparar o ambiente. A CI executa o check em Python 3.11, 3.12, 3.13 e 3.14.

## O que preservar

- A API pública e os códigos estáveis de erro; mensagens não devem ecoar entradas.
- Funções puras e validação estrita, inclusive de subclasses, booleanos em inteiros, chaves extras e calendário alterado.
- Importação CSV integral: nenhum resultado parcial em caso de erro.
- Publicação por hard link sem sobrescrever destinos; leitura limitada de arquivos regulares sem seguir o symlink final.
- Determinismo: sem hora real, aleatoriedade no calendário ou acesso à rede.

Inclua testes de comportamento para mudanças relevantes e atualize a documentação quando alterar a API ou o formato. A regra de orientação do calendário é intencional, inclusive seu desequilíbrio possível de mandos no turno simples. Mudanças nessa regra exigem uma decisão explícita sobre compatibilidade.

Não inclua dados pessoais, credenciais, resultados reais ou artefatos de ambiente no pacote. Relate problemas com um exemplo fictício mínimo, o comando usado e o código de erro, removendo caminhos e dados privados.
