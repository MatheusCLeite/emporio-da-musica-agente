import io
import sqlite3
from datetime import datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

import cli
from agent import FALLBACK_TEXT, ConfigError, build_chain, build_graph, build_models, message_text, respond
from prompts import system_message
from store import TZ
from tools import ALL_TOOLS


def chamada(nome="consultar_politicas", args=None, id_="c1"):
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args or {"tema": "horarios"}, "id": id_}])


def modelo_em_sequencia(*respostas, capturadas=None):
    fila = list(respostas)

    def responder(mensagens):
        if capturadas is not None:
            capturadas.append(mensagens)
        return fila.pop(0)

    return RunnableLambda(responder)


def modelo_429():
    def falhar(_):
        raise ChatGoogleGenerativeAIError("429 RESOURCE_EXHAUSTED")

    return RunnableLambda(falhar)


def test_laco_chama_ferramenta_e_responde():
    modelo = modelo_em_sequencia(chamada(), AIMessage(content="resposta final"))
    r = respond(build_graph(modelo, MemorySaver()), "t1", "Qual o horário?")
    assert r["texto"] == "resposta final" and r["ferramentas"][0]["nome"] == "consultar_politicas"


def test_sistema_atualizado_a_cada_chamada_e_fora_do_estado():
    capturadas = []
    graph = build_graph(modelo_em_sequencia(AIMessage(content="oi"), capturadas=capturadas), MemorySaver())
    respond(graph, "t1", "oi")
    assert isinstance(capturadas[0][0], SystemMessage)
    estado = graph.get_state({"configurable": {"thread_id": "t1"}}).values["messages"]
    assert not any(isinstance(m, SystemMessage) for m in estado)


def test_fallback_em_erro_de_api():
    reserva = modelo_em_sequencia(AIMessage(content="ok do reserva"))
    r = respond(build_graph(build_chain([modelo_429(), reserva]), MemorySaver()), "t", "oi")
    assert r["texto"] == "ok do reserva"


def test_erro_de_programacao_nao_aciona_reserva():
    def quebrar(_):
        raise KeyError("bug")

    reserva = modelo_em_sequencia(AIMessage(content="não deveria"))
    with pytest.raises(KeyError):
        build_chain([RunnableLambda(quebrar), reserva]).invoke([HumanMessage(content="oi")])


def test_cadeia_inteira_falha_da_mensagem_amigavel():
    r = respond(build_graph(build_chain([modelo_429()]), MemorySaver()), "t", "oi")
    assert r["texto"] == FALLBACK_TEXT


def test_conversa_continua_depois_de_falha():
    modelo = RunnableLambda(lambda _, fila=[ChatGoogleGenerativeAIError("429"), AIMessage(content="voltei")]: _responder_ou_falhar(fila))
    graph = build_graph(modelo, MemorySaver())
    assert respond(graph, "t", "oi")["texto"] == FALLBACK_TEXT
    assert respond(graph, "t", "oi de novo")["texto"] == "voltei"


def _responder_ou_falhar(fila):
    item = fila.pop(0)
    if isinstance(item, Exception):
        raise item
    return item


def test_resposta_vazia_da_mensagem_amigavel():
    r = respond(build_graph(modelo_em_sequencia(AIMessage(content="")), MemorySaver()), "t", "oi")
    assert r["texto"] == FALLBACK_TEXT


def test_laco_infinito_da_mensagem_amigavel_e_estado_limpo():
    graph = build_graph(RunnableLambda(lambda _: chamada()), MemorySaver())
    assert respond(graph, "t", "oi")["texto"] == FALLBACK_TEXT
    ultima = graph.get_state({"configurable": {"thread_id": "t"}}).values["messages"][-1]
    assert isinstance(ultima, AIMessage) and not ultima.tool_calls


def test_texto_de_blocos():
    msg = AIMessage(content=[{"type": "text", "text": "a"}, {"type": "thinking", "text": "x"}, {"type": "text", "text": "b"}])
    assert message_text(msg) == "ab"


def test_historico_sobrevive_a_reabertura(tmp_path):
    caminho = tmp_path / "c.sqlite"
    for texto in ("primeira", "segunda"):
        conexao = sqlite3.connect(caminho, check_same_thread=False)
        graph = build_graph(modelo_em_sequencia(AIMessage(content="ok")), SqliteSaver(conexao))
        respond(graph, "t", texto)
        estado = graph.get_state({"configurable": {"thread_id": "t"}}).values["messages"]
        conexao.close()
    assert [m.content for m in estado if isinstance(m, HumanMessage)] == ["primeira", "segunda"]


def test_build_models_exige_chave_gemini():
    with pytest.raises(ConfigError):
        build_models(ALL_TOOLS, {})
    assert len(build_models(ALL_TOOLS, {"GOOGLE_API_KEY": "x"})) == 2


def test_build_models_acrescenta_groq_depois_dos_gemini():
    modelos = build_models(ALL_TOOLS, {"GOOGLE_API_KEY": "x", "GROQ_API_KEY": "y"})
    groq = [m.bound for m in modelos[2:]]
    assert [m.model_name for m in groq] == ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]
    assert {m.openai_api_base for m in groq} == {"https://api.groq.com/openai/v1"}


def test_build_models_aceita_trocar_modelos_groq():
    env = {"GOOGLE_API_KEY": "x", "GROQ_API_KEY": "y", "GROQ_MODEL": "a", "GROQ_FALLBACK_MODEL": "b"}
    assert [m.bound.model_name for m in build_models(ALL_TOOLS, env)[2:]] == ["a", "b"]


def test_prompt_traz_data_e_status():
    s = system_message(datetime(2026, 11, 1, 10, tzinfo=TZ))
    assert "01/11/2026" in s and "fechada" in s and "Sua música começa aqui" in s


def test_cli_replay_gera_transcricao(tmp_path):
    entrada = tmp_path / "e.txt"
    entrada.write_text("Qual o horário?\n\n", encoding="utf-8")
    saida = tmp_path / "s.md"
    graph = build_graph(modelo_em_sequencia(chamada(), AIMessage(content="das 9 às 18")), MemorySaver())
    cli.run_replay(graph, "t", entrada, saida)
    texto = saida.read_text(encoding="utf-8")
    assert "**Cliente:** Qual o horário?" in texto and "**Assistente" in texto
    assert "consultar_politicas" in texto and "das 9 às 18" in texto


def test_cli_interativa_sai_limpo_em_eof(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    cli.run_chat(build_graph(modelo_em_sequencia(), MemorySaver()), "t", debug=False)
