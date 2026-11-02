"""Grafo LangGraph do agente e cadeia de modelos com fallback."""

import logging
import os
import warnings

import httpx
import openai
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError, GoogleAPIError
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from prompts import system_message
from store import agora
from tools import ALL_TOOLS

# gemini-3.5-flash-lite ignora a temperatura; o aviso só atrapalharia a conversa no terminal.
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*")

logger = logging.getLogger(__name__)

FALLBACK_TEXT = (
    "Poxa, tive um problema técnico e não consegui responder agora. "
    "Tenta de novo em instantes ou fala com a equipe pelo WhatsApp (67) 3321-4500."
)
GROQ_URL = "https://api.groq.com/openai/v1"
TIMEOUT_SEGUNDOS = 30
MAX_RODADAS_DE_FERRAMENTAS = 4
RECURSION_LIMIT = 2 * MAX_RODADAS_DE_FERRAMENTAS + 4
# Só falhas de API acionam o modelo reserva; erro de programação deve aparecer.
# ValueError e TypeError: é assim que os SDKs reagem a uma resposta 200 malformada do provedor.
API_ERRORS = (
    ChatGoogleGenerativeAIError,
    GoogleAPIError,
    ContextOverflowError,
    openai.APIError,
    httpx.HTTPError,
    ValueError,
    TypeError,
)


class ConfigError(Exception):
    pass


def build_models(tools, env=os.environ) -> list[Runnable]:
    chave = env.get("GOOGLE_API_KEY")
    if not chave:
        raise ConfigError("Defina GOOGLE_API_KEY no arquivo .env (veja .env.example).")
    nomes = (
        env.get("GEMINI_MODEL") or "gemini-3.5-flash-lite",
        env.get("GEMINI_FALLBACK_MODEL") or "gemini-3.8-flash",
    )
    modelos = [
        ChatGoogleGenerativeAI(model=n, google_api_key=chave, temperature=0.2, max_retries=1, timeout=TIMEOUT_SEGUNDOS)
        for n in nomes
    ]
    if env.get("GROQ_API_KEY"):
        nomes_groq = (
            env.get("GROQ_MODEL") or "openai/gpt-oss-120b",
            env.get("GROQ_FALLBACK_MODEL") or "openai/gpt-oss-20b",
        )
        modelos += [
            ChatOpenAI(
                model=n,
                api_key=env["GROQ_API_KEY"],
                base_url=GROQ_URL,
                temperature=0.2,
                max_retries=1,
                timeout=TIMEOUT_SEGUNDOS,
            )
            for n in nomes_groq
        ]
    return [m.bind_tools(tools) for m in modelos]


def build_chain(models: list[Runnable]) -> Runnable:
    principal, *reservas = models
    return principal.with_fallbacks(reservas, exceptions_to_handle=API_ERRORS) if reservas else principal


def message_text(msg) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return "".join(
        b if isinstance(b, str) else b.get("text", "")
        for b in msg.content
        if isinstance(b, str) or b.get("type") == "text"
    )


def _rodadas_desde_o_cliente(mensagens) -> int:
    rodadas = 0
    for m in reversed(mensagens):
        if isinstance(m, HumanMessage):
            break
        rodadas += isinstance(m, AIMessage)
    return rodadas


def build_graph(chain: Runnable, checkpointer):
    def agente(state: MessagesState):
        mensagens = state["messages"]
        # Toda saída de erro vira mensagem final, para o histórico nunca ficar com chamada de ferramenta pendente.
        if _rodadas_desde_o_cliente(mensagens) > MAX_RODADAS_DE_FERRAMENTAS:
            return {"messages": [AIMessage(content=FALLBACK_TEXT)]}
        try:
            resposta = chain.invoke([SystemMessage(content=system_message(agora())), *mensagens])
        except API_ERRORS as erro:
            logger.warning("Todos os modelos falharam: %s", erro)
            return {"messages": [AIMessage(content=FALLBACK_TEXT)]}
        if not resposta.tool_calls and not message_text(resposta).strip():
            return {"messages": [AIMessage(content=FALLBACK_TEXT)]}
        return {"messages": [resposta]}

    grafo = StateGraph(MessagesState)
    grafo.add_node("agente", agente)
    grafo.add_node("ferramentas", ToolNode(ALL_TOOLS, handle_tool_errors=True))
    grafo.add_edge(START, "agente")
    grafo.add_conditional_edges("agente", tools_condition, {"tools": "ferramentas", END: END})
    grafo.add_edge("ferramentas", "agente")
    return grafo.compile(checkpointer=checkpointer)


def _resolver_ferramentas_interrompidas(graph, config) -> None:
    # Chamada sem resultado no histórico faz o provedor rejeitar todos os turnos seguintes.
    estado = graph.get_state(config)
    if estado.next:
        pendentes = estado.values["messages"][-1].tool_calls
        resultados = [ToolMessage(content="Consulta interrompida.", tool_call_id=c["id"]) for c in pendentes]
        graph.update_state(config, {"messages": resultados}, as_node="ferramentas")


def respond(graph, thread_id: str, text: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    _resolver_ferramentas_interrompidas(graph, config)
    anteriores = graph.get_state(config).values.get("messages", [])
    mensagens = graph.invoke({"messages": [HumanMessage(content=text)]}, config)["messages"]
    novas = mensagens[len(anteriores):]
    return {
        "texto": message_text(mensagens[-1]),
        "modelo": mensagens[-1].response_metadata.get("model_name"),
        "ferramentas": [
            {"nome": c["name"], "args": c["args"]}
            for m in novas
            if isinstance(m, AIMessage)
            for c in m.tool_calls
        ],
    }
