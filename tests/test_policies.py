import pytest

from policies import TEMAS, get_policy


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


def test_calendario_de_promocoes_avisa_que_nao_indica_promocao_ativa():
    texto = get_policy("promocoes")
    assert texto.index("em_promocao=true") < texto.index("Black Friday")


def test_troca_por_defeito_lembra_a_garantia_legal():
    assert "garantia legal" in get_policy("trocas_devolucoes")


def test_tema_invalido():
    with pytest.raises(KeyError):
        get_policy("astrologia")
