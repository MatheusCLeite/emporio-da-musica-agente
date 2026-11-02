import json

import pytest

import tools
from tools import ALL_TOOLS, buscar_produtos, consultar_pedido, consultar_politicas, dias_corridos_desde, registrar_encaminhamento


def test_pedido_inexistente_e_contato_errado_sao_iguais():
    a = consultar_pedido.invoke({"numero": "8", "contato": "(67) 90000-0000"})
    b = consultar_pedido.invoke({"numero": "999", "contato": "(67) 90000-0000"})
    assert a == b and "Ana" not in a and "BRJL" not in a


@pytest.mark.parametrize("numero", ["8", "#8", "pedido 8"])
def test_formatos_do_numero(numero):
    assert "BRJL5544332BR" in consultar_pedido.invoke({"numero": numero, "contato": "(67) 99654-7821"})


@pytest.mark.parametrize("data", ["28/10/2026", "2026-10-28"])
def test_dias_corridos(monkeypatch, data):
    monkeypatch.setenv("AGENT_NOW", "2026-11-02T10:00")
    assert json.loads(dias_corridos_desde.invoke({"data": data}))["dias"] == 5


@pytest.mark.parametrize("data", ["ontem", "31/02/2026", "10/10/2030"])
def test_data_invalida_ou_futura(monkeypatch, data):
    monkeypatch.setenv("AGENT_NOW", "2026-11-02T10:00")
    assert "erro" in json.loads(dias_corridos_desde.invoke({"data": data}))


def test_encaminhamento_grava_e_devolve_protocolo(tmp_path, monkeypatch):
    path = tmp_path / "h.jsonl"
    monkeypatch.setattr(tools, "HANDOFF_PATH", path)
    r = json.loads(registrar_encaminhamento.invoke({"motivo": "reclamacao", "resumo": "x", "contato": "(67) 99888-7777"}))
    assert r["protocolo"] and json.loads(path.read_text(encoding="utf-8"))["protocolo"] == r["protocolo"]
    assert "24 horas úteis" in r["prazo_retorno"]


def test_schema_tem_enum_de_tema_e_categoria():
    assert "frete" in str(consultar_politicas.args) and "Violões" in str(buscar_produtos.args)


def test_busca_devolve_json_com_acentos():
    saida = buscar_produtos.invoke({"termo": "Takamine GD20"})
    assert json.loads(saida)["disponiveis"][0]["id"] == 95 and "Violões" in saida


def test_politica_por_tema():
    assert "Rua 14 de Maio" in consultar_politicas.invoke({"tema": "loja"})


def test_lista_de_ferramentas_completa():
    assert {t.name for t in ALL_TOOLS} == {
        "buscar_produtos",
        "consultar_pedido",
        "consultar_politicas",
        "dias_corridos_desde",
        "registrar_encaminhamento",
    }


@pytest.mark.parametrize("contato", ["Não informado pelo usuário", "", "99999", "desconhecido"])
def test_encaminhamento_sem_contato_real_nao_gera_protocolo(contato, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "HANDOFF_PATH", tmp_path / "h.jsonl")
    resposta = json.loads(registrar_encaminhamento.invoke({"motivo": "m", "resumo": "r", "contato": contato}))
    assert "protocolo" not in resposta and "erro" in resposta
    assert not (tmp_path / "h.jsonl").exists()


@pytest.mark.parametrize("contato", ["(67) 99888-7777", "ana@exemplo.com"])
def test_encaminhamento_com_telefone_ou_email_gera_protocolo(contato, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "HANDOFF_PATH", tmp_path / "h.jsonl")
    resposta = json.loads(registrar_encaminhamento.invoke({"motivo": "m", "resumo": "r", "contato": contato}))
    assert resposta["protocolo"].startswith("EM-")
