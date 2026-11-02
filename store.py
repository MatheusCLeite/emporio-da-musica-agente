"""Dados da loja e regras de negócio determinísticas (preço, estoque, parcelas, pedidos)."""

import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("America/Campo_Grande")
DATA_DIR = Path(__file__).parent / "data"

# shortcut: lista revisada à mão, corrigir na origem com dados reais
# Nome, descrição e specs destes produtos se contradizem no CSV.
CONFLITO_CATALOGO = frozenset({135, 136, 137, 139, 140, 142, 144})

CATEGORIAS = [
    "Guitarras",
    "Baixos",
    "Baterias e Percussão",
    "Teclados e Pianos",
    "Violões",
    "Instrumentos de Sopro (Madeiras)",
    "Instrumentos de Sopro (Metais)",
    "Cordas Orquestrais",
    "Ukuleles",
]
# (abertura, fechamento) em horas, por weekday(); domingo fechado.
HORARIOS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
LIMITE_RESULTADOS = 15
MOTIVOS = {"discontinued": "descontinuado", "coming_soon": "em_breve"}


def agora() -> datetime:
    fixo = os.environ.get("AGENT_NOW")
    return datetime.fromisoformat(fixo).replace(tzinfo=TZ) if fixo else datetime.now(TZ)


def status_loja(dt: datetime) -> str:
    horario = HORARIOS.get(dt.weekday())
    if horario and horario[0] <= dt.hour < horario[1]:
        return f"Loja aberta agora, até {horario[1]:02d}:00."
    for dias in range(8):
        dia = dt + timedelta(days=dias)
        abertura = HORARIOS.get(dia.weekday())
        if abertura and (dias > 0 or dt.hour < abertura[0]):
            quando = "hoje" if dias == 0 else DIAS[dia.weekday()]
            return f"Loja fechada agora. Reabre {quando} às {abertura[0]:02d}:00."
    raise ValueError("Tabela de horários vazia")


def max_parcelas(valor: float) -> int:
    def minimo(n):
        return 50 if n <= 3 else 80 if n <= 6 else 100

    return max((n for n in range(1, 13) if valor / n >= minimo(n)), default=1)


def _tabela(nome: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"desafio_tecnico_ai_eng - {nome}.csv", encoding="utf-8")


def _raiz(palavra: str) -> str:
    if palavra.endswith("oes"):
        return palavra[:-3] + "ao"
    if palavra.endswith("ais") and len(palavra) > 4:
        return palavra[:-2] + "l"
    if palavra.endswith("res") and len(palavra) > 4:
        return palavra[:-2]
    return palavra[:-1] if palavra.endswith("s") and len(palavra) > 3 else palavra


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _tokens(texto: str) -> set[str]:
    return {_raiz(p) for p in re.findall(r"[a-z0-9]+", _sem_acento(texto))}


def _compacto(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _sem_acento(texto))


def _casa_com_termo(item: dict, termo: str) -> bool:
    tokens = _tokens(termo)
    if tokens and tokens <= item["_busca"]:
        return True
    # Códigos de modelo variam na escrita: GD20, GD-20 e GD 20 são o mesmo produto.
    compacto = _compacto(termo)
    return any(c.isdigit() for c in compacto) and compacto in item["_nome_compacto"]


def _motivo(produto: dict) -> str | None:
    if produto["status"] != "active":
        return MOTIVOS[produto["status"]]
    return None if produto["stock_quantity"] > 0 else "sem_estoque"


def _item(p: dict, categoria: str, promo: dict | None) -> dict:
    tabela = float(p["price_brl"])
    desconto = int(promo["discount_percent"]) if promo else None
    final = round(tabela * (1 - desconto / 100), 2) if promo else tabela
    item = {
        "id": int(p["product_id"]),
        "nome": p["name"],
        "categoria": categoria,
        "preco_tabela": tabela,
        "promocao": promo["description"] if promo else None,
        "desconto_percentual": desconto,
        "preco_final": final,
        "preco_pix": None if promo else round(tabela * 0.95, 2),
        "max_parcelas": max_parcelas(final),
        "estoque": int(p["stock_quantity"]),
    }
    motivo = _motivo(p)
    if motivo:
        item["motivo"] = motivo
    if item["id"] in CONFLITO_CATALOGO:
        item["ficha_tecnica_indisponivel"] = True
        busca = f"{p['name']} {categoria}"
    else:
        item["descricao"] = p["description"]
        item["specs"] = json.loads(p["specs"])
        busca = f"{p['name']} {categoria} {p['description']} {' '.join(item['specs'].values())}"
    item["_busca"] = _tokens(busca)
    item["_nome_compacto"] = _compacto(p["name"])
    return item


def _catalogo() -> list[dict]:
    """Produtos com preço final calculado, prontos para filtrar e apresentar."""
    categorias = _tabela("categories")
    nomes = dict(zip(categorias.category_id, categorias.name))
    ativas = _tabela("promotions").query("is_active == 1").sort_values("discount_percent")
    # Ordem crescente: se houver mais de uma promoção ativa, a última (maior desconto) prevalece.
    promos = {p["product_id"]: p for p in ativas.to_dict("records")}
    return [_item(p, nomes[p["category_id"]], promos.get(p["product_id"])) for p in _tabela("products").to_dict("records")]


def _publico(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _listar(itens: list[dict]) -> list[dict]:
    return [_publico(i) for i in sorted(itens, key=lambda i: i["preco_final"])[:LIMITE_RESULTADOS]]


def search_products(termo=None, categoria=None, preco_min=None, preco_max=None, em_promocao=False) -> dict:
    catalogo = _catalogo()
    achados = catalogo
    if termo:
        achados = [i for i in achados if _casa_com_termo(i, termo)]
    if categoria:
        achados = [i for i in achados if _tokens(i["categoria"]) == _tokens(categoria)]
    if preco_min is not None:
        achados = [i for i in achados if i["preco_final"] >= preco_min]
    if preco_max is not None:
        achados = [i for i in achados if i["preco_final"] <= preco_max]
    if em_promocao:
        achados = [i for i in achados if i["desconto_percentual"] is not None]

    disponiveis = [i for i in achados if "motivo" not in i]
    # Em buscas por faixa de preço ou promoção, itens indisponíveis só atrapalhariam o cliente.
    so_termo = termo and preco_min is None and preco_max is None and not em_promocao
    indisponiveis = [i for i in achados if "motivo" in i] if so_termo else []

    alternativas = []
    if indisponiveis and not disponiveis:
        base = indisponiveis[0]
        candidatos = [i for i in catalogo if "motivo" not in i and i["categoria"] == base["categoria"]]
        alternativas = sorted(candidatos, key=lambda i: abs(i["preco_final"] - base["preco_final"]))[:3]

    return {
        "disponiveis": _listar(disponiveis),
        "indisponiveis": _listar(indisponiveis),
        "alternativas": [_publico(i) for i in alternativas],
        "total_encontrado": len(disponiveis) + len(indisponiveis),
        "truncado": max(len(disponiveis), len(indisponiveis)) > LIMITE_RESULTADOS,
    }


def _digitos(texto: str) -> str:
    digitos = re.sub(r"\D", "", texto)
    return digitos[2:] if len(digitos) > 11 and digitos.startswith("55") else digitos


def _contato_confere(contato: str, cliente: dict) -> bool:
    contato = contato.strip()
    if "@" in contato:
        return contato.casefold() == cliente["email"].casefold()
    return bool(_digitos(contato)) and _digitos(contato) == _digitos(cliente["phone"])


def _opcional(valor):
    return None if pd.isna(valor) else valor


def find_order(numero: str, contato: str, hoje: date) -> dict | None:
    if not numero.isdigit():
        return None
    pedidos = _tabela("orders")
    pedidos = pedidos[pedidos.order_id == int(numero)]
    if pedidos.empty:
        return None
    pedido = pedidos.iloc[0].to_dict()
    clientes = _tabela("customers")
    cliente = clientes[clientes.customer_id == pedido["customer_id"]].iloc[0].to_dict()
    if not _contato_confere(contato, cliente):
        return None

    itens = _tabela("order_items")
    produtos = _tabela("products")
    nomes = dict(zip(produtos.product_id, produtos.name))
    previsao = _opcional(pedido["estimated_delivery"])
    return {
        "numero": int(numero),
        "cliente_primeiro_nome": cliente["name"].split()[0],
        "status": pedido["status"],
        "itens": [
            {"nome": nomes[i.product_id], "quantidade": int(i.quantity)}
            for i in itens[itens.order_id == int(numero)].itertuples()
        ],
        "total_registrado": float(pedido["total_brl"]),
        "pagamento": pedido["payment_method"],
        "rastreio": _opcional(pedido["tracking_code"]),
        "previsao": previsao,
        "previsao_vencida": bool(pedido["status"] == "shipped" and previsao and date.fromisoformat(previsao) < hoje),
        "observacoes": _opcional(pedido["notes"]),
    }
