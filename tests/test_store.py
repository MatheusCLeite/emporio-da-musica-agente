from datetime import date, datetime
from decimal import Decimal

import pytest

from store import TZ, centavo_acima, find_order, max_parcelas, search_products, status_loja


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


@pytest.mark.parametrize(
    "termo",
    ["Takamine GD-20", "Ohana CK20", "KA15S", "SGD195E", "RG-550", "RG 550", "Giannini GF3D", "gd20", "CK-20"],
)
def test_busca_aceita_codigo_de_modelo_escrito_de_outro_jeito(termo):
    assert search_products(termo=termo)["total_encontrado"] >= 1


def test_codigo_de_modelo_nao_vira_palpite():
    assert search_products(termo="XZ-999")["total_encontrado"] == 0
    assert search_products(termo="RG-551")["total_encontrado"] == 0


@pytest.mark.parametrize(("plural", "singular"), [("sintetizadores", "sintetizador"), ("profissionais", "profissional")])
def test_busca_aceita_plural(plural, singular):
    assert search_products(termo=plural)["total_encontrado"] == search_products(termo=singular)["total_encontrado"] > 0


def test_resultado_cortado_avisa_que_ha_mais_itens():
    assert search_products(categoria="Violões")["truncado"] is True
    assert search_products(termo="Takamine GD20")["truncado"] is False


@pytest.mark.parametrize("termo", ["🎸", "---", "吉他"])
def test_termo_sem_letras_nem_numeros_nao_devolve_o_catalogo(termo):
    assert search_products(termo=termo)["total_encontrado"] == 0


def _um(termo):
    return search_products(termo=termo)


def test_condicoes_sem_promocao_traz_parcelas_e_depois_pix():
    item = _um("Bateria Acustica Yamaha Kit 1")["disponiveis"][0]
    assert item["condicoes"] == "R$ 4.439,00 em até 12x sem juros no cartão ou R$ 4.217,05 no PIX"


def test_condicoes_com_promocao_traz_original_desconto_e_sem_pix():
    item = _um("Ohana CK-20")["disponiveis"][0]
    assert item["condicoes"] == "R$ 439,20 (de R$ 549,00, com 20% de desconto), em até 5x sem juros no cartão, sem desconto adicional no PIX"


def test_item_indisponivel_nao_traz_condicoes_de_compra():
    item = _um("Giannini GF-3D")["indisponiveis"][0]
    assert "condicoes" not in item


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("41.15", 41.15), ("41.152", 41.16), ("408.405", 408.41), ("41.1", 41.1), ("2089.05", 2089.05)],
)
def test_arredonda_so_a_partir_do_centavo_e_para_cima(valor, esperado):
    assert centavo_acima(Decimal(valor)) == esperado


@pytest.mark.parametrize(
    ("termo", "pix"),
    [("Tagima Memphis AC-39", 408.41), ("Yamaha C40", 569.91), ("Takamine GD20", 2089.05)],
)
def test_pix_usa_a_regra_do_centavo(termo, pix):
    assert search_products(termo=termo)["disponiveis"][0]["preco_pix"] == pix


def test_termo_que_nomeia_categoria_nao_traz_produto_de_outra():
    resultado = search_products(termo="violão")
    categorias = {i["categoria"] for i in resultado["disponiveis"] + resultado["indisponiveis"]}
    assert categorias == {"Violões"}
    assert "Kala KA-B Barítono Mogno" not in str(resultado)


def test_termo_sem_categoria_continua_buscando_na_descricao():
    assert "Kala KA-B Barítono Mogno" in str(search_products(termo="mogno"))
    assert search_products(termo="7 cordas")["total_encontrado"] >= 1


@pytest.mark.parametrize("contato", ["067 99654-7821", "+55 067 99654-7821", "0055 67 99654-7821"])
def test_telefone_com_zero_de_tronco_confere(contato):
    assert find_order("8", contato, date(2026, 11, 3)) is not None


def test_contato_so_com_zeros_nunca_confere():
    assert find_order("8", "000", date(2026, 11, 3)) is None
