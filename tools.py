"""Ferramentas expostas ao modelo. As docstrings orientam o modelo sobre quando usar cada uma."""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

from policies import TEMAS, get_policy
from store import CATEGORIAS, agora, find_order, search_products

HANDOFF_PATH = Path(__file__).resolve().parent / "runtime" / "handoffs.jsonl"
PEDIDO_NAO_VERIFICADO = {
    "verificado": False,
    "mensagem": "Não foi possível localizar um pedido com esse número e esse contato.",
}

Categoria = Literal[tuple(CATEGORIAS)]
Tema = Literal[tuple(TEMAS)]


def _contato_valido(contato: str) -> bool:
    # O modelo já tentou registrar "Não informado pelo usuário": protocolo sem contato é promessa que ninguém cumpre.
    return len(re.sub(r"\D", "", contato)) >= 10 or bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contato.strip()))


def _json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False)


@tool
def buscar_produtos(
    termo: str | None = None,
    categoria: Categoria | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
    em_promocao: bool = False,
) -> str:
    """Consulta o catálogo: preço, promoção ativa, estoque, parcelas, descrição e specs.

    Use para qualquer pergunta sobre produto, preço, disponibilidade, recomendação ou promoções vigentes
    (em_promocao=true lista as ativas). termo aceita marca, modelo ou característica.
    O resultado separa disponiveis, indisponiveis (com motivo) e alternativas, do mais barato ao mais caro.
    Com truncado=true há mais itens: refine a busca, por exemplo com preco_min para ver os mais caros.
    Com lista vazia, tente de novo com menos palavras antes de dizer que o catálogo não tem o item.
    """
    return _json(search_products(termo, categoria, preco_min, preco_max, em_promocao))


@tool
def consultar_pedido(numero: str, contato: str) -> str:
    """Consulta status, itens, total, rastreio e previsão de um pedido.

    Exige o número do pedido e o telefone ou e-mail do cliente cadastrado. Peça os dois ao cliente;
    nunca invente nem reaproveite contato de outra pessoa.
    """
    pedido = find_order(re.sub(r"\D", "", numero), contato, agora().date())
    return _json({"verificado": True, **pedido} if pedido else PEDIDO_NAO_VERIFICADO)


@tool
def consultar_politicas(tema: Tema) -> str:
    """Consulta o manual da loja por tema.

    loja: endereço, contatos e o que a loja vende. horarios: funcionamento. pagamento: formas e parcelamento.
    trocas_devolucoes: arrependimento, defeito e preferência. frete: entregas e rastreio.
    promocoes: regras de desconto (o que está em promoção agora vem de buscar_produtos). garantia: legal e de fabricante. privacidade: dados pessoais e LGPD.
    """
    return get_policy(tema)


@tool
def dias_corridos_desde(data: str) -> str:
    """Calcula os dias corridos entre uma data passada (dd/mm/aaaa ou aaaa-mm-dd) e hoje.

    Use para comparar com prazos de troca, devolução e garantia, em vez de fazer a conta de cabeça.
    """
    hoje = agora().date()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            inicio = datetime.strptime(data.strip(), formato).date()
        except ValueError:
            continue
        if inicio > hoje:
            return _json({"erro": "A data informada está no futuro."})
        return _json({"dias": (hoje - inicio).days})
    return _json({"erro": "Data inválida. Use o formato dd/mm/aaaa."})


@tool
def registrar_encaminhamento(motivo: str, resumo: str, contato: str) -> str:
    """Encaminha o caso à equipe humana e devolve um protocolo.

    Use em reclamações, pedido com previsão vencida, frete especial ou quando não houver dado para responder.
    Só use depois de o cliente informar um contato e concordar com o encaminhamento.
    """
    if not _contato_valido(contato):
        return _json({"erro": "Peça ao cliente um telefone com DDD ou e-mail antes de encaminhar."})
    momento = agora()
    protocolo = f"EM-{momento:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    registro = {"protocolo": protocolo, "em": momento.isoformat(), "motivo": motivo, "resumo": resumo, "contato": contato}
    with HANDOFF_PATH.open("a", encoding="utf-8") as arquivo:
        arquivo.write(_json(registro) + "\n")
    return _json({"protocolo": protocolo, "prazo_retorno": "24 horas úteis"})


ALL_TOOLS = [buscar_produtos, consultar_pedido, consultar_politicas, dias_corridos_desde, registrar_encaminhamento]
