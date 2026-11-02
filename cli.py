"""Interface de linha de comando do agente: conversa interativa e geração de transcrições."""

import argparse
import logging
import sqlite3
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.checkpoint.sqlite import SqliteSaver

from agent import FALLBACK_TEXT, ConfigError, build_chain, build_graph, build_models, respond
from tools import ALL_TOOLS

CHECKPOINTS = Path(__file__).resolve().parent / "runtime" / "checkpoints.sqlite"
logger = logging.getLogger(__name__)


def run_chat(graph, thread: str, debug: bool) -> None:
    print("Empório da Música. Sua música começa aqui. (Ctrl+C para sair)")
    while True:
        try:
            texto = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not texto:
            continue
        try:
            resposta = respond(graph, thread, texto)
        except KeyboardInterrupt:
            print()
            return
        except Exception:
            # O cliente nunca vê traceback; o detalhe aparece com --debug.
            logger.exception("Falha ao responder")
            print(f"\nAssistente: {FALLBACK_TEXT}")
            continue
        if debug:
            for f in resposta["ferramentas"]:
                print(f"[ferramenta] {f['nome']}({f['args']})")
            print(f"[modelo] {resposta['modelo']}")
        print(f"\nAssistente: {resposta['texto']}")


def run_replay(graph, thread: str, entrada: Path, saida: Path) -> None:
    blocos = [f"# Conversa: {entrada.stem}"]
    for linha in entrada.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        resposta = respond(graph, thread, linha.strip())
        blocos.append(f"**Cliente:** {linha.strip()}")
        blocos.extend(f"> Ferramenta: `{f['nome']}({f['args']})`" for f in resposta["ferramentas"])
        blocos.append(f"**Assistente** (`{resposta['modelo']}`): {resposta['texto']}")
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n\n".join(blocos) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    parser = argparse.ArgumentParser(description="Agente de atendimento da Empório da Música")
    parser.add_argument("--thread", help="identificador da conversa, para retomá-la depois; sem ele, a conversa é nova")
    parser.add_argument("--debug", action="store_true", help="mostra ferramentas chamadas e modelo usado")
    parser.add_argument("--replay", type=Path, help="arquivo com uma mensagem do cliente por linha")
    parser.add_argument("--out", type=Path, help="arquivo Markdown de saída do --replay")
    args = parser.parse_args()
    if args.replay and not args.out:
        parser.error("--replay exige --out")
    if args.replay and not args.replay.is_file():
        parser.error(f"arquivo não encontrado: {args.replay}")
    logging.basicConfig(level=logging.WARNING if args.debug else logging.CRITICAL)

    try:
        chain = build_chain(build_models(ALL_TOOLS))
    except ConfigError as erro:
        print(erro, file=sys.stderr)
        return 2

    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(CHECKPOINTS, check_same_thread=False)
    try:
        graph = build_graph(chain, SqliteSaver(conexao))
        if args.replay:
            # Thread novo a cada captura, para o exemplo não herdar conversa anterior.
            run_replay(graph, f"{args.thread or 'exemplo'}-{uuid.uuid4().hex[:8]}", args.replay, args.out)
        else:
            # Conversa nova por padrão: um thread guarda o contato e o pedido verificado de um único cliente.
            run_chat(graph, args.thread or f"cliente-{uuid.uuid4().hex[:8]}", args.debug)
    finally:
        conexao.close()
        wait_for_all_tracers()  # o envio ao LangSmith roda em segundo plano e morreria com o processo
    return 0


if __name__ == "__main__":
    sys.exit(main())
