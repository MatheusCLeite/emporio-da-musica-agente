"""Grafo LangGraph do agente e cadeia de modelos com fallback."""

import os

import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from prompts import system_message
from store import agora
from tools import ALL_TOOLS

FALLBACK_TEXT = (
    "Poxa, tive um problema técnico e não consegui responder agora. "
    "Tenta de novo em instantes ou fala com a equipe pelo WhatsApp (67) 3321-4500."
)
OPENROUTER_URL = "https://openrouter.ai/api/v1"
MAX_RODADAS_DE_FERRAMENTAS = 4
RECURSION_LIMIT = 2 * MAX_RODADAS_DE_FERRAMENTAS + 2
# Só falhas de API acionam o modelo reserva; erro de programação deve aparecer.
API_ERRORS = (ChatGoogleGenerativeAIError, openai.APIError)


class ConfigError(Exception):
    pass


def build_models(tools, env=os.environ) -> list[Runnable]:
    chave = env.get("GOOGLE_API_KEY")
    if not chave:
        raise ConfigError("Defina GOOGLE_API_KEY no arquivo .env (veja .env.example).")
    nomes = (
        env.get("GEMINI_MODEL") or "gemini-3.8-flash",
        env.get("GEMINI_FALLBACK_MODEL") or "gemini-3.5-flash-lite",
    )
    modelos = [ChatGoogleGenerativeAI(model=n, google_api_key=chave, temperature=0.2, max_retries=1) for n in nomes]
    if env.get("OPENROUTER_API_KEY") and env.get("OPENROUTER_MODEL"):
        modelos.append(
            ChatOpenAI(
                model=env["OPENROUTER_MODEL"],
                api_key=env["OPENROUTER_API_KEY"],
                base_url=OPENROUTER_URL,
                temperature=0.2,
                max_retries=1,
            )
        )
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
        if _rodadas_desde_o_cliente(mensagens) >= MAX_RODADAS_DE_FERRAMENTAS:
            return {"messages": [AIMessage(content=FALLBACK_TEXT)]}
        try:
            resposta = chain.invoke([SystemMessage(content=system_message(agora())), *mensagens])
        except API_ERRORS:
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


def respond(graph, thread_id: str, text: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
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
