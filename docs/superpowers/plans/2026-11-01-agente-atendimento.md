# Agente de atendimento da Empório da Música: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agente de atendimento por texto em Python que responde clientes consultando dados e políticas da loja, entregue em repositório público com README e conversas de exemplo.

**Architecture:** Grafo LangGraph (`agente <-> ToolNode`) com histórico em `SqliteSaver`. Fatos e cálculos ficam em código determinístico (`store.py`, `policies.py`), e o modelo só decide o que consultar e como comunicar. Modelos em cadeia com `with_fallbacks`.

**Tech Stack:** Python 3.11, `langgraph`, `langgraph-checkpoint-sqlite`, `langchain-google-genai`, `langchain-openai`, `pandas`, `pypdf`, `python-dotenv`, `tzdata`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-01-agente-atendimento-design.md`

**Ordem em relação à spec:** a validação dos modelos (passo 2 da spec) vira a Task 5, porque não há chaves ainda e só `build_models` depende dela. Se as chaves chegarem antes, rode a Task 5 antes.

## Global Constraints

- Código em módulos na raiz do projeto; sem pacote nem camadas extras.
- `.env`, `.venv/`, `runtime/`, `*.3mf` e `desafio_tecnico_ai_eng_artefact.pdf` nunca entram no git.
- Chaves só no `.env`; nunca no chat, em logs ou em transcrições.
- Fuso: `America/Campo_Grande`.
- Disponível: `status == active` e `stock_quantity > 0`.
- Promoção: só `is_active == 1`. PIX: 5% sobre preço de tabela, só sem promoção ativa.
- Parcelas: 1–3x mínimo R$ 50, 4–6x R$ 80, 7–12x R$ 100.
- Produtos com conflito: `{135, 136, 137, 139, 140, 142, 144}`.
- Exemplos e README refletem execuções reais; nada escrito à mão como se fosse saída do agente.
- Rodar comandos da raiz do projeto com `.venv/Scripts/python`.
- Abrir arquivos com `encoding="utf-8"`.

## Review Focus

- Cliente escreve "violões", "violao" ou "guitarra" (plural e sem acento): a busca encontra o produto. Teste na Task 1.
- Cliente informa o telefone como `+55 67 99654-7821` ou o pedido como `#8`: a verificação funciona; contato vazio nunca confere. Testes nas Tasks 1 e 3.
- Data de recebimento em `dd/mm/aaaa`, inválida ou futura: aceita o formato brasileiro e devolve erro claro nos outros casos. Teste na Task 3.
- Toda a cadeia de modelos falha, o modelo devolve resposta vazia ou o limite de iterações estoura: mensagem amigável, sem traceback. Teste na Task 4.
- Conversa com `content` em lista de blocos (formato do Gemini 3) ou Ctrl-C/EOF na CLI: texto extraído corretamente e saída limpa. Teste na Task 4.

---

### Task 1: Base do projeto e regras de negócio

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `store.py`, `tests/test_store.py`

**Interfaces:**
- Produces, em `store.py`:
  - `agora() -> datetime`: `AGENT_NOW` (ISO) se definido, senão o relógio real; sempre com fuso de Campo Grande.
  - `status_loja(dt: datetime) -> str`: contém `"aberta"` ou `"fechada"` e o próximo horário de abertura.
  - `max_parcelas(valor: float) -> int`
  - `search_products(termo=None, categoria=None, preco_min=None, preco_max=None, em_promocao=False) -> dict` com chaves `disponiveis`, `indisponiveis`, `alternativas`, `total_encontrado`.
  - `find_order(numero: str, contato: str, hoje: date) -> dict | None`
  - `CATEGORIAS: list[str]`

Item de produto: `id, nome, categoria, preco_tabela, promocao, desconto_percentual, preco_final, preco_pix, max_parcelas, estoque`, e ainda `descricao, specs` ou `ficha_tecnica_indisponivel: True`. Em `indisponiveis`, também `motivo` (`sem_estoque`, `descontinuado`, `em_breve`).

Pedido: `numero, cliente_primeiro_nome, status, itens [{nome, quantidade}], total_registrado, pagamento, rastreio, previsao, previsao_vencida, observacoes`. Campos vazios do CSV viram `None`.

- [ ] **Step 1: Criar a base**

`git init -b main`. `.gitignore` conforme Global Constraints, mais `__pycache__/`. `.env.example` com `GOOGLE_API_KEY=`, `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite`, `OPENROUTER_API_KEY=`, `OPENROUTER_MODEL=`, `AGENT_NOW=`. Criar `.venv`, instalar as dependências do Tech Stack nas versões atuais e fixá-las em `requirements.txt`.

- [ ] **Step 2: Escrever os testes**

```python
def ids(items): return {i["id"] for i in items}

def test_violoes_ate_1000():
    r = search_products(categoria="Violões", preco_max=1000)
    assert ids(r["disponiveis"]) == {81,82,83,84,85,86,87,88,89,91,107,112}
    assert r["indisponiveis"] == []  # filtro de preço não lista 96 nem 113

def test_termo_com_filtro_de_preco_nao_lista_indisponiveis():
    assert search_products(termo="violão", preco_max=1000)["indisponiveis"] == []

def test_takamine_promocao_inativa():
    p = search_products(termo="Takamine GD20")["disponiveis"][0]
    assert (p["id"], p["preco_final"], p["desconto_percentual"]) == (95, 2199.0, None)
    assert p["preco_pix"] == 2089.05 and p["max_parcelas"] == 12

def test_promocao_ativa_sem_pix():
    p = search_products(termo="Ohana CK-20")["disponiveis"][0]
    assert (p["preco_tabela"], p["desconto_percentual"], p["preco_final"], p["preco_pix"]) == (549.0, 20, 439.2, None)
    assert p["max_parcelas"] == 5

def test_lista_promocoes_ativas():
    assert ids(search_products(em_promocao=True)["disponiveis"]) == {127, 121, 90, 94}

def test_sem_estoque_com_alternativas():
    r = search_products(termo="Giannini GF-3D")
    assert r["disponiveis"] == [] and r["indisponiveis"][0]["motivo"] == "sem_estoque"
    assert ids(r["alternativas"]) == {107, 82, 86}

def test_status_vence_estoque():
    assert search_products(termo="Ibanez Bass")["indisponiveis"][0]["motivo"] == "descontinuado"
    assert search_products(termo="KA-ABP-CTG")["indisponiveis"][0]["motivo"] == "em_breve"

def test_conflito_fora_da_saida_e_da_busca():
    assert search_products(termo="Fender Jazz")["disponiveis"] == []
    p = search_products(termo="Music Man Bass 1X")["disponiveis"][0]
    assert p["ficha_tecnica_indisponivel"] is True and "descricao" not in p and "specs" not in p

@pytest.mark.parametrize("termo", ["violões", "violao", "VIOLÃO"])
def test_busca_tolera_plural_e_acento(termo):
    assert search_products(termo=termo)["total_encontrado"] > 0

def test_guitarra_singular_encontra_categoria():
    assert 131 in ids(search_products(termo="guitarra")["disponiveis"])

def test_busca_sem_resultado():
    r = search_products(termo="saxofone")
    assert r["disponiveis"] == r["indisponiveis"] == r["alternativas"] == []

@pytest.mark.parametrize("valor,n", [(159.9,3),(323.1,4),(439.2,5),(1199,11),(2199,12),(40,1)])
def test_max_parcelas(valor, n):
    assert max_parcelas(valor) == n

@pytest.mark.parametrize("contato", ["(67) 99654-7821", "+55 67 99654-7821", "ANACAROL.FERREIRA@coldmail.com"])
def test_pedido_contato_certo(contato):
    o = find_order("8", contato, date(2026, 11, 1))
    assert o["rastreio"] == "BRJL5544332BR" and o["previsao_vencida"] is True
    assert o["cliente_primeiro_nome"] == "Ana" and o["itens"][0]["nome"] == "Kala KA-C Concert Mogno"

@pytest.mark.parametrize("numero,contato", [("8","(67) 90000-0000"),("8",""),("8","   "),("999","(67) 99654-7821"),("abc","(67) 99654-7821")])
def test_pedido_negado(numero, contato):
    assert find_order(numero, contato, date(2026, 11, 1)) is None

def test_previsao_vencida_so_em_shipped():
    assert find_order("1", "(67) 98432-1098", date(2026, 11, 1))["previsao_vencida"] is False

@pytest.mark.parametrize("dt,esperado", [
    ("2026-11-01T10:00", "fechada"),   # domingo
    ("2026-11-02T08:59", "fechada"),
    ("2026-11-02T09:00", "aberta"),
    ("2026-11-07T12:59", "aberta"),    # sábado
    ("2026-11-07T13:00", "fechada"),
])
def test_status_loja(dt, esperado):
    assert esperado in status_loja(datetime.fromisoformat(dt).replace(tzinfo=TZ))

def test_status_loja_informa_reabertura():
    s = status_loja(datetime.fromisoformat("2026-11-07T13:00").replace(tzinfo=TZ))
    assert "segunda" in s and "09:00" in s
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -q`
Expected: erro de importação de `store`.

- [ ] **Step 4: Implementar `store.py`**

Lê os CSVs a cada chamada, a partir de `data/desafio_tecnico_ai_eng - <tabela>.csv`. A normalização de busca remove acentos e caixa e reduz cada palavra (`oes` final vira `ao`; `s` final sai), nos dois lados. Um produto casa se todos os tokens do termo estão em nome + categoria + descrição + specs; nos produtos com conflito, só nome + categoria. Ordene por `preco_final` e limite cada lista a 15 itens, mantendo `total_encontrado`.

`indisponiveis` só é preenchido quando há `termo` sem `preco_min`, `preco_max` nem `em_promocao`. `alternativas` só quando há indisponíveis e nenhum disponível: mesma categoria, disponíveis, 3 de preço mais próximo. Com várias promoções ativas no mesmo produto, usar o maior desconto. Telefone: só dígitos, sem `55` inicial quando sobrarem mais de 11. Marcar `CONFLITO_CATALOGO` com `# shortcut: lista revisada à mão, corrigir na origem com dados reais`.

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -q`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example requirements.txt store.py tests/test_store.py data docs
git commit -m "feat: add catalog, order and pricing rules"
```

### Task 2: Políticas

**Files:**
- Create: `policies.py`, `tests/test_policies.py`

**Interfaces:**
- Produces: `TEMAS: dict[str, str]` e `get_policy(tema: str) -> str` em `policies.py`.

`TEMAS` mapeia para títulos exatos: `loja`="1. Sobre a Empório da Música", `horarios`="2. Horário de Funcionamento", `pagamento`="3. Formas de Pagamento", `trocas_devolucoes`="4. Política de Trocas e Devoluções", `frete`="5. Política de Frete e Entregas", `promocoes`="6. Promoções e Descontos", `garantia`="8. Garantia", `privacidade`="9. Privacidade e Proteção de Dados".

- [ ] **Step 1: Escrever os testes**

```python
def test_temas_cobrem_conteudo():
    assert "7 (sete) dias corridos" in get_policy("trocas_devolucoes")
    assert "Rua 14 de Maio, 3200" in get_policy("loja")
    assert "09:00 às 13:00" in get_policy("horarios")
    assert "BR4K7M2X9P1BR" in get_policy("frete")  # seção que atravessa páginas
    assert "90" in get_policy("garantia") and "LGPD" in get_policy("privacidade")

def test_sem_cabecalho_rodape_nem_secoes_internas():
    todas = " ".join(get_policy(t) for t in TEMAS)
    assert "Página " not in todas and "Manual de Políticas" not in todas
    assert "Saudação:" not in todas and "Tom de voz" not in todas

def test_contradicoes_corrigidas():
    loja, pag = get_policy("loja"), get_policy("pagamento")
    assert "contato@emporiodamusica.com.br" in loja and "empóriodamusica" not in loja
    assert "(67) 3321-4500" in loja
    assert "exceto abaixo" not in pag and "R$ 50,00" in pag
    assert "Parcela mínima de R$ 100,00" not in pag.split("3.1")[0]

def test_tema_invalido():
    with pytest.raises(KeyError):
        get_policy("astrologia")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_policies.py -q`
Expected: erro de importação de `policies`.

- [ ] **Step 3: Implementar `policies.py`**

Localize o PDF com `glob("data/pol*.pdf")`, porque o acento do nome pode variar no git. Extraia com `pypdf` uma vez (`lru_cache`), remova as linhas de cabeçalho e rodapé, e corte pelos títulos exatos, inclusive "7. Atendimento via WhatsApp" e "10. Disposições Finais" como delimitadores. Não use regex genérica de `^\d+\.`: a lista do §7.2 tem linhas como "3. Consulta:". Aplique as correções com `re.sub` tolerante a espaços e quebras de linha.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_policies.py -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add policies.py tests/test_policies.py
git commit -m "feat: serve store policies by topic"
```

### Task 3: Ferramentas do agente

**Files:**
- Create: `tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `search_products`, `find_order`, `agora`, `CATEGORIAS`, `get_policy`, `TEMAS`.
- Produces: `ALL_TOOLS: list[BaseTool]` em `tools.py`, com `buscar_produtos`, `consultar_pedido`, `consultar_politicas`, `dias_corridos_desde`, `registrar_encaminhamento`, e a constante `HANDOFF_PATH = Path("runtime/handoffs.jsonl")`.

`categoria` e `tema` são `Literal`, para virarem enum no schema. Retornos estruturados em JSON com `ensure_ascii=False`. Docstrings em português dizem quando usar cada ferramenta, pois são lidas pelo modelo.

- [ ] **Step 1: Escrever os testes**

```python
NAO_VERIFICADO = {"verificado": False}

def test_pedido_inexistente_e_contato_errado_sao_iguais():
    a = consultar_pedido.invoke({"numero": "8", "contato": "(67) 90000-0000"})
    b = consultar_pedido.invoke({"numero": "999", "contato": "(67) 90000-0000"})
    assert a == b and "Ana" not in a and "BRJL" not in a

@pytest.mark.parametrize("numero", ["8", "#8", "pedido 8"])
def test_formatos_do_numero(numero):
    assert "BRJL5544332BR" in consultar_pedido.invoke({"numero": numero, "contato": "(67) 99654-7821"})

@pytest.mark.parametrize("data", ["28/10/2026", "2026-10-28"])
def test_dias_corridos(monkeypatch, data):
    monkeypatch.setenv("AGENT_NOW", "2026-11-02T10:00")
    assert json.loads(dias_corridos_desde.invoke({"data": data}))["dias"] == 5

@pytest.mark.parametrize("data", ["ontem", "31/02/2026", "10/10/2030"])
def test_data_invalida_ou_futura(monkeypatch, data):
    monkeypatch.setenv("AGENT_NOW", "2026-11-02T10:00")
    assert "erro" in json.loads(dias_corridos_desde.invoke({"data": data}))

def test_encaminhamento_grava_e_devolve_protocolo(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(tools, "HANDOFF_PATH", path)
    r = json.loads(registrar_encaminhamento.invoke({"motivo": "reclamacao", "resumo": "x", "contato": "y"}))
    assert r["protocolo"] and json.loads(path.read_text(encoding="utf-8"))["protocolo"] == r["protocolo"]
    assert "24 horas úteis" in r["prazo_retorno"]

def test_schema_tem_enum_de_tema_e_categoria():
    assert "frete" in str(consultar_politicas.args) and "Violões" in str(buscar_produtos.args)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_tools.py -q`
Expected: erro de importação de `tools`.

- [ ] **Step 3: Implementar `tools.py`**

`consultar_pedido` extrai os dígitos de `numero` e devolve `{"verificado": false, "mensagem": ...}` em qualquer falha, com texto único. `registrar_encaminhamento` cria o diretório, acrescenta uma linha JSONL e devolve protocolo `EM-AAAAMMDD-xxxx` e `prazo_retorno` "24 horas úteis".

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_tools.py -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: expose agent tools with order verification"
```

### Task 4: Prompt, grafo, fallback e CLI

**Files:**
- Create: `prompts.py`, `agent.py`, `cli.py`, `tests/test_agent.py`

**Interfaces:**
- Consumes: `ALL_TOOLS`, `agora`, `status_loja`.
- Produces:
  - `prompts.system_message(dt: datetime) -> str`
  - `agent.build_models(tools, env=os.environ) -> list[Runnable]`: levanta `ConfigError` sem `GOOGLE_API_KEY`; o elo OpenRouter só entra com `OPENROUTER_API_KEY` e `OPENROUTER_MODEL`.
  - `agent.build_chain(models: list[Runnable]) -> Runnable`
  - `agent.build_graph(chain, checkpointer) -> CompiledGraph`
  - `agent.message_text(msg) -> str`
  - `agent.respond(graph, thread_id: str, text: str) -> dict` com `texto`, `modelo`, `ferramentas`; nunca levanta exceção de modelo ou limite, devolve `FALLBACK_TEXT`.
  - `cli.py`: `--thread ID` (padrão `cliente`), `--debug`, `--replay entrada.txt --out saida.md`.

O prompt segue a seção "Prompt" da spec, mais a regra dos produtos com `ficha_tecnica_indisponivel` e os contatos definidos. A mensagem de sistema é montada a cada chamada e não é gravada no estado. `recursion_limit` é 10. Checkpoint em `runtime/checkpoints.sqlite`. `modelo` vem de `response_metadata`.

- [ ] **Step 1: Escrever os testes**

Modelos falsos são `RunnableLambda` que devolvem `AIMessage` em sequência ou levantam erro.

```python
def test_laco_chama_ferramenta_e_responde():
    # 1a resposta com tool_call de consultar_politicas(tema="horarios"), 2a com texto
    r = respond(build_graph(seq_model, MemorySaver()), "t1", "Qual o horário?")
    assert r["texto"] == "resposta final" and r["ferramentas"][0]["nome"] == "consultar_politicas"

def test_sistema_atualizado_a_cada_chamada_e_fora_do_estado(monkeypatch):
    # captura as mensagens recebidas pelo modelo falso
    assert isinstance(capturadas[0], SystemMessage)
    assert not any(isinstance(m, SystemMessage) for m in graph.get_state(cfg).values["messages"])

def test_fallback_em_erro_de_api():
    r = respond(build_graph(build_chain([model_que_levanta_429, model_ok]), MemorySaver()), "t", "oi")
    assert r["texto"] == "ok do reserva"

def test_cadeia_inteira_falha_da_mensagem_amigavel():
    assert respond(build_graph(build_chain([model_que_levanta_429]), MemorySaver()), "t", "oi")["texto"] == FALLBACK_TEXT

def test_resposta_vazia_da_mensagem_amigavel():
    assert respond(build_graph(modelo_vazio, MemorySaver()), "t", "oi")["texto"] == FALLBACK_TEXT

def test_laco_infinito_da_mensagem_amigavel():
    assert respond(build_graph(modelo_sempre_tool_call, MemorySaver()), "t", "oi")["texto"] == FALLBACK_TEXT

def test_texto_de_blocos():
    assert message_text(AIMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])) == "ab"

def test_historico_sobrevive_a_reabertura(tmp_path):
    # SqliteSaver em tmp_path; fecha a conexão, reabre e confere 2 mensagens humanas no thread

def test_build_models_exige_chave_e_opcional_openrouter():
    with pytest.raises(ConfigError): build_models(ALL_TOOLS, {})
    assert len(build_models(ALL_TOOLS, {"GOOGLE_API_KEY": "x"})) == 2
    assert len(build_models(ALL_TOOLS, {"GOOGLE_API_KEY": "x", "OPENROUTER_API_KEY": "y", "OPENROUTER_MODEL": "m"})) == 3

def test_prompt_traz_data_e_status():
    s = system_message(datetime(2026, 11, 1, 10, tzinfo=TZ))
    assert "01/11/2026" in s and "fechada" in s and "Sua música começa aqui" in s

def test_cli_replay_gera_transcricao(tmp_path):
    # chama cli.run_replay(graph_falso, entrada, saida): cada linha vira um turno
    # a saída contém "**Cliente:**", "**Assistente" e o nome da ferramenta chamada

def test_cli_interativa_sai_limpo_em_eof():
    # stdin vazio: cli.run_chat retorna sem exceção
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_agent.py -q`
Expected: erro de importação.

- [ ] **Step 3: Implementar `prompts.py`, `agent.py` e `cli.py`**

`with_fallbacks` só com as classes de erro de API, e não com `Exception`; confirme as classes na Task 5. `ToolNode(ALL_TOOLS, handle_tool_errors=True)`. A CLI faz `sys.stdout.reconfigure(encoding="utf-8")`, carrega `.env`, mostra mensagem clara em `ConfigError` (saída 2) e sai limpo em EOF e `KeyboardInterrupt`.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add prompts.py agent.py cli.py tests/test_agent.py
git commit -m "feat: add LangGraph agent with model fallback and CLI"
```

### Task 5: Validar modelos reais e ajustar o prompt

**Bloqueio:** precisa de `GOOGLE_API_KEY` e `OPENROUTER_API_KEY` no `.env`, além de `OPENROUTER_MODEL` (modelo gratuito com ferramentas). Peça ao usuário e pare até tê-las.

**Files:**
- Create: `tests/test_live.py`
- Modify: `agent.py` (classes de erro), `prompts.py`, `.env.example` (IDs confirmados)

- [ ] **Step 1: Confirmar cada elo com uma ferramenta**

Invoque cada modelo de `build_models` com "Qual o horário da loja?" e confira `tool_calls` e o formato de `content`. Confira no AI Studio se `GEMINI_FALLBACK_MODEL` tem limite maior; se não, peça ao usuário outro ID. Ajuste as classes de erro em `build_chain` com um ID inválido e com a mensagem real de 429.

- [ ] **Step 2: Escrever `tests/test_live.py`**

Pula sem `GOOGLE_API_KEY`. Confere a ferramenta chamada: "Quanto custa o Takamine GD20?" -> `buscar_produtos`; "Posso devolver minha compra?" -> `consultar_politicas`; "Cadê o pedido 8? Meu telefone é (67) 99654-7821" -> `consultar_pedido`; "Qual a capital da França?" -> nenhuma; "Vocês têm violões até R$ 1000?" -> `buscar_produtos`.

Run: `.venv/Scripts/python -m pytest tests/test_live.py -q`
Expected: 5 passam.

- [ ] **Step 3: Testar a troca real de provedor**

Numa conversa com ferramentas no histórico, defina `GEMINI_MODEL` e `GEMINI_FALLBACK_MODEL` como IDs inválidos e continue no mesmo `--thread --debug`.
Expected: o modelo OpenRouter responde sem erro de formato do histórico. Se falhar, conserte e adicione o caso aos testes; se não houver conserto simples, registre nas limitações.

- [ ] **Step 4: Ajustar o prompt com as perguntas do enunciado e dos 5 exemplos**

Corrija o que violar as regras, em poucas execuções, para preservar cota.
Expected: nenhuma resposta contraria a seção "Fracasso, mesmo funcionando" da spec.

- [ ] **Step 5: Commit**

```bash
git add agent.py prompts.py .env.example tests/test_live.py
git commit -m "test: validate model chain and tune prompt on live runs"
```

### Task 6: Conversas de exemplo

**Files:**
- Create: `examples/inputs/0[1-5]-*.txt`, `examples/0[1-5]-*.md`

- [ ] **Step 1: Escrever as entradas dos 5 cenários**

Use os cenários da seção "Conversas de exemplo" da spec, em threads novos e separados.

- [ ] **Step 2: Capturar com o modelo principal**

Run, para cada cenário, com `AGENT_NOW=2026-11-03T10:00:00`: `.venv/Scripts/python cli.py --thread ex-NN --replay examples/inputs/NN-x.txt --out examples/NN-x.md`
Expected: todos os turnos respondidos por `GEMINI_MODEL`, conferido no campo de modelo da transcrição. Se a resposta for `FALLBACK_TEXT` ou vier de outro modelo, recapture.

- [ ] **Step 3: Conferir cada transcrição contra os CSVs e o manual**

Expected: exemplo 1 sem 96 e 113, Takamine R$ 2.199,00; exemplo 3 nega contato errado e mostra `BRJL5544332BR`; exemplo 4 pergunta canal e data; exemplo 5 mostra R$ 549,00, 20%, R$ 439,20 e sem PIX adicional. Nenhuma linha editada à mão.

- [ ] **Step 4: Commit**

```bash
git add examples
git commit -m "docs: add captured agent conversations"
```

### Task 7: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Escrever o README em português**

Seções: como rodar (venv, `.env`, comandos, onde obter chaves, testes); arquitetura; decisões com justificativa (LangGraph, Gemini, cadeia de fallback, ferramentas parametrizadas sem SQL, políticas por seção sem vetores, prompt, histórico SQLite, CLI); todas as "Suposições" e os "Conflitos no catálogo" da spec; divergências do manual e dos dados; limitações (identidade simplificada, encaminhamento simulado, histórico sem corte, carrinho, feriados, frete, cotas e privacidade da camada gratuita, qualidade nos modelos reserva); o que faria com mais tempo; uso de assistentes de código, descrevendo o fluxo real desta sessão com Claude Code (análise, debate de decisões, revisão do design, plano, TDD); link para os exemplos.

- [ ] **Step 2: Instalar do zero seguindo só o README**

Em venv novo, execute os comandos do README.
Expected: `pytest` passa e a CLI responde "Qual o endereço da loja?" com Rua 14 de Maio, 3200.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with decisions and limitations"
```

### Task 8: Publicação

**Bloqueio:** criar repositório público é ação externa. Peça confirmação explícita ao usuário e o horário exato do prazo antes de qualquer passo abaixo.

- [ ] **Step 1: Conferir o que será publicado**

Run: `git ls-files` e `git log --oneline`
Expected: sem `.env`, `runtime/`, `.3mf` nem PDF do enunciado; commits progressivos. Busque padrões de chave no histórico com `git log -p | grep -E "AIza|sk-or-"`, sem resultado.

- [ ] **Step 2: Publicar**

Run: `gh repo create emporio-da-musica-agente --public --source . --push`
Expected: URL do repositório. Abra-a e confira README e exemplos. Sem force-push.

- [ ] **Step 3: Entregar o link ao usuário**

O usuário responde o e-mail da Artefact. Lembre: não alterar nada após o prazo.
