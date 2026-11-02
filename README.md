# Agente de atendimento da Empório da Música

Agente em Python que atende por texto os clientes da Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS. Ele responde sobre produtos, pedidos e políticas, consulta os dados antes de afirmar qualquer coisa e recusa com educação o que está fora do escopo.

Conversas reais estão em [`examples/`](examples/).

## Como rodar

Testado com Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Preencha o `.env`:

- `GOOGLE_API_KEY` (obrigatória): [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
- `GROQ_API_KEY` (opcional, ativa os dois últimos modelos de reserva): [console.groq.com/keys](https://console.groq.com/keys).

```bash
python cli.py                    # conversa interativa
python cli.py --thread ana       # cria ou retoma a conversa "ana", mesmo depois de fechar o programa
python cli.py --debug            # mostra ferramentas chamadas, modelo usado e falhas de API
python cli.py --replay examples/inputs/01-violoes-e-preco.txt --out saida.md   # gera uma transcrição
```

Sem `--thread`, cada execução começa uma conversa nova. Um thread guarda o contato e o pedido verificado de um único cliente, então não o reaproveite entre pessoas.

`AGENT_NOW` fixa data e hora, por exemplo `AGENT_NOW=2026-11-03T10:00:00`. Serve para reproduzir os exemplos em horário comercial.

### Tracing com LangSmith (opcional)

Para ver cada turno com chamadas de modelo, ferramentas, trocas de modelo e erros, crie uma chave em [smith.langchain.com](https://smith.langchain.com) e preencha o `.env`:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=sua_chave
LANGSMITH_PROJECT=emporio-da-musica
```

Os turnos de um mesmo `--thread` ficam agrupados em uma conversa. Conta na UE também precisa de `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com`. Com o tracing ligado, as conversas vão para um serviço externo, inclusive contatos e pedidos; `LANGSMITH_HIDE_INPUTS=true` e `LANGSMITH_HIDE_OUTPUTS=true` ocultam esse conteúdo. Os testes nunca enviam traces.

### Testes

```bash
python -m pytest                  # offline, não gasta cota
RUN_LIVE=1 python -m pytest tests/test_live.py   # modelos reais; no PowerShell: $env:RUN_LIVE=1
```

## Arquitetura

```text
START -> agente -> (pediu ferramenta? ferramentas -> agente : END)
```

| Arquivo | Responsabilidade |
|---|---|
| `store.py` | Lê os CSVs e concentra preço, disponibilidade, parcelas e verificação de pedido |
| `policies.py` | Extrai o manual em PDF e serve cada seção por tema |
| `tools.py` | As 5 ferramentas expostas ao modelo |
| `prompts.py` | Persona e regras de atendimento |
| `agent.py` | Grafo LangGraph e cadeia de modelos |
| `cli.py` | Conversa interativa e geração de transcrições |

O modelo decide o que consultar e como comunicar. Fatos e contas ficam em código determinístico.

## Decisões técnicas

**Fatos em código, não no modelo.** O manual proíbe informar preço, estoque ou prazo sem consultar o sistema, e um valor errado pode configurar propaganda enganosa. Por isso, preço final, PIX, parcelas, disponibilidade e contagem de dias são calculados em Python. A frase de pagamento também sai pronta da ferramenta, no campo `condicoes`, para o modelo não sugerir, por exemplo, que o valor do PIX pode ser parcelado.

**LangGraph.** O problema é um laço simples de agente com ferramentas, e o framework já traz esse laço, tratamento de erro de ferramenta e histórico persistente. Um único nó de agente basta; mais agentes só acrescentariam custo e pontos de falha.

**Ferramentas parametrizadas, sem SQL gerado por modelo.** Parâmetros fixos impedem consultas arbitrárias aos dados de clientes. Em `consultar_pedido`, pedido inexistente e contato errado devolvem a mesma resposta, para não revelar quais pedidos existem.

**Políticas por seção, sem banco vetorial.** São 8 páginas com seções bem delimitadas. Um tema escolhido em lista fechada devolve o trecho exato, sem infraestrutura de embeddings e sem risco de recuperar o parágrafo errado.

**Gemini como provedor.** Tem chamada de ferramentas nativa, camada gratuita suficiente para um protótipo e integração direta com o LangGraph. Os modelos ficam em variáveis de ambiente, então trocá-los não exige mudar código.

**Estratégia de prompt.** A mensagem de sistema traz persona e regras por situação, derivadas do §7 do manual, mas nenhum dado da loja: preços, estoque e políticas vêm sempre das ferramentas. As descrições das ferramentas dizem ao modelo quando usar cada uma. O prompt trata mensagens do cliente e resultados de ferramentas como dados, nunca como instruções, e foi ajustado com execuções reais. Quando a regra precisa valer sempre, ela sai do prompt e vai para o código, como aconteceu com a frase de pagamento.

**Tratamento dos dados.** Os CSVs são lidos a cada consulta, então uma edição vale na hora. A busca ignora acentos, maiúsculas e plural, e aceita código de modelo escrito de formas diferentes. O manual é extraído por seção, sem cabeçalhos e rodapés, e as contradições são corrigidas antes de chegar ao modelo, conforme as suposições abaixo.

**Cadeia de modelos.** Cada modelo só é acionado se o anterior falhar por erro de API (qualquer 4xx ou 5xx, rede, timeout de 30 s ou resposta malformada), nunca por qualidade de resposta:

1. `gemini-3.5-flash-lite`: principal, pela cota diária maior na camada gratuita.
2. `gemini-3.8-flash`: reserva do mesmo provedor, com cota diária pequena.
3. `openai/gpt-oss-120b` (Groq): outro provedor, para quando o Gemini inteiro falhar.
4. `openai/gpt-oss-20b` (Groq): modelo de produção com ferramentas e cota própria.

Se todos falharem, o cliente recebe uma mensagem amigável, a conversa continua depois e `--debug` mostra o erro. O Groq usa o cliente compatível com OpenAI, sem dependência a mais. A troca foi testada com modelos reais, nos dois sentidos, em conversas com ferramentas no histórico.

**Histórico em SQLite por `thread_id`.** Sobrevive ao fechamento do programa e não exige servidor. A mensagem de sistema fica fora do histórico e é remontada a cada chamada, para a data e o status da loja estarem sempre corretos.

**Tracing opcional.** O LangGraph já integra com o LangSmith por variáveis de ambiente, então não há código de instrumentação. Fica desligado por padrão porque envia dados de clientes para fora.

**CLI.** O desafio pede um agente por texto. A CLI mantém o foco no comportamento, e `--replay` gera os exemplos a partir de execuções reais.

## Suposições

- **Contatos:** telefone (67) 3341-4444, WhatsApp (67) 3321-4500 (§7) e e-mail `contato@emporiodamusica.com.br` (capa, sem acento, por ser um domínio mais plausível). O manual traz versões conflitantes.
- **Parcela mínima:** o §3.1 prevalece sobre a tabela, por ser mais específico: R$ 50 até 3x, R$ 80 de 4x a 6x, R$ 100 de 7x a 12x.
- **Arredondamento do PIX:** 5% sobre o preço de tabela. Valor com até dois decimais não muda, e qualquer fração além do centavo sobe para o centavo seguinte: 41,15 fica 41,15 e 41,152 vira 41,16.
- **Busca por categoria:** se o termo nomeia uma categoria da planilha, só produtos dela aparecem, mesmo que a descrição de outro cite a palavra.
- **Catálogo:** o manual cita mais de 300 instrumentos, e o CSV tem 65. Vale o CSV. Sopro e cordas orquestrais têm 0 produtos, e o agente diz que não há itens disponíveis no momento.
- **Promoções:** vale só `is_active = 1`. O CSV prevalece sobre o calendário do manual, inclusive para a Black Friday em novembro. Hoje há 4 promoções ativas, nenhuma de Black Friday.
- **Disponibilidade:** `status = active` e estoque maior que zero. `coming_soon` e `discontinued` nunca são vendáveis, mesmo com estoque.
- **Pedidos 3 e 20:** o total registrado difere da soma dos itens. O agente informa o total registrado, sem recalcular.
- **Previsão vencida:** o agente informa com transparência, passa o rastreio e oferece encaminhar à equipe. Os dados de pedido terminam em março de 2026.
- **Devolução:** não há data de recebimento nem canal de compra nos dados, então o agente pergunta. O arrependimento vale só para compra online.
- **Frete de exatamente R$ 500:** o manual não define o caso, então o agente encaminha.
- **Lojas parceiras:** não há lista, então o agente sugere procurar uma loja especializada, sem citar nomes.
- **Feriados:** não há calendário. O status "aberta" considera só dia da semana e horário.
- **Defeito depois de 30 dias:** o §4.2 manda acionar o fabricante, e o §8.1 dá garantia legal de 90 dias a partir do recebimento. O agente informa as duas coisas e oferece encaminhar.
- **Identidade:** número do pedido + telefone ou e-mail, pois o CSV não tem CPF.

## Conflitos no catálogo

Nos produtos 135, 136, 137, 139, 140, 142 e 144, nome, descrição e specs se contradizem. O 135, "Music Man", é descrito como "Fender Jazz Bass"; o 142, "Korg", é descrito como "Roland" de 88 teclas, com 61 nas specs.

O agente continua informando nome, preço e estoque, mas a descrição e as specs ficam fora da busca e da resposta, com `ficha_tecnica_indisponivel: true`. Se perguntarem detalhes, ele diz que não pode confirmar e oferece encaminhar. A lista é fixa porque foi revisada à mão; com dados reais, a correção seria na origem.

## Limitações conhecidas

- **Cota gratuita:** cada mensagem que usa ferramenta gasta ao menos duas requisições, e os limites gratuitos são baixos: o `gemini-3.8-flash` tem só 20 por dia. Por isso ele é reserva, não principal. Cada turno dos exemplos mostra o modelo que respondeu.
- **Latência:** nos testes, as respostas variaram de 3 s a 86 s. A camada gratuita oscila bastante, e com o Gemini sobrecarregado o tempo de espera e as tentativas de cada modelo se somam antes da troca.
- **Variação entre execuções:** a mesma pergunta pode gerar respostas diferentes. Regras no prompt reduzem esse risco, mas só o que está em código é garantido. Modelos reserva podem seguir pior o prompt.
- **Encaminhamento simulado:** `registrar_encaminhamento` grava em `runtime/handoffs.jsonl` e devolve um protocolo; não há equipe recebendo.
- **Identidade simplificada:** quem souber número do pedido e contato vê o pedido.
- **Histórico sem corte:** conversas muito longas podem exceder cota ou contexto.
- **Fora de escopo:** fazer pedidos, alterar dados, cotar frete para outras cidades e calcular carrinho com vários produtos.
- **Privacidade:** na camada gratuita, o conteúdo pode ser usado para melhorar produtos do provedor. É aceitável com dados fictícios; produção exigiria plano pago.

## Com mais tempo

- Avaliação automática com conversas de referência, para medir regressões a cada mudança de prompt ou modelo.
- Autenticação real e integração com WhatsApp.
- Banco de dados real no lugar dos CSVs, com correção dos conflitos na origem.
- Cálculo de vários produtos e calendário de feriados.
- Corte ou resumo de histórico longo.
- Painéis e alertas de custo, latência e taxa de fallback sobre os traces.

## Uso de assistentes de código

Usei o Claude Code em todo o projeto, com este fluxo:

1. **Análise:** leitura do enunciado, dos CSVs e do manual, que revelou as contradições e armadilhas listadas acima.
2. **Decisões:** debate das opções. Provedor, framework, escopo e fallback foram decisões minhas. As demais, como recomendar produtos a partir das descrições e os modelos do Groq, foram propostas pelo assistente e registradas no design.
3. **Design e plano:** documentos revisados antes de qualquer código, em [`docs/superpowers/`](docs/superpowers/).
4. **Implementação com TDD:** testes escritos antes do código, com um commit por etapa.
5. **Validação com modelos reais:** revelou o que os testes offline não pegavam. Erros 5xx do Gemini não acionavam o fallback, um modelo do Groq não estava disponível na conta e o agente prometeu Black Friday a partir do calendário do manual. Cada caso virou correção no código, no prompt ou em ambos.
6. **Revisão:** as transcrições foram conferidas contra os CSVs e o manual. Uma nova sessão do assistente, sem o contexto da implementação, revisou o projeto inteiro e apontou, por exemplo, que a conversa padrão herdava dados de pedido do cliente anterior; os problemas críticos e importantes foram corrigidos.

O assistente acelerou a implementação e a checagem dos dados; a validação com execuções reais continuou indispensável.
