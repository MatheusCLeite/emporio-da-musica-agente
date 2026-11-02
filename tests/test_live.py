"""Testes com modelos reais. Gastam cota, então só rodam com RUN_LIVE=1 e as chaves no .env."""

import os

import pytest
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from agent import build_chain, build_graph, build_models, respond
from tools import ALL_TOOLS

load_dotenv()
pytestmark = pytest.mark.skipif(
    not (os.environ.get("RUN_LIVE") and os.environ.get("GOOGLE_API_KEY")),
    reason="defina RUN_LIVE=1 e GOOGLE_API_KEY",
)


@pytest.mark.parametrize(
    ("pergunta", "ferramenta"),
    [
        ("Quanto custa o Takamine GD20?", "buscar_produtos"),
        ("Posso devolver minha compra?", "consultar_politicas"),
        ("Cadê o pedido 8? Meu telefone é (67) 99654-7821", "consultar_pedido"),
        ("Qual a capital da França?", None),
        ("Vocês têm violões até R$ 1000?", "buscar_produtos"),
        ("Estamos em novembro, cadê os descontos de Black Friday?", "buscar_produtos"),
    ],
)
def test_modelo_escolhe_a_ferramenta_certa(pergunta, ferramenta):
    graph = build_graph(build_chain(build_models(ALL_TOOLS)), MemorySaver())
    resposta = respond(graph, "live", pergunta)
    print(f"\n[{resposta['modelo']}] {resposta['texto']}")
    chamadas = [f["nome"] for f in resposta["ferramentas"]]
    assert ferramenta in chamadas if ferramenta else not chamadas
    assert "Paris" not in resposta["texto"]


def test_modelo_copia_as_condicoes_de_pagamento():
    graph = build_graph(build_chain(build_models(ALL_TOOLS)), MemorySaver())
    texto = respond(graph, "live", "Vocês têm bateria?")["texto"]
    assert "R$ 4.439,00 em até 12x sem juros no cartão ou R$ 4.217,05 no PIX" in texto
