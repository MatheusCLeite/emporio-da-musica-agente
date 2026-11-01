from datetime import date, datetime

import pytest

from store import TZ, find_order, max_parcelas, search_products, status_loja


def ids(items):
    return {i["id"] for i in items}


def test_violoes_ate_1000():
    r = search_products(categoria="Violões", preco_max=1000)
    assert ids(r["disponiveis"]) == {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112}
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


@pytest.mark.parametrize("valor,n", [(159.9, 3), (323.1, 4), (439.2, 5), (1199, 11), (2199, 12), (40, 1)])
def test_max_parcelas(valor, n):
    assert max_parcelas(valor) == n


@pytest.mark.parametrize("contato", ["(67) 99654-7821", "+55 67 99654-7821", "ANACAROL.FERREIRA@coldmail.com"])
def test_pedido_contato_certo(contato):
    o = find_order("8", contato, date(2026, 11, 1))
    assert o["rastreio"] == "BRJL5544332BR" and o["previsao_vencida"] is True
    assert o["cliente_primeiro_nome"] == "Ana" and o["itens"][0]["nome"] == "Kala KA-C Concert Mogno"


@pytest.mark.parametrize(
    "numero,contato",
    [("8", "(67) 90000-0000"), ("8", ""), ("8", "   "), ("999", "(67) 99654-7821"), ("abc", "(67) 99654-7821")],
)
def test_pedido_negado(numero, contato):
    assert find_order(numero, contato, date(2026, 11, 1)) is None


def test_previsao_vencida_so_em_shipped():
    assert find_order("1", "(67) 98432-1098", date(2026, 11, 1))["previsao_vencida"] is False


@pytest.mark.parametrize(
    "dt,esperado",
    [
        ("2026-11-01T10:00", "fechada"),  # domingo
        ("2026-11-02T08:59", "fechada"),
        ("2026-11-02T09:00", "aberta"),
        ("2026-11-07T12:59", "aberta"),  # sábado
        ("2026-11-07T13:00", "fechada"),
    ],
)
def test_status_loja(dt, esperado):
    assert esperado in status_loja(datetime.fromisoformat(dt).replace(tzinfo=TZ))


def test_status_loja_informa_reabertura():
    s = status_loja(datetime.fromisoformat("2026-11-07T13:00").replace(tzinfo=TZ))
    assert "segunda" in s and "09:00" in s
